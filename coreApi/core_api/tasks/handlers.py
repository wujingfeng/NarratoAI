from __future__ import annotations

from pathlib import Path
import threading
from datetime import datetime
from collections.abc import Callable

from core_api.adapters.narrato.asr import AsrAdapter
from core_api.adapters.narrato.media_probe import AdapterError, MediaProbeAdapter
from core_api.adapters.narrato.short_drama import ShortDramaAdapter
from core_api.infrastructure.oss_client import InfrastructureError
from core_api.runtime.artifact_store import ArtifactSecurityError
from core_api.runtime.workspace import CoreTaskWorkspace
from core_api.tasks.models import CoreTaskStatus
from core_api.tasks.service import (
    InvalidTaskTransitionError,
    StaleLeaseError,
    TaskService,
)


HeartbeatOnce = Callable[[str, str, int, float], None]


class HeartbeatPump:
    """在独立 Session callback 中周期续租并提供副作用前 fencing。"""

    def __init__(
        self,
        *,
        attempt_id: str,
        lease_token: str,
        lease_version: int,
        lease_seconds: float,
        interval_seconds: float,
        heartbeat_once: HeartbeatOnce,
    ) -> None:
        self.attempt_id = attempt_id
        self.lease_token = lease_token
        self.lease_version = lease_version
        self.lease_seconds = lease_seconds
        self.interval_seconds = interval_seconds
        self.heartbeat_once = heartbeat_once
        self._stopped = threading.Event()
        self._failure: BaseException | None = None
        self._thread = threading.Thread(target=self._loop, daemon=True)

    def __enter__(self) -> HeartbeatPump:
        """启动周期 heartbeat。"""

        self._thread.start()
        return self

    def __exit__(self, *_args) -> None:
        """停止 heartbeat 并有界等待线程退出。"""

        self._stopped.set()
        self._thread.join(timeout=max(1.0, self.interval_seconds * 2))

    def _loop(self) -> None:
        while not self._stopped.wait(self.interval_seconds):
            try:
                self.heartbeat_once(
                    self.attempt_id,
                    self.lease_token,
                    self.lease_version,
                    self.lease_seconds,
                )
            except BaseException as exc:
                self._failure = exc
                self._stopped.set()
                return

    def guard(self) -> None:
        """副作用前同步确认 current token/version 仍可续租。"""

        if self._failure is not None:
            raise StaleLeaseError("STALE_LEASE") from self._failure
        try:
            self.heartbeat_once(
                self.attempt_id,
                self.lease_token,
                self.lease_version,
                self.lease_seconds,
            )
        except BaseException as exc:
            self._failure = exc
            raise StaleLeaseError("STALE_LEASE") from exc


