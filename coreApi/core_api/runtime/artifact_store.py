from __future__ import annotations

import hashlib
import mimetypes
import os
import secrets
import stat
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from core_api.ids import new_time_ordered_id
from core_api.infrastructure.oss_client import (
    CdnUrlPolicy,
    OssClient,
    build_object_key,
    normalize_extension,
)
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

    def __init__(
        self,
        oss_client: OssClient,
        public_url_policy: CdnUrlPolicy | None = None,
        *,
        upload_protection_seconds: float = 300.0,
    ) -> None:
        """绑定一个不会泄漏供应商细节的 OSS client。"""

        self.oss_client = oss_client
        if public_url_policy is None:
            host = urlsplit(str(getattr(oss_client, "public_base_url", ""))).hostname
            if (
                not host
                or host.lower() == "localhost"
                or host.lower().endswith((".localhost", ".local", ".internal"))
            ):
                raise ValueError("ArtifactStore 必须配置公开 CDN URL 策略")
            public_url_policy = CdnUrlPolicy({host}, prefix="/narrato/coreApi/")
        self.public_url_policy = public_url_policy
        if not 30 <= upload_protection_seconds <= 3600:
            raise ValueError("ArtifactStore 上传保护租约必须在 [30, 3600] 秒")
        self.upload_protection_seconds = upload_protection_seconds

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
                seed = (
                    f"{core_task_id}:{attempt_no}:{artifact_id}:{secrets.token_hex(16)}"
                )
                object_key = build_object_key(
                    now=datetime.now(timezone.utc).date(),
                    extension=extension,
                    seed=seed,
                )
                media_type = (
                    content_type
                    or mimetypes.guess_type(path.name)[0]
                    or "application/octet-stream"
                )
                digest = f"sha256:{checksum.hexdigest()}"
                # Local import avoids a module cycle while making the journal a
                # mandatory write-ahead boundary for every adapter using this store.
                from core_api.tasks.artifact_reconciliation import (
                    ArtifactReconciliationJournal,
                )

                journal = ArtifactReconciliationJournal(workspace.base_dir)
                intent_name = journal.record_intent(
                    core_task_id,
                    attempt_no,
                    artifact_id=artifact_id,
                    kind=kind,
                    object_key=object_key,
                    content_type=media_type,
                    size=size,
                    checksum=digest,
                    upload_protection_seconds=self.upload_protection_seconds,
                )
                stopped = threading.Event()

                def heartbeat_intent() -> None:
                    interval = min(30.0, self.upload_protection_seconds / 3)
                    while not stopped.wait(interval):
                        if not journal.heartbeat_upload(
                            intent_name,
                            protection_seconds=self.upload_protection_seconds,
                        ):
                            return

                heartbeat = threading.Thread(target=heartbeat_intent)
                heartbeat.start()
                try:
                    # Synchronous ownership is intentional: return/raise is
                    # impossible while a detached PUT continues in this process.
                    uploaded = self.oss_client.upload_stream(
                        handle,
                        object_key,
                        content_type=media_type,
                        size=size,
                    )
                finally:
                    stopped.set()
                    heartbeat.join()
        finally:
            if descriptor >= 0:
                os.close(descriptor)
        if uploaded.object_key != object_key:
            delete = getattr(self.oss_client, "delete_object", None)
            if callable(delete):
                try:
                    delete(uploaded.object_key)
                except Exception:
                    pass
            raise ArtifactSecurityError("ARTIFACT_KEY_MISMATCH")
        try:
            validated_url = self.public_url_policy.validate(uploaded.url)
            parsed_validated = urlsplit(validated_url)
            if parsed_validated.query or parsed_validated.path != f"/{object_key}":
                raise ValueError("Artifact URL 禁止 query")
        except Exception:
            delete = getattr(self.oss_client, "delete_object", None)
            if callable(delete):
                try:
                    delete(uploaded.object_key)
                except Exception:
                    pass
            raise ArtifactSecurityError("ARTIFACT_URL_REJECTED")
        reference = ArtifactRef(
            artifact_id=artifact_id,
            kind=kind,
            bucket=uploaded.bucket,
            object_key=uploaded.object_key,
            url=validated_url,
            content_type=media_type,
            size=size,
            checksum=digest,
        )
        updated = journal.update_reference(
            intent_name,
            reference,
            task_id=core_task_id,
            attempt_no=attempt_no,
        )
        if updated is None:
            journal.ensure_cleanup_tombstone(core_task_id, attempt_no, reference)
            try:
                self.oss_client.delete_object(reference.object_key)
            except BaseException:
                raise
            raise ArtifactSecurityError("ARTIFACT_UPLOAD_RECONCILED")
        return reference

    def compensate(self, artifacts: list[ArtifactRef]) -> None:
        """尽力删除当前失败 attempt 已上传但尚未登记的对象。"""
        delete = getattr(self.oss_client, "delete_object", None)
        if not callable(delete):
            return
        for artifact in reversed(artifacts):
            try:
                delete(artifact.object_key)
            except Exception:
                # 原始执行错误优先；扫描清理可根据 attempt/object key 后续补偿。
                continue

    def delete_reconciled_artifact(self, artifact: ArtifactRef) -> None:
        """Delete one journaled object and surface OSS failure for durable retry."""
        if not artifact.object_key.startswith(
            "narrato/coreApi/"
        ) or ".." in artifact.object_key.split("/"):
            raise ArtifactSecurityError("ARTIFACT_OBJECT_KEY_REJECTED")
        delete = getattr(self.oss_client, "delete_object", None)
        if not callable(delete):
            raise ArtifactSecurityError("ARTIFACT_DELETE_UNAVAILABLE")
        delete(artifact.object_key)

    def is_reconciled_artifact_absent(self, artifact: ArtifactRef) -> bool:
        """Use provider HEAD when available; otherwise retain tombstone forever."""
        exists = getattr(self.oss_client, "object_exists", None)
        if not callable(exists):
            return False
        return not bool(exists(artifact.object_key))
