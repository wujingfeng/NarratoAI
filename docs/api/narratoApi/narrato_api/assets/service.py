from __future__ import annotations

import secrets
import time
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from narrato_api.api.errors import ApiError
from narrato_api.assets.constraints import (
    AssetDeclarationError,
    validate_asset_declaration,
)
from narrato_api.assets.models import Asset
from narrato_api.integrations.core_client import CoreClientError, MediaProbeResult
from narrato_api.integrations.oss_client import OssClientError, OssObject
from narrato_api.projects.models import Project

POLICY_RESERVATION_TTL = timedelta(minutes=10)


def new_asset_id() -> str:
    """生成不可由用户输入控制的资产 ID。"""

    return f"ast_{time.time_ns():016x}{secrets.token_hex(8)}"


def project_for_update_statement(*, user_id: str, project_id: str) -> Any:
    """构造 PostgreSQL 项目行锁；SQLite 测试环境不模拟该并发语义。"""

    return (
        select(Project)
        .where(Project.id == project_id, Project.user_id == user_id)
        .with_for_update()
    )


class UploadService:
    """将已直传对象以归属、HEAD 和探测结果登记为资产。"""

    def __init__(
        self,
        *,
        session_factory: Callable[[], Session],
        oss_client: Any,
        core_client: Any,
        oss_bucket: str,
    ) -> None:
        self.session_factory = session_factory
        self.oss_client = oss_client
        self.core_client = core_client
        self.oss_bucket = oss_bucket

    def complete(
        self,
        *,
        user_id: str,
        project_id: str,
        asset_type: str,
        filename: str,
        size_bytes: int,
        content_type: str,
        object_key: str,
    ) -> Asset:
        """HEAD 复核直传对象后触发 Core，并记录 validating 到终态的转换。"""

        if not object_key.startswith("narrato/api/") or "/../" in object_key:
            raise ApiError("UPLOAD_OBJECT_REJECTED", "Uploaded object is invalid", 422)
        try:
            with self.session_factory() as session:
                self._owned_project(session, user_id=user_id, project_id=project_id)
                asset = session.scalar(
                    select(Asset).where(
                        Asset.user_id == user_id,
                        Asset.project_id == project_id,
                        Asset.bucket == self.oss_bucket,
                        Asset.object_key == object_key,
                    )
                )
                if (
                    asset is None
                    or asset.filename != filename
                    or asset.asset_type != asset_type
                    or asset.size_bytes != size_bytes
                ):
                    raise ApiError(
                        "UPLOAD_OBJECT_REJECTED", "Uploaded object is invalid", 422
                    )
                existing_video_count = int(
                    session.scalar(
                        select(func.count())
                        .select_from(Asset)
                        .where(
                            Asset.project_id == project_id, Asset.asset_type == "video"
                        )
                    )
                    or 0
                )
                declaration = validate_asset_declaration(
                    asset_type=asset_type,
                    filename=filename,
                    size_bytes=size_bytes,
                    existing_video_count=existing_video_count,
                )
                expected_content_type = self._expected_content_type(
                    declaration.extension
                )
                if content_type != expected_content_type:
                    raise ApiError(
                        "UPLOAD_CONTENT_TYPE_REJECTED",
                        "Uploaded object is invalid",
                        422,
                    )
                object_info = self.oss_client.head_object(self.oss_bucket, object_key)
                self._validate_head(object_info, size_bytes, expected_content_type)
                asset.reservation_expires_at = None
                session.commit()
                session.refresh(asset)
        except AssetDeclarationError as error:
            raise ApiError(
                "UPLOAD_DECLARATION_REJECTED", "Upload declaration is invalid", 422
            ) from error
        except OssClientError as error:
            raise ApiError(
                "OSS_UNAVAILABLE", "Upload object verification is unavailable", 503
            ) from error

        try:
            probe: MediaProbeResult = self.core_client.probe_media(
                source_url=asset.cdn_url,
                media_type=asset_type,
                declared_extension=declaration.extension,
                caller_task_id=asset.id,
            )
        except CoreClientError as error:
            raise ApiError(
                "MEDIA_PROBE_UNAVAILABLE", "Media validation is unavailable", 503
            ) from error
        if probe.valid is not None:
            with self.session_factory() as session:
                persisted = session.get(Asset, asset.id)
                if persisted is None:
                    raise ApiError("ASSET_NOT_FOUND", "Asset not found", 404)
                persisted.status = "ready" if probe.valid else "invalid"
                if persisted.asset_type == "video" and probe.valid:
                    persisted.duration_seconds = probe.duration_seconds
                session.commit()
                session.refresh(persisted)
                return persisted
        if probe.core_task_id:
            with self.session_factory() as session:
                persisted = session.get(Asset, asset.id)
                if persisted is None:
                    raise ApiError("ASSET_NOT_FOUND", "Asset not found", 404)
                persisted.core_task_id = probe.core_task_id
                session.commit()
                session.refresh(persisted)
                return persisted
        return asset

    def reserve(
        self,
        *,
        user_id: str,
        project_id: str,
        asset_type: str,
        filename: str,
        size_bytes: int,
        object_key: str,
        cdn_url: str,
    ) -> None:
        """用项目行锁、有限预留 TTL 原子保留可完成的单一对象键。"""
        with self.session_factory() as session:
            project = session.scalar(
                project_for_update_statement(user_id=user_id, project_id=project_id)
            )
            if project is None:
                raise ApiError("PROJECT_NOT_FOUND", "Project not found", 404)
            now = datetime.now(timezone.utc)
            session.execute(
                delete(Asset).where(
                    Asset.project_id == project_id,
                    Asset.status == "validating",
                    Asset.core_task_id.is_(None),
                    Asset.reservation_expires_at.is_not(None),
                    Asset.reservation_expires_at <= now,
                )
            )
            existing_video_count = int(
                session.scalar(
                    select(func.count())
                    .select_from(Asset)
                    .where(
                        Asset.project_id == project_id,
                        Asset.asset_type == "video",
                        or_(
                            Asset.reservation_expires_at.is_(None),
                            Asset.reservation_expires_at > now,
                        ),
                    )
                )
                or 0
            )
            try:
                validate_asset_declaration(
                    asset_type=asset_type,
                    filename=filename,
                    size_bytes=size_bytes,
                    existing_video_count=existing_video_count,
                )
            except AssetDeclarationError as error:
                raise ApiError(
                    "UPLOAD_DECLARATION_REJECTED", "Upload declaration is invalid", 422
                ) from error
            session.add(
                Asset(
                    id=new_asset_id(),
                    user_id=user_id,
                    project_id=project.id,
                    asset_type=asset_type,
                    status="validating",
                    filename=filename,
                    bucket=self.oss_bucket,
                    object_key=object_key,
                    cdn_url=cdn_url,
                    size_bytes=size_bytes,
                    reservation_expires_at=now + POLICY_RESERVATION_TTL,
                )
            )
            session.commit()

    def get_owned_asset(self, *, user_id: str, asset_id: str) -> Asset:
        """读取单个归属资产，并在后续请求中收敛异步 Core 探测终态。"""

        with self.session_factory() as session:
            asset = session.scalar(
                select(Asset).where(Asset.id == asset_id, Asset.user_id == user_id)
            )
            if asset is None:
                raise ApiError("ASSET_NOT_FOUND", "Asset not found", 404)
            core_task_id = (
                asset.core_task_id
                if asset.status == "validating"
                or (
                    asset.asset_type == "video"
                    and asset.duration_seconds is None
                    and asset.core_task_id is not None
                )
                else None
            )
        if not core_task_id:
            return asset
        try:
            probe: MediaProbeResult = self.core_client.get_probe_result(core_task_id)
        except CoreClientError as error:
            raise ApiError(
                "MEDIA_PROBE_UNAVAILABLE", "Media validation is unavailable", 503
            ) from error
        if probe.valid is None:
            return asset
        with self.session_factory() as session:
            persisted = session.scalar(
                select(Asset).where(Asset.id == asset_id, Asset.user_id == user_id)
            )
            if persisted is None:
                raise ApiError("ASSET_NOT_FOUND", "Asset not found", 404)
            if persisted.core_task_id == core_task_id and (
                persisted.status == "validating"
                or (
                    persisted.asset_type == "video"
                    and persisted.duration_seconds is None
                )
            ):
                persisted.status = "ready" if probe.valid else "invalid"
                if persisted.asset_type == "video" and probe.valid:
                    persisted.duration_seconds = probe.duration_seconds
                session.commit()
                session.refresh(persisted)
            return persisted

    def reconcile_owned_project_assets(self, *, user_id: str, project_id: str) -> None:
        """报价前轮询项目素材，补回历史媒体探测遗漏的时长。"""

        with self.session_factory() as session:
            self._owned_project(session, user_id=user_id, project_id=project_id)
            asset_ids = list(
                session.scalars(
                    select(Asset.id).where(
                        Asset.user_id == user_id, Asset.project_id == project_id
                    )
                )
            )
        for asset_id in asset_ids:
            self.get_owned_asset(user_id=user_id, asset_id=asset_id)

    @staticmethod
    def _owned_project(session: Session, *, user_id: str, project_id: str) -> Project:
        project = session.scalar(
            select(Project).where(Project.id == project_id, Project.user_id == user_id)
        )
        if project is None:
            raise ApiError("PROJECT_NOT_FOUND", "Project not found", 404)
        return project

    @staticmethod
    def _expected_content_type(extension: str) -> str:
        return {
            ".mp4": "video/mp4",
            ".mov": "video/quicktime",
            ".avi": "video/x-msvideo",
            ".srt": "application/octet-stream",
        }[extension]

    @staticmethod
    def _validate_head(
        object_info: OssObject, size_bytes: int, content_type: str
    ) -> None:
        if (
            object_info.size_bytes != size_bytes
            or object_info.content_type != content_type
        ):
            raise ApiError("UPLOAD_OBJECT_REJECTED", "Uploaded object is invalid", 422)
