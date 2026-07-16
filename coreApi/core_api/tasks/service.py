from __future__ import annotations

import hashlib
import json
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from core_api.ids import new_time_ordered_id
from core_api.tasks.callbacks import OutboxEventConflictError, enqueue_state_callback
from core_api.tasks.models import (
    AttemptStatus,
    CoreTask,
    CoreTaskAttempt,
    CoreTaskStatus,
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
    ) -> CoreTask:
        """按调用方、路径和 Key 幂等创建不可变 Core Task。"""

        if max_retries < 0:
            raise ValueError("max_retries 不能小于零")
        scope = f"{caller}\x1f{route}\x1f{idempotency_key}"
        digest = _digest_payload(input_snapshot)
        existing = self.session.scalar(
            select(CoreTask).where(CoreTask.idempotency_scope == scope)
        )
        if existing is not None:
            if existing.request_digest != digest:
                raise IdempotencyConflictError("IDEMPOTENCY_CONFLICT")
            return existing
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
            max_retries=max_retries,
        )
        # 唯一约束是并发幂等的最终裁决；savepoint 让 loser 可恢复并回读 winner。
        self.session.commit()
        try:
            with self.session.begin_nested():
                self.session.add(task)
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
            return winner
        self.session.commit()
        return task

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
        task = self.session.scalar(
            select(CoreTask).where(CoreTask.id == task_id).with_for_update()
        )
        if task is None:
            raise TaskNotFoundError("CORE_TASK_NOT_FOUND")
        if task.status not in {CoreTaskStatus.QUEUED, CoreTaskStatus.RETRY_WAIT}:
            raise InvalidTaskTransitionError("CORE_TASK_NOT_CLAIMABLE")
        now = utc_now()
        task.current_attempt_no += 1
        self._transition(task, CoreTaskStatus.RUNNING)
        task.started_at = task.started_at or now
        attempt = CoreTaskAttempt(
            id=new_time_ordered_id("attempt_"),
            core_task_id=task.id,
            attempt_no=task.current_attempt_no,
            status=AttemptStatus.RUNNING,
            lease_token=secrets.token_urlsafe(32),
            lease_version=task.current_attempt_no,
            heartbeat_at=now,
            lease_expires_at=now + timedelta(seconds=lease_seconds),
            started_at=now,
        )
        self.session.add(attempt)
        enqueue_state_callback(
            self.session,
            task,
            event_id=f"evt_{task.id}_{task.state_version}",
        )
        self.session.commit()
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
            attempt, task, lease_seconds=lease_seconds, now=observed_at
        )

    def _restart_locked_attempt(
        self,
        attempt: CoreTaskAttempt,
        task: CoreTask,
        *,
        lease_seconds: float,
        now: datetime,
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
        task.current_attempt_no += 1
        self._transition(task, CoreTaskStatus.RUNNING)
        replacement = CoreTaskAttempt(
            id=new_time_ordered_id("attempt_"),
            core_task_id=task.id,
            attempt_no=task.current_attempt_no,
            status=AttemptStatus.RUNNING,
            lease_token=secrets.token_urlsafe(32),
            lease_version=task.current_attempt_no,
            heartbeat_at=now,
            lease_expires_at=now + timedelta(seconds=lease_seconds),
            started_at=now,
        )
        self.session.add(replacement)
        enqueue_state_callback(
            self.session,
            task,
            event_id=f"evt_{task.id}_{task.state_version}",
        )
        self.session.commit()
        return replacement

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

    def fail_attempt(
        self,
        attempt_id: str,
        lease_token: str,
        error: dict[str, Any],
        *,
        retryable: bool,
        lease_version: int,
    ) -> CoreTaskAttempt | None:
        """记录失败；确定性错误终止，临时错误按预算自动重试。"""

        attempt, task = self._locked_attempt_and_task(attempt_id)
        if not self._valid_current_lease(
            task, attempt, lease_token, lease_version, now=utc_now()
        ):
            raise StaleLeaseError("STALE_LEASE")
        attempt.error = {**error, "retryable": retryable}
        if retryable:
            return self._restart_locked_attempt(
                attempt, task, lease_seconds=60, now=utc_now()
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
        )
        if attempt is None:
            raise TaskNotFoundError("CORE_ATTEMPT_NOT_FOUND")
        task = self.session.scalar(
            select(CoreTask)
            .where(CoreTask.id == attempt.core_task_id)
            .with_for_update()
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
