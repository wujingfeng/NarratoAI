from __future__ import annotations

import hashlib
import mimetypes
import os
import secrets
import stat
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from core_api.ids import new_time_ordered_id
from core_api.infrastructure.oss_client import OssClient, build_object_key, normalize_extension
from core_api.runtime.workspace import CoreTaskWorkspace, WorkspaceSecurityError


class ArtifactSecurityError(ValueError):
    """上传文件不属于当前 attempt output 或类型不受支持。"""

    code = "ARTIFACT_PATH_REJECTED"
    retryable = False


@dataclass(frozen=True, slots=True)
class ArtifactRef:
    """跨服务可返回的统一 Artifact DTO。"""

    artifact_id: str
    kind: str
    bucket: str
    object_key: str
    url: str
    content_type: str
    size: int
    checksum: str | None = None

    def to_dict(self) -> dict[str, object]:
        """返回不含服务器本地路径的可序列化引用。"""

        return asdict(self)


class ArtifactStore:
    """仅上传当前 attempt output 中白名单文件并登记数据库。"""

    def __init__(self, oss_client: OssClient) -> None:
        """绑定一个不会泄漏供应商细节的 OSS client。"""

        self.oss_client = oss_client

    def upload(
        self,
        *,
        workspace: CoreTaskWorkspace,
        local_path: str | Path,
        core_task_id: str,
        attempt_no: int,
        kind: str,
        content_type: str | None = None,
    ) -> ArtifactRef:
        """校验路径、流式摘要并以不可覆盖对象键上传。"""

        path = Path(local_path)
        output = workspace.validate_directory(workspace.output_dir)
        if path.parent != output or not kind:
            raise ArtifactSecurityError("ARTIFACT_PATH_REJECTED")
        extension = normalize_extension(path.suffix)
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        try:
            directory_fd = workspace.open_area_fd("output")
            descriptor = os.open(path.name, flags, dir_fd=directory_fd)
            os.close(directory_fd)
        except (OSError, WorkspaceSecurityError) as exc:
            try:
                os.close(directory_fd)
            except (OSError, UnboundLocalError):
                pass
            raise ArtifactSecurityError("ARTIFACT_NOT_FOUND") from exc
        try:
            file_stat = os.fstat(descriptor)
            if not stat.S_ISREG(file_stat.st_mode) or file_stat.st_size <= 0:
                raise ArtifactSecurityError("ARTIFACT_PATH_REJECTED")
            size = file_stat.st_size
            checksum = hashlib.sha256()
            with os.fdopen(descriptor, "rb", closefd=True) as handle:
                descriptor = -1
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    checksum.update(chunk)
                handle.seek(0)
                artifact_id = new_time_ordered_id("art_")
                seed = f"{core_task_id}:{attempt_no}:{artifact_id}:{secrets.token_hex(16)}"
                object_key = build_object_key(
                    now=datetime.now(timezone.utc).date(), extension=extension, seed=seed
                )
                media_type = (
                    content_type
                    or mimetypes.guess_type(path.name)[0]
                    or "application/octet-stream"
                )
                uploaded = self.oss_client.upload_stream(
                    handle,
                    object_key,
                    content_type=media_type,
                    size=size,
                )
        finally:
            if descriptor >= 0:
                os.close(descriptor)
        if uploaded.object_key != object_key:
            raise ArtifactSecurityError("ARTIFACT_KEY_MISMATCH")
        reference = ArtifactRef(
            artifact_id=artifact_id,
            kind=kind,
            bucket=uploaded.bucket,
            object_key=uploaded.object_key,
            url=uploaded.url,
            content_type=media_type,
            size=size,
            checksum=f"sha256:{checksum.hexdigest()}",
        )
        return reference
