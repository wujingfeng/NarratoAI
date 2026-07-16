from __future__ import annotations

import hashlib
import json
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from core_api.ids import new_time_ordered_id
from core_api.tasks.callbacks import OutboxEventConflictError, enqueue_state_callback
from core_api.tasks.dispatch import enqueue_task_dispatch
from core_api.tasks.models import (
    AttemptStatus,
    CoreTask,
    CoreTaskAttempt,
    CoreTaskStatus,
    CoreArtifact,
    utc_now,
)
from core_api.tasks.state_machine import can_transition


class TaskRuntimeError(RuntimeError):
    """Core Task 运行时稳定错误的基类。"""


class TaskNotFoundError(TaskRuntimeError):
    """Core Task 或 attempt 不存在。"""


class IdempotencyConflictError(TaskRuntimeError):
    """同一幂等作用域收到不同请求体。"""


class InvalidTaskTransitionError(TaskRuntimeError):
    """Core Task 状态迁移不合法。"""


class StaleLeaseError(TaskRuntimeError):
    """Worker 提交了无效、过期或已被替代的租约。"""


class LeaseStillActiveError(TaskRuntimeError):
    """调度器试图提前替换仍有效的租约。"""


@dataclass(frozen=True, slots=True)
class TaskCreation:
    """幂等创建返回的任务及本调用是否赢得创建。"""

    task: CoreTask
    created: bool


