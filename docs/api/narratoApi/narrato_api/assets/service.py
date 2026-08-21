from __future__ import annotations

import logging
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
    MAX_AI_VIDEO_PROJECT_VIDEO_COUNT,
    validate_asset_declaration,
)
from narrato_api.assets.models import Asset
from narrato_api.integrations.core_client import (
    CoreClientError,
    CoreClientRejectedError,
    MediaProbeResult,
)
from narrato_api.integrations.oss_client import OssClientError, OssObject
from narrato_api.projects.models import Project

POLICY_RESERVATION_TTL = timedelta(minutes=10)
_PROJECT_DELETION_STATES = frozenset({"deleting", "deleted"})
logger = logging.getLogger(__name__)


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
                project = session.scalar(
                    project_for_update_statement(user_id=user_id, project_id=project_id)
                )
                if project is None:
                    raise ApiError("PROJECT_NOT_FOUND", "Project not found", 404)
                self._ensure_asset_mutable(project)
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
                    max_video_count=(MAX_AI_VIDEO_PROJECT_VIDEO_COUNT if project.product == "ai_video" else 5),
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

        # 图片的类型/大小已由直传策略和 OSS HEAD 双重锁定，无需送往仅处理
        # 音视频探测的 Core；这也保证 AI 视频供应商调用不会经 Core 中转。
        if asset_type == "image":
            with self.session_factory() as session:
                persisted = session.get(Asset, asset.id)
                if persisted is None:
                    raise ApiError("ASSET_NOT_FOUND", "Asset not found", 404)
                persisted.status = "ready"
                session.commit()
                session.refresh(persisted)
                return persisted
        try:
            probe: MediaProbeResult = self.core_client.probe_media(
                source_url=asset.cdn_url,
                media_type=asset_type,
                declared_extension=declaration.extension,
                caller_task_id=asset.id,
            )
        except CoreClientRejectedError as error:
            raise ApiError(
                "MEDIA_PROBE_REJECTED",
                "Media validation rejected the uploaded file",
                422,
            ) from error
        except CoreClientError as error:
            raise ApiError(
                "MEDIA_PROBE_UNAVAILABLE", "Media validation is unavailable", 503
            ) from error
        if probe.valid is not None:
            with self.session_factory() as session:
                project = session.scalar(
                    project_for_update_statement(user_id=user_id, project_id=project_id)
                )
                if project is None:
                    raise ApiError("PROJECT_NOT_FOUND", "Project not found", 404)
                self._ensure_asset_mutable(project)
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
                project = session.scalar(
                    project_for_update_statement(user_id=user_id, project_id=project_id)
                )
                if project is None:
                    raise ApiError("PROJECT_NOT_FOUND", "Project not found", 404)
                self._ensure_asset_mutable(project)
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
            self._ensure_asset_mutable(project)
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
                    max_video_count=(MAX_AI_VIDEO_PROJECT_VIDEO_COUNT if project.product == "ai_video" else 5),
                )
            except AssetDeclarationError as error:
                raise ApiError(
                    "UPLOAD_DECLARATION_REJECTED", "Upload declaration is invalid", 422
                ) from error
            highest_sort_order = session.scalar(
                select(func.max(Asset.sort_order)).where(
                    Asset.project_id == project_id,
                    Asset.asset_type == asset_type,
                )
            )
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
                    sort_order=(
                        highest_sort_order if highest_sort_order is not None else -1
                    )
                    + 1,
                    reservation_expires_at=now + POLICY_RESERVATION_TTL,
                )
            )
            session.commit()

    def reorder_owned_video_assets(
        self, *, user_id: str, project_id: str, asset_ids: list[str]
    ) -> list[str]:
        """在任务启动前原子保存完整视频顺序，拒绝遗漏、重复或越权素材。"""

        if len(asset_ids) != len(set(asset_ids)):
            raise ApiError(
                "PROJECT_ASSET_ORDER_INVALID",
                "Video asset order contains duplicates",
                422,
            )
        with self.session_factory() as session:
            project = session.scalar(
                project_for_update_statement(user_id=user_id, project_id=project_id)
            )
            if project is None:
                raise ApiError("PROJECT_NOT_FOUND", "Project not found", 404)
            self._ensure_asset_mutable(
                project,
                code="PROJECT_ASSET_ORDER_LOCKED",
                message="Project assets can no longer be reordered",
            )
            if (
                project.current_stage not in {"created", "settings"}
                or project.is_locked
            ):
                raise ApiError(
                    "PROJECT_ASSET_ORDER_LOCKED",
                    "Project assets can no longer be reordered",
                    409,
                )
            now = datetime.now(timezone.utc)
            videos = list(
                session.scalars(
                    select(Asset)
                    .where(
                        Asset.user_id == user_id,
                        Asset.project_id == project_id,
                        Asset.asset_type == "video",
                        or_(
                            Asset.reservation_expires_at.is_(None),
                            Asset.reservation_expires_at > now,
                        ),
                    )
                    .order_by(Asset.sort_order, Asset.created_at, Asset.id)
                )
            )
            videos_by_id = {video.id: video for video in videos}
            if len(asset_ids) != len(videos) or set(asset_ids) != set(videos_by_id):
                raise ApiError(
                    "PROJECT_ASSET_ORDER_INVALID",
                    "Video asset order must contain every project video exactly once",
                    422,
                )
            for sort_order, asset_id in enumerate(asset_ids):
                videos_by_id[asset_id].sort_order = sort_order
            session.commit()
            return asset_ids

    def get_owned_asset(self, *, user_id: str, asset_id: str) -> Asset:
        """读取单个归属资产，并在后续请求中收敛异步 Core 探测终态。"""

        with self.session_factory() as session:
            asset = session.scalar(
                select(Asset).where(Asset.id == asset_id, Asset.user_id == user_id)
            )
            if asset is None:
                raise ApiError("ASSET_NOT_FOUND", "Asset not found", 404)
            project_id = asset.project_id
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
            project = session.scalar(
                project_for_update_statement(user_id=user_id, project_id=project_id)
            )
            if project is None:
                raise ApiError("PROJECT_NOT_FOUND", "Project not found", 404)
            self._ensure_asset_mutable(project)
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

    def remove_owned_asset(
        self, *, user_id: str, project_id: str, asset_id: str
    ) -> None:
        """删除尚未开始项目的素材记录和已上传 OSS 对象。"""

        object_to_delete: tuple[str, str] | None = None
        with self.session_factory() as session:
            project = session.scalar(
                project_for_update_statement(user_id=user_id, project_id=project_id)
            )
            if project is None:
                raise ApiError("PROJECT_NOT_FOUND", "Project not found", 404)
            if project.status not in {"draft", "uploading", "validating", "ready"}:
                raise ApiError(
                    "PROJECT_ASSET_LOCKED",
                    "Project assets can no longer be removed",
                    409,
                )
            asset = session.scalar(
                select(Asset).where(
                    Asset.id == asset_id,
                    Asset.project_id == project_id,
                    Asset.user_id == user_id,
                )
            )
            if asset is None:
                raise ApiError("ASSET_NOT_FOUND", "Asset not found", 404)
            shared_count = int(
                session.scalar(
                    select(func.count())
                    .select_from(Asset)
                    .join(Project, Project.id == Asset.project_id)
                    .where(
                        Asset.bucket == asset.bucket,
                        Asset.object_key == asset.object_key,
                        Asset.id != asset.id,
                        Project.status != "deleted",
                    )
                )
                or 0
            )
            if shared_count == 0:
                object_to_delete = (asset.bucket, asset.object_key)
            session.delete(asset)
            session.commit()

        # 先提交业务删除，保证已从页面移除的素材不会在后续排序时残留。
        # OSS 临时不可用仅影响对象清理，不应阻塞项目继续创建。
        if object_to_delete is not None:
            try:
                self.oss_client.delete_object(*object_to_delete)
            except OssClientError:
                logger.warning(
                    "asset object cleanup deferred because OSS is unavailable",
                    extra={"project_id": project_id, "asset_id": asset_id},
                )

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
    def _ensure_asset_mutable(
        project: Project,
        *,
        code: str = "PROJECT_ASSET_LOCKED",
        message: str = "Project assets cannot change while the project is being deleted",
    ) -> None:
        if project.status in _PROJECT_DELETION_STATES:
            raise ApiError(code, message, 409)

    @staticmethod
    def _expected_content_type(extension: str) -> str:
        return {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".webp": "image/webp",
            ".mp4": "video/mp4",
            ".mov": "video/quicktime",
            ".avi": "video/x-msvideo",
            ".srt": "application/octet-stream",
            ".mp3": "audio/mpeg",
            ".wav": "audio/wav",
            ".m4a": "audio/mp4",
            ".aac": "audio/aac",
            ".ogg": "audio/ogg",
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