class AtomicTaskHandler:
    """使用持久租约执行 media_probe/asr 原子任务。"""

    def __init__(
        self,
        *,
        task_service: TaskService,
        work_root: str | Path,
        media_probe_adapter: MediaProbeAdapter | None = None,
        asr_adapter: AsrAdapter | None = None,
        short_drama_adapter: ShortDramaAdapter | None = None,
        lease_seconds: float = 900,
        heartbeat_once: HeartbeatOnce | None = None,
        heartbeat_interval_seconds: float | None = None,
    ) -> None:
        self.task_service = task_service
        self.work_root = Path(work_root)
        self.media_probe_adapter = media_probe_adapter
        self.asr_adapter = asr_adapter
        self.short_drama_adapter = short_drama_adapter
        self.lease_seconds = lease_seconds
        self.heartbeat_once = heartbeat_once
        self.heartbeat_interval_seconds = heartbeat_interval_seconds or min(
            30.0, lease_seconds / 3
        )

    def run(
        self,
        task_id: str,
        *,
        expected_state_version: int | None = None,
        not_before: datetime | None = None,
        dispatch_id: str | None = None,
    ) -> None:
        """领取一个 attempt，按错误分类完成或进入自动恢复。"""

        task = self.task_service.get_task(task_id)
        if task.status not in {CoreTaskStatus.QUEUED, CoreTaskStatus.RETRY_WAIT}:
            # Celery 重复或迟到唤醒不得重复执行 current/terminal task。
            return
        try:
            attempt = self.task_service.claim_dispatched_task(
                task_id,
                expected_state_version=(
                    task.state_version
                    if expected_state_version is None
                    else expected_state_version
                ),
                not_before=not_before or task.updated_at,
                lease_seconds=self.lease_seconds,
            )
        except InvalidTaskTransitionError:
            return
        if attempt is None:
            return
        workspace = CoreTaskWorkspace.create(
            self.work_root, task.id, attempt.attempt_no
        )

        def heartbeat_once(
            attempt_id: str, token: str, version: int, lease_seconds: float
        ) -> None:
            """选择生产独立 Session callback 或当前测试 TaskService。"""

            if self.heartbeat_once is not None:
                self.heartbeat_once(attempt_id, token, version, lease_seconds)
            else:
                self.task_service.heartbeat(
                    attempt_id,
                    token,
                    version,
                    lease_seconds=lease_seconds,
                )

        self.task_service.heartbeat(
            attempt.id,
            attempt.lease_token,
            attempt.lease_version,
            lease_seconds=self.lease_seconds,
        )
        pump = HeartbeatPump(
            attempt_id=attempt.id,
            lease_token=attempt.lease_token,
            lease_version=attempt.lease_version,
            lease_seconds=self.lease_seconds,
            interval_seconds=self.heartbeat_interval_seconds,
            heartbeat_once=heartbeat_once,
        )
        if task.task_type in {"video_analysis", "script_generation"}:
            self.task_service.update_attempt_progress(
                attempt.id,
                attempt.lease_token,
                attempt.lease_version,
                phase=(
                    "analysis"
                    if task.task_type == "video_analysis"
                    else "script_generation"
                ),
                progress=10,
            )
        try:
            with pump:
                if (
                    task.task_type == "media_probe"
                    and self.media_probe_adapter is not None
                ):
                    result = self.media_probe_adapter.run(
                        workspace=workspace, **task.input_snapshot
                    )
                elif task.task_type == "asr" and self.asr_adapter is not None:
                    result = self.asr_adapter.run(
                        workspace=workspace,
                        core_task_id=task.id,
                        attempt_no=attempt.attempt_no,
                        lease_guard=pump.guard,
                        **task.input_snapshot,
                    )
                elif (
                    task.task_type == "video_analysis"
                    and self.short_drama_adapter is not None
                ):
                    result = self.short_drama_adapter.run_analysis(
                        workspace=workspace,
                        core_task_id=task.id,
                        attempt_no=attempt.attempt_no,
                        lease_guard=pump.guard,
                        **task.input_snapshot,
                    )
                elif (
                    task.task_type == "script_generation"
                    and self.short_drama_adapter is not None
                ):
                    result = self.short_drama_adapter.run_script_generation(
                        workspace=workspace,
                        core_task_id=task.id,
                        attempt_no=attempt.attempt_no,
                        lease_guard=pump.guard,
                        **task.input_snapshot,
                    )
                else:
                    raise AdapterError("TASK_HANDLER_UNAVAILABLE")
                pump.guard()
            self.task_service.complete_attempt(
                attempt.id,
                attempt.lease_token,
                result,
                lease_version=attempt.lease_version,
            )
        except (InfrastructureError, AdapterError, ArtifactSecurityError) as exc:
            code = getattr(exc, "code", "ATOMIC_TASK_FAILED")
            retryable = bool(getattr(exc, "retryable", False))
            self.task_service.fail_attempt(
                attempt.id,
                attempt.lease_token,
                {"code": code},
                retryable=retryable,
                lease_version=attempt.lease_version,
            )
