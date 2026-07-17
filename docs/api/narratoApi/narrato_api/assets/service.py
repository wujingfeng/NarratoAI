from __future__ import annotations

import secrets
import time
from collections.abc import Callable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from narrato_api.api.errors import ApiError
from narrato_api.assets.constraints import AssetDeclarationError, validate_asset_declaration
from narrato_api.assets.models import Asset
from narrato_api.integrations.core_client import CoreClientError, MediaProbeResult
from narrato_api.integrations.oss_client import OssClientError, OssObject
from narrato_api.projects.models import Project


def new_asset_id() -> str:
    """生成不可由用户输入控制的资产 ID。"""

    return f"ast_{time.time_ns():016x}{secrets.token_hex(8)}"


class UploadService:
    """将已直传对象以归属、HEAD 和探测结果登记为资产。"""

    def __init__(
        self,
        *,
        session_factory: Callable[[], Session],
        oss_client: object,
        core_client: object,
        oss_bucket: str,
    ) -> None:
        self.session_factory = session_factory
        self.oss_client = oss_client
        self.core_client = core_client
        self.oss_bucket = oss_bucket

    def existing_video_count(self, *, user_id: str, project_id: str) -> int:
        """在项目归属确认后读取视频声明配额。"""

        with self.session_factory() as session:
            self._owned_project(session, user_id=user_id, project_id=project_id)
            return int(
                session.scalar(
                    select(func.count()).select_from(Asset).where(
                        Asset.project_id == project_id, Asset.asset_type == "video"
                    )
                )
                or 0
            )

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
                asset = session.scalar(select(Asset).where(Asset.user_id == user_id, Asset.project_id == project_id, Asset.bucket == self.oss_bucket, Asset.object_key == object_key))
                if asset is None or asset.filename != filename or asset.asset_type != asset_type or asset.size_bytes != size_bytes:
                    raise ApiError("UPLOAD_OBJECT_REJECTED", "Uploaded object is invalid", 422)
                existing_video_count = int(
                    session.scalar(
                        select(func.count()).select_from(Asset).where(
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
                expected_content_type = self._expected_content_type(declaration.extension)
                if content_type != expected_content_type:
                    raise ApiError("UPLOAD_CONTENT_TYPE_REJECTED", "Uploaded object is invalid", 422)
                object_info = self.oss_client.head_object(self.oss_bucket, object_key)
                self._validate_head(object_info, size_bytes, expected_content_type)
                session.commit()
                session.refresh(asset)
        except AssetDeclarationError as error:
            raise ApiError("UPLOAD_DECLARATION_REJECTED", "Upload declaration is invalid", 422) from error
        except OssClientError as error:
            raise ApiError("UPLOAD_OBJECT_REJECTED", "Uploaded object is invalid", 422) from error

        try:
            probe: MediaProbeResult = self.core_client.probe_media(
                source_url=asset.cdn_url, media_type=asset_type,
                declared_extension=declaration.extension, caller_task_id=asset.id,
            )
        except CoreClientError as error:
            raise ApiError("MEDIA_PROBE_UNAVAILABLE", "Media validation is unavailable", 503) from error
        if probe.valid is None and probe.core_task_id:
            try:
                probe = self.core_client.get_probe_result(probe.core_task_id)
            except CoreClientError as error:
                raise ApiError("MEDIA_PROBE_UNAVAILABLE", "Media validation is unavailable", 503) from error
        if probe.valid is not None:
            with self.session_factory() as session:
                persisted = session.get(Asset, asset.id)
                if persisted is None:
                    raise ApiError("ASSET_NOT_FOUND", "Asset not found", 404)
                persisted.status = "ready" if probe.valid else "invalid"
                session.commit()
                session.refresh(persisted)
                return persisted
        return asset

    def reserve(self, *, user_id: str, project_id: str, asset_type: str, filename: str, size_bytes: int, object_key: str, cdn_url: str) -> None:
        """在签发 Policy 时先持久化唯一对象键，令 complete 只能消费该预留。"""
        with self.session_factory() as session:
            project = self._owned_project(session, user_id=user_id, project_id=project_id)
            session.add(Asset(id=new_asset_id(), user_id=user_id, project_id=project.id, asset_type=asset_type, status="validating", filename=filename, bucket=self.oss_bucket, object_key=object_key, cdn_url=cdn_url, size_bytes=size_bytes))
            session.commit()

    @staticmethod
    def _owned_project(session: Session, *, user_id: str, project_id: str) -> Project:
        project = session.scalar(select(Project).where(Project.id == project_id, Project.user_id == user_id))
        if project is None:
            raise ApiError("PROJECT_NOT_FOUND", "Project not found", 404)
        return project

    @staticmethod
    def _expected_content_type(extension: str) -> str:
        return {".mp4": "video/mp4", ".mov": "video/quicktime", ".avi": "video/x-msvideo", ".srt": "application/x-subrip"}[extension]

    @staticmethod
    def _validate_head(object_info: OssObject, size_bytes: int, content_type: str) -> None:
        if object_info.size_bytes != size_bytes or object_info.content_type != content_type:
            raise ApiError("UPLOAD_OBJECT_REJECTED", "Uploaded object is invalid", 422)
