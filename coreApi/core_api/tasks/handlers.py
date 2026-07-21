from __future__ import annotations

from pathlib import Path
import threading
from datetime import datetime
from collections.abc import Callable

from core_api.adapters.narrato.asr import AsrAdapter
from core_api.adapters.narrato.media_probe import AdapterError, MediaProbeAdapter
from core_api.adapters.narrato.short_drama import ShortDramaAdapter
from core_api.adapters.narrato.render import RenderAdapter
from core_api.adapters.narrato.tts import TtsAdapter
from core_api.infrastructure.oss_client import InfrastructureError
from core_api.runtime.artifact_store import ArtifactRef, ArtifactSecurityError
from core_api.runtime.workspace import CoreTaskWorkspace
from core_api.tasks.models import CoreTaskStatus
from core_api.tasks.callbacks import OutboxEventConflictError
from core_api.tasks.artifact_reconciliation import (
    ArtifactReconciliationJournal,
    ArtifactReconciliationScanner,
)
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
        tts_adapter: TtsAdapter | None = None,
        render_adapter: RenderAdapter | None = None,
        lease_seconds: float = 900,
        heartbeat_once: HeartbeatOnce | None = None,
        heartbeat_interval_seconds: float | None = None,
        reconciliation_store=None,
    ) -> None:
        self.task_service = task_service
        self.work_root = Path(work_root)
        self.work_root.mkdir(parents=True, exist_ok=True)
        self.media_probe_adapter = media_probe_adapter
        self.asr_adapter = asr_adapter
        self.short_drama_adapter = short_drama_adapter
        self.tts_adapter = tts_adapter
        self.render_adapter = render_adapter
        self.lease_seconds = lease_seconds
        self.heartbeat_once = heartbeat_once
        self.heartbeat_interval_seconds = heartbeat_interval_seconds or min(
            30.0, lease_seconds / 3
        )
        self.reconciliation_store = reconciliation_store
        self.reconciliation_journal = ArtifactReconciliationJournal(self.work_root)

    def _record_pending_reconciliation(
        self,
        task_id: str,
        attempt_no: int,
        result: object,
        *,
        known_orphan: bool = False,
    ) -> None:
        """原子持久化提交结果未知时待数据库恢复确认的 OSS 引用。"""
        references = self._artifact_references(result)
        if references:
            aggregate = self.reconciliation_journal.record(
                task_id, attempt_no, references, known_orphan=known_orphan
            )
            self.reconciliation_journal.discard_artifacts(
                task_id, attempt_no, references, exclude={aggregate}
            )

    def reconcile_pending_artifacts(self) -> int:
        """扫描持久补偿事实；DB 成功事实保留对象，否则幂等删除孤儿。"""
        return ArtifactReconciliationScanner(
            self.task_service.session,
            self.reconciliation_journal,
            self._artifact_store(),
        ).scan()

    @staticmethod
    def _artifact_references(result: object) -> list[ArtifactRef]:
        references: list[ArtifactRef] = []
        if not isinstance(result, dict):
            return references
        for item in result.get("artifacts", []):
            if isinstance(item, dict):
                try:
                    references.append(ArtifactRef(**item))
                except (TypeError, ValueError):
                    continue
        return references

    def _artifact_store(self):
        if self.reconciliation_store is not None:
            return self.reconciliation_store
        for adapter in (
            self.asr_adapter,
            self.short_drama_adapter,
            self.tts_adapter,
            self.render_adapter,
        ):
            store = getattr(adapter, "artifact_store", None)
            if store is not None:
                return store
        return None

    def _compensate_result(
        self,
        result: object,
        *,
        task_id: str | None = None,
        attempt_no: int | None = None,
    ) -> bool:
        """删除终态事务未提交时当前 attempt 已上传的对象。"""
        store = self._artifact_store()
        references = self._artifact_references(result)
        if store is None or not references:
            return False
        try:
            for reference in reversed(references):
                store.delete_reconciled_artifact(reference)
            if task_id is not None and attempt_no is not None:
                self.reconciliation_journal.discard_artifacts(
                    task_id, attempt_no, references
                )
            return True
        except BaseException:
            return False

    def run(
        self,
        task_id: str,
        *,
        expected_state_version: int | None = None,
        not_before: datetime | None = None,
        dispatch_id: str | None = None,
    ) -> None:
        """领取一个 attempt，按错误分类完成或进入自动恢复。"""

        self.reconcile_pending_artifacts()
        task = self.task_service.get_task(task_id)
        if task.status not in {CoreTaskStatus.QUEUED, CoreTaskStatus.RETRY_WAIT}:
            # Celery 重复或迟到唤醒不得重复执行 current/terminal task。
            return
        result: dict[str, object] | None = None
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
        if task.task_type in {
            "video_analysis",
            "script_generation",
            "tts",
            "subtitle",
            "video_render",
        }:
            self.task_service.update_attempt_progress(
                attempt.id,
                attempt.lease_token,
                attempt.lease_version,
                phase=(
                    "analysis"
                    if task.task_type == "video_analysis"
                    else (
                        "script_generation"
                        if task.task_type == "script_generation"
                        else task.task_type
                    )
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
                elif task.task_type == "tts" and self.tts_adapter is not None:
                    result = self.tts_adapter.run(
                        workspace=workspace,
                        core_task_id=task.id,
                        attempt_no=attempt.attempt_no,
                        lease_guard=pump.guard,
                        **task.input_snapshot,
                    )
                elif (
                    task.task_type == "video_render" and self.render_adapter is not None
                ):
                    result = self.render_adapter.run(
                        workspace=workspace,
                        core_task_id=task.id,
                        attempt_no=attempt.attempt_no,
                        lease_guard=pump.guard,
                        **task.input_snapshot,
                    )
                elif task.task_type == "subtitle" and self.render_adapter is not None:
                    result = self.render_adapter.run_subtitle(
                        workspace=workspace,
                        core_task_id=task.id,
                        attempt_no=attempt.attempt_no,
                        lease_guard=pump.guard,
                        **task.input_snapshot,
                    )
                else:
                    raise AdapterError("TASK_HANDLER_UNAVAILABLE")
                pump.guard()
            try:
                self.task_service.complete_attempt(
                    attempt.id,
                    attempt.lease_token,
                    result,
                    lease_version=attempt.lease_version,
                )
            except BaseException as completion_error:
                if isinstance(completion_error, OutboxEventConflictError):
                    if not self._compensate_result(
                        result, task_id=task.id, attempt_no=attempt.attempt_no
                    ):
                        self._record_pending_reconciliation(
                            task.id,
                            attempt.attempt_no,
                            result,
                            known_orphan=True,
                        )
                    raise
                committed: bool | None = None
                try:
                    observed = self.task_service.get_task(task.id)
                    committed = observed.status == CoreTaskStatus.SUCCEEDED
                except BaseException:
                    # COMMIT may have succeeded while its acknowledgement and the
                    # confirmation read both failed.  Unknown is not rolled back:
                    # preserving objects lets the task/artifact reconciliation path
                    # repair the durable state without creating broken CDN records.
                    committed = None
                if committed is False:
                    if not self._compensate_result(
                        result, task_id=task.id, attempt_no=attempt.attempt_no
                    ):
                        self._record_pending_reconciliation(
                            task.id,
                            attempt.attempt_no,
                            result,
                            known_orphan=True,
                        )
                elif committed is None:
                    self._record_pending_reconciliation(
                        task.id, attempt.attempt_no, result
                    )
                raise
        except StaleLeaseError:
            return
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