def _utc(value: datetime) -> datetime:
    """将 SQLite 返回的朴素时间恢复为 UTC 时间。"""

    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _digest_payload(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class TaskService:
    """在显式数据库事务中维护 Core Task 事实状态。"""

    def __init__(self, session: Session) -> None:
        self.session = session

    def get_task(self, task_id: str) -> CoreTask:
        """读取 Core Task，不存在时抛稳定错误。"""

        task = self.session.get(CoreTask, task_id)
        if task is None:
            raise TaskNotFoundError("CORE_TASK_NOT_FOUND")
        return task

    def find_idempotent_task(
        self,
        *,
        caller: str,
        route: str,
        idempotency_key: str,
        idempotency_payload: dict[str, Any],
    ) -> CoreTask | None:
        """按公开请求摘要查找首次任务；异体 Key 立即冲突。"""

        scope = f"{caller}\x1f{route}\x1f{idempotency_key}"
        digest = _digest_payload(idempotency_payload)
        existing = self.session.scalar(
            select(CoreTask).where(CoreTask.idempotency_scope == scope)
        )
        if existing is not None and existing.request_digest != digest:
            raise IdempotencyConflictError("IDEMPOTENCY_CONFLICT")
        return existing

    def create_core_task(
        self,
        *,
        caller: str,
        route: str,
        task_type: str,
        idempotency_key: str,
        input_snapshot: dict[str, Any],
        caller_task_id: str | None = None,
        max_retries: int = 3,
        idempotency_payload: dict[str, Any] | None = None,
    ) -> CoreTask:
        """按调用方、路径和 Key 幂等创建不可变 Core Task。"""

        return self.create_core_task_result(
            caller=caller,
            route=route,
            task_type=task_type,
            idempotency_key=idempotency_key,
            input_snapshot=input_snapshot,
            caller_task_id=caller_task_id,
            max_retries=max_retries,
            idempotency_payload=idempotency_payload,
        ).task

    def create_core_task_result(
        self,
        *,
        caller: str,
        route: str,
        task_type: str,
        idempotency_key: str,
        input_snapshot: dict[str, Any],
        caller_task_id: str | None = None,
        max_retries: int = 3,
        idempotency_payload: dict[str, Any] | None = None,
    ) -> TaskCreation:
        """幂等创建任务，并告诉路由是否需要进行首次 Celery 唤醒。"""

        if max_retries < 0:
            raise ValueError("max_retries 不能小于零")
        scope = f"{caller}\x1f{route}\x1f{idempotency_key}"
        # caller_task_id 来自同一公开请求体，也必须参与“同 Key + 同请求”判定。
        digest = _digest_payload(
            idempotency_payload
            if idempotency_payload is not None
            else {"input_snapshot": input_snapshot, "caller_task_id": caller_task_id}
        )
        existing = self.session.scalar(
            select(CoreTask).where(CoreTask.idempotency_scope == scope)
        )
        if existing is not None:
            if existing.request_digest != digest:
                raise IdempotencyConflictError("IDEMPOTENCY_CONFLICT")
            return TaskCreation(existing, False)
        task = CoreTask(
            id=new_time_ordered_id("ctask_"),
            task_type=task_type,
            caller=caller,
            caller_task_id=caller_task_id,
            idempotency_scope=scope,
            idempotency_key=idempotency_key,
            request_digest=digest,
            # JSON round-trip 防止调用方随后修改原 dict 影响不可变快照。
            input_snapshot=json.loads(json.dumps(input_snapshot)),
            initial_response={},
            max_retries=max_retries,
        )
        task.initial_response = {"core_task_id": task.id, "status": "queued"}
        # 唯一约束是并发幂等的最终裁决；savepoint 让 loser 可恢复并回读 winner。
        self.session.commit()
        try:
            with self.session.begin_nested():
                self.session.add(task)
                self.session.flush()
                enqueue_task_dispatch(self.session, task)
                self.session.flush()
        except IntegrityError as exc:
            self.session.expire_all()
            winner = self.session.scalar(
                select(CoreTask).where(CoreTask.idempotency_scope == scope)
            )
            if winner is None:
                self.session.rollback()
                raise
            self.session.commit()
            if winner.request_digest != digest:
                raise IdempotencyConflictError("IDEMPOTENCY_CONFLICT") from exc
            return TaskCreation(winner, False)
        self.session.commit()
        return TaskCreation(task, True)

    def start_attempt(
        self, task_id: str, *, lease_seconds: float = 60
    ) -> CoreTaskAttempt:
        """从 queued/retry_wait 原子领取任务并创建 current attempt。"""

        return self.acquire_lease(task_id, lease_seconds=lease_seconds)

    def acquire_lease(
        self, task_id: str, *, lease_seconds: float = 60
    ) -> CoreTaskAttempt:
        """领取任务，生成高熵 token 和单调租约版本。"""

        if lease_seconds <= 0:
            raise ValueError("lease_seconds 必须大于零")
        task = self.session.scalar(select(CoreTask).where(CoreTask.id == task_id))
        if task is None:
            raise TaskNotFoundError("CORE_TASK_NOT_FOUND")
        attempt = self.claim_dispatched_task(
            task_id,
            expected_state_version=task.state_version,
            not_before=utc_now(),
            lease_seconds=lease_seconds,
        )
        if attempt is None:
            raise InvalidTaskTransitionError("CORE_TASK_NOT_CLAIMABLE")
        return attempt

    def claim_dispatched_task(
        self,
        task_id: str,
        *,
        expected_state_version: int,
        not_before: datetime,
        now: datetime | None = None,
        lease_seconds: float = 60,
    ) -> CoreTaskAttempt | None:
        """按 wake 版本与到期时间原子领取；迟到、重复和并发 loser 均忽略。"""

        if lease_seconds <= 0:
            raise ValueError("lease_seconds 必须大于零")
        observed_at = _utc(now) if now is not None else utc_now()
        if _utc(not_before) > observed_at:
            return None
        result = self.session.execute(
            update(CoreTask)
            .where(
                CoreTask.id == task_id,
                CoreTask.state_version == expected_state_version,
                CoreTask.status.in_((CoreTaskStatus.QUEUED, CoreTaskStatus.RETRY_WAIT)),
            )
            .values(
                status=CoreTaskStatus.RUNNING,
                state_version=CoreTask.state_version + 1,
                current_attempt_no=CoreTask.current_attempt_no + 1,
                started_at=func.coalesce(CoreTask.started_at, observed_at),
                updated_at=observed_at,
            )
            .execution_options(synchronize_session=False)
        )
        if result.rowcount != 1:
            self.session.commit()
            self.session.expire_all()
            return None
        self.session.expire_all()
        task = self.session.scalar(
            select(CoreTask)
            .where(CoreTask.id == task_id)
            .execution_options(populate_existing=True)
        )
        if task is None:
            self.session.rollback()
            raise TaskNotFoundError("CORE_TASK_NOT_FOUND")
        attempt = CoreTaskAttempt(
            id=new_time_ordered_id("attempt_"),
            core_task_id=task.id,
            attempt_no=task.current_attempt_no,
            status=AttemptStatus.RUNNING,
            lease_token=secrets.token_urlsafe(32),
            lease_version=task.current_attempt_no,
            heartbeat_at=observed_at,
            lease_expires_at=observed_at + timedelta(seconds=lease_seconds),
            started_at=observed_at,
        )
        try:
            self.session.add(attempt)
            enqueue_state_callback(
                self.session,
                task,
                event_id=f"evt_{task.id}_{task.state_version}",
            )
            self.session.commit()
        except IntegrityError:
            # PostgreSQL/SQLite 唯一约束是并发领取的最后防线。
            self.session.rollback()
            self.session.expire_all()
            return None
        return attempt

    def heartbeat(
        self,
        attempt_id: str,
        lease_token: str,
        lease_version: int,
        *,
        lease_seconds: float = 60,
    ) -> CoreTaskAttempt:
        """仅为合法 current attempt 续租。"""

        if lease_seconds <= 0:
            raise ValueError("lease_seconds 必须大于零")
        attempt, task = self._locked_attempt_and_task(attempt_id)
        now = utc_now()
        if not self._valid_current_lease(
            task, attempt, lease_token, lease_version, now=now
        ):
            raise StaleLeaseError("STALE_LEASE")
        attempt.heartbeat_at = now
        attempt.lease_expires_at = now + timedelta(seconds=lease_seconds)
        self.session.commit()
        return attempt

    def expire_and_restart(
        self,
        attempt_id: str,
        *,
        lease_seconds: float = 60,
        heartbeat_timeout_seconds: float = 60,
        now: datetime | None = None,
        retry_delay_seconds: float | None = None,
    ) -> CoreTaskAttempt | None:
        """确认租约或心跳超时后，使 current attempt 失效并恢复。"""

        if lease_seconds <= 0:
            raise ValueError("lease_seconds 必须大于零")
        if heartbeat_timeout_seconds <= 0:
            raise ValueError("heartbeat_timeout_seconds 必须大于零")
        attempt, task = self._locked_attempt_and_task(attempt_id)
        if (
            task.status != CoreTaskStatus.RUNNING
            or attempt.status != AttemptStatus.RUNNING
            or task.current_attempt_no != attempt.attempt_no
        ):
            raise StaleLeaseError("STALE_LEASE")
        observed_at = _utc(now) if now is not None else utc_now()
        lease_expired = _utc(attempt.lease_expires_at) <= observed_at
        heartbeat_expired = _utc(attempt.heartbeat_at) <= observed_at - timedelta(
            seconds=heartbeat_timeout_seconds
        )
        if not lease_expired and not heartbeat_expired:
            raise LeaseStillActiveError("LEASE_STILL_ACTIVE")
        return self._restart_locked_attempt(
            attempt,
            task,
            now=observed_at,
            retry_delay_seconds=retry_delay_seconds,
        )

    def _restart_locked_attempt(
        self,
        attempt: CoreTaskAttempt,
        task: CoreTask,
        *,
        now: datetime,
        retry_delay_seconds: float | None,
    ) -> CoreTaskAttempt | None:
        """在调用方已持有 current task/attempt 行锁时执行原子恢复。"""

        attempt.status = AttemptStatus.EXPIRED
        attempt.finished_at = now
        if attempt.error is None:
            attempt.error = {"code": "LEASE_EXPIRED", "retryable": True}

        # max_retries 表示初次执行之外的自动重试次数，默认总计最多四次。
        retries_used = task.current_attempt_no - 1
        if retries_used >= task.max_retries:
            task.error = {"code": "RETRY_EXHAUSTED", "retryable": False}
            task.finished_at = now
            self._transition(task, CoreTaskStatus.FAILED)
            enqueue_state_callback(
                self.session,
                task,
                event_id=f"evt_{task.id}_{task.state_version}",
            )
            self.session.commit()
            return None

        self._transition(task, CoreTaskStatus.RETRY_WAIT)
        enqueue_state_callback(
            self.session,
            task,
            event_id=f"evt_{task.id}_{task.state_version}",
        )
        retries_used = attempt.attempt_no - 1
        if retry_delay_seconds is None:
            retry_delay_seconds = min(300.0, 5.0 * (2**retries_used))
        enqueue_task_dispatch(
            self.session,
            task,
            available_at=now + timedelta(seconds=retry_delay_seconds),
        )
        self.session.commit()
        return None

    def update_attempt_progress(
        self,
        attempt_id: str,
        lease_token: str,
        lease_version: int,
        *,
        phase: str,
        progress: int,
    ) -> CoreTask:
        """仅由 current attempt 更新规范化阶段和未完成进度。"""

        if not phase or not 0 <= progress < 100:
            raise ValueError("phase/progress 无效")
        attempt, task = self._locked_attempt_and_task(attempt_id)
        if not self._valid_current_lease(
            task, attempt, lease_token, lease_version, now=utc_now()
        ):
            raise StaleLeaseError("STALE_LEASE")
        task.phase = phase
        task.progress = progress
        task.updated_at = utc_now()
        self.session.commit()
        return task

    def complete_attempt(
        self,
        attempt_id: str,
        lease_token: str,
        result: list[dict[str, Any]] | dict[str, Any],
        *,
        lease_version: int,
        event_id: str | None = None,
    ) -> CoreTask:
        """仅允许 current 租约完成任务，迟到结果持久审计后拒绝。"""

        attempt, task = self._locked_attempt_and_task(attempt_id)
        now = utc_now()
        if not self._valid_current_lease(
            task, attempt, lease_token, lease_version, now=now
        ):
            # 审计只保存摘要，避免把完整供应商结果或敏感内容落入错误记录。
            attempt.late_result_audit = {
                "outcome": "rejected_stale",
                "received_at": now.isoformat(),
                "result_digest": _digest_payload({"result": result}),
                "supplied_lease_version": lease_version,
            }
            self.session.commit()
            raise StaleLeaseError("STALE_LEASE")

        attempt.status = AttemptStatus.SUCCEEDED
        attempt.finished_at = now
        task.result = result
        self._register_result_artifacts(task, attempt, result)
        task.error = None
        task.progress = 100
        task.finished_at = now
        self._transition(task, CoreTaskStatus.SUCCEEDED)
        try:
            enqueue_state_callback(
                self.session,
                task,
                event_id=event_id or f"evt_{task.id}_{task.state_version}",
            )
            self.session.flush()
        except OutboxEventConflictError:
            # 状态与 Outbox 必须同事务；事件冲突时回滚 attempt 与 task 终态。
            self.session.rollback()
            raise
        except IntegrityError as exc:
            self.session.rollback()
            raise OutboxEventConflictError("OUTBOX_EVENT_CONFLICT") from exc
        self.session.commit()
        return task

    def _register_result_artifacts(
        self,
        task: CoreTask,
        attempt: CoreTaskAttempt,
        result: list[dict[str, Any]] | dict[str, Any],
    ) -> None:
        """在合法租约终态事务中登记统一 Artifact DTO。"""

        if not isinstance(result, dict):
            return
        raw_artifacts = result.get("artifacts", [])
        if not isinstance(raw_artifacts, list):
            raise ValueError("artifacts 必须是数组")
        for item in raw_artifacts:
            if not isinstance(item, dict):
                raise ValueError("artifact 必须是对象")
            self.session.add(
                CoreArtifact(
                    id=str(item["artifact_id"]),
                    core_task_id=task.id,
                    attempt_no=attempt.attempt_no,
                    kind=str(item["kind"]),
                    bucket=str(item["bucket"]),
                    object_key=str(item["object_key"]),
                    url=str(item["url"]),
                    content_type=str(item["content_type"]),
                    size=int(item["size"]),
                    checksum=str(item["checksum"]) if item.get("checksum") else None,
                )
            )

    def fail_attempt(
        self,
        attempt_id: str,
        lease_token: str,
        error: dict[str, Any],
        *,
        retryable: bool,
        lease_version: int,
        retry_delay_seconds: float | None = None,
    ) -> CoreTaskAttempt | None:
        """记录失败；确定性错误终止，临时错误按预算自动重试。"""

        attempt, task = self._locked_attempt_and_task(attempt_id)
        if not self._valid_current_lease(
            task, attempt, lease_token, lease_version, now=utc_now()
        ):
            raise StaleLeaseError("STALE_LEASE")
        attempt.error = {**error, "retryable": retryable}
        if retryable:
            return self._schedule_retry_locked(
                attempt,
                task,
                now=utc_now(),
                retry_delay_seconds=retry_delay_seconds,
            )
        now = utc_now()
        attempt.status = AttemptStatus.FAILED
        attempt.finished_at = now
        task.error = {**error, "retryable": False}
        task.finished_at = now
        self._transition(task, CoreTaskStatus.FAILED)
        enqueue_state_callback(
            self.session, task, event_id=f"evt_{task.id}_{task.state_version}"
        )
        self.session.commit()
        return None

    def _schedule_retry_locked(
        self,
        attempt: CoreTaskAttempt,
        task: CoreTask,
        *,
        now: datetime,
        retry_delay_seconds: float | None,
    ) -> None:
        """结束旧 attempt，并在 backoff 到期后可靠唤醒 retry_wait 任务。"""

        attempt.status = AttemptStatus.FAILED
        attempt.finished_at = now
        retries_used = attempt.attempt_no - 1
        if retries_used >= task.max_retries:
            task.error = {"code": "RETRY_EXHAUSTED", "retryable": False}
            task.finished_at = now
            self._transition(task, CoreTaskStatus.FAILED)
            enqueue_state_callback(
                self.session, task, event_id=f"evt_{task.id}_{task.state_version}"
            )
            self.session.commit()
            return None

        task.error = attempt.error
        self._transition(task, CoreTaskStatus.RETRY_WAIT)
        enqueue_state_callback(
            self.session, task, event_id=f"evt_{task.id}_{task.state_version}"
        )
        if retry_delay_seconds is None:
            exponential = min(300.0, 5.0 * (2**retries_used))
            retry_delay_seconds = exponential + secrets.randbelow(1000) / 1000
        if retry_delay_seconds < 0:
            raise ValueError("retry_delay_seconds 不能小于零")
        enqueue_task_dispatch(
            self.session,
            task,
            available_at=now + timedelta(seconds=retry_delay_seconds),
        )
        self.session.commit()
        return None

    def mark_succeeded(self, task_id: str, *, event_id: str) -> CoreTask:
        """幂等标记成功并保证终态回调只写一次。"""

        task = self.session.scalar(
            select(CoreTask).where(CoreTask.id == task_id).with_for_update()
        )
        if task is None:
            raise TaskNotFoundError("CORE_TASK_NOT_FOUND")
        if task.status == CoreTaskStatus.FAILED:
            raise InvalidTaskTransitionError("CORE_TASK_TERMINAL")
        if task.status != CoreTaskStatus.SUCCEEDED:
            task.progress = 100
            task.finished_at = utc_now()
            self._transition(task, CoreTaskStatus.SUCCEEDED)
        try:
            enqueue_state_callback(self.session, task, event_id=event_id)
            self.session.flush()
        except OutboxEventConflictError:
            # event_id 属于其他逻辑事件时，终态与版本增量一起回滚。
            self.session.rollback()
            raise
        except IntegrityError as exc:
            self.session.rollback()
            raise OutboxEventConflictError("OUTBOX_EVENT_CONFLICT") from exc
        self.session.commit()
        return task

    def _locked_attempt_and_task(
        self, attempt_id: str
    ) -> tuple[CoreTaskAttempt, CoreTask]:
        attempt = self.session.scalar(
            select(CoreTaskAttempt)
            .where(CoreTaskAttempt.id == attempt_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if attempt is None:
            raise TaskNotFoundError("CORE_ATTEMPT_NOT_FOUND")
        task = self.session.scalar(
            select(CoreTask)
            .where(CoreTask.id == attempt.core_task_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if task is None:
            raise TaskNotFoundError("CORE_TASK_NOT_FOUND")
        return attempt, task

    @staticmethod
    def _valid_current_lease(
        task: CoreTask,
        attempt: CoreTaskAttempt,
        lease_token: str,
        lease_version: int,
        *,
        now: datetime,
    ) -> bool:
        return (
            task.status == CoreTaskStatus.RUNNING
            and attempt.status == AttemptStatus.RUNNING
            and task.current_attempt_no == attempt.attempt_no
            and secrets.compare_digest(attempt.lease_token, lease_token)
            and attempt.lease_version == lease_version
            and _utc(attempt.lease_expires_at) > now
        )

    @staticmethod
    def _transition(task: CoreTask, target: CoreTaskStatus) -> None:
        if not can_transition(task.status, target):
            raise InvalidTaskTransitionError(
                f"INVALID_TASK_TRANSITION:{task.status.value}->{target.value}"
            )
        task.status = target
        task.state_version += 1
        task.updated_at = utc_now()
