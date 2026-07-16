from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from core_api.tasks.models import (
    AttemptStatus,
    CoreDispatchOutbox,
    CoreTask,
    CoreTaskAttempt,
    CoreTaskStatus,
    DispatchStatus,
    utc_now,
)
from core_api.tasks.service import LeaseStillActiveError, StaleLeaseError, TaskService


def _utc(value: datetime) -> datetime:
    """统一 SQLite 朴素时间与生产带时区时间。"""

    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class TaskRecoveryScanner:
    """从数据库事实恢复 Broker 丢失 wake、过期租约和到期 retry。"""

    def __init__(
        self,
        session: Session,
        *,
        queued_timeout_seconds: float = 300,
        heartbeat_timeout_seconds: float = 60,
        retry_delay_seconds: float = 5,
        max_visibility_timeout_seconds: float = 3600,
    ) -> None:
        self.session = session
        self.queued_timeout_seconds = queued_timeout_seconds
        self.heartbeat_timeout_seconds = heartbeat_timeout_seconds
        self.retry_delay_seconds = retry_delay_seconds
        self.max_visibility_timeout_seconds = max_visibility_timeout_seconds

    def recover(self, *, now: datetime | None = None, limit: int = 100) -> int:
        """幂等恢复最多 limit 条；成功和仍有效执行永不重做。"""

        observed_at = _utc(now) if now is not None else utc_now()
        # 先释放会阻塞状态机的 expired running，避免大量 stale sent 造成饥饿。
        changed = self._expire_running(observed_at, limit=limit)
        remaining = max(0, limit - changed)
        if remaining:
            changed += self._rearm_sent_wakes(
                observed_at, status=CoreTaskStatus.RETRY_WAIT, limit=remaining
            )
        remaining = max(0, limit - changed)
        if remaining:
            changed += self._rearm_sent_wakes(
                observed_at, status=CoreTaskStatus.QUEUED, limit=remaining
            )
        return changed

    def _rearm_sent_wakes(
        self, now: datetime, *, status: CoreTaskStatus, limit: int
    ) -> int:
        rows = self.session.scalars(
            select(CoreDispatchOutbox)
            .join(CoreTask, CoreTask.id == CoreDispatchOutbox.core_task_id)
            .where(
                CoreDispatchOutbox.status == DispatchStatus.SENT,
                CoreDispatchOutbox.recover_after.is_not(None),
                CoreDispatchOutbox.recover_after <= now,
                CoreTask.state_version == CoreDispatchOutbox.state_version,
                CoreTask.status == status,
            )
            .order_by(CoreDispatchOutbox.recover_after, CoreDispatchOutbox.id)
            .limit(limit)
            .with_for_update(skip_locked=True)
        ).all()
        for row in rows:
            row.status = DispatchStatus.PENDING
            row.available_at = now
            row.sent_at = None
            row.recover_after = None
            row.last_error = "WAKE_NOT_CLAIMED"
        if rows:
            self.session.commit()
        return len(rows)

    def _expire_running(self, now: datetime, *, limit: int) -> int:
        attempt_ids = self.session.scalars(
            select(CoreTaskAttempt.id)
            .join(CoreTask, CoreTask.id == CoreTaskAttempt.core_task_id)
            .where(
                CoreTask.status == CoreTaskStatus.RUNNING,
                CoreTaskAttempt.status == AttemptStatus.RUNNING,
                CoreTaskAttempt.attempt_no == CoreTask.current_attempt_no,
                (
                    (CoreTaskAttempt.lease_expires_at <= now)
                    | (
                        CoreTaskAttempt.heartbeat_at
                        <= now - timedelta(seconds=self.heartbeat_timeout_seconds)
                    )
                ),
            )
            .limit(limit)
            .with_for_update(skip_locked=True)
        ).all()
        changed = 0
        for attempt_id in attempt_ids:
            try:
                TaskService(self.session).expire_and_restart(
                    attempt_id,
                    heartbeat_timeout_seconds=self.heartbeat_timeout_seconds,
                    now=now,
                    retry_delay_seconds=self.retry_delay_seconds,
                )
            except (LeaseStillActiveError, StaleLeaseError):
                self.session.rollback()
                continue
            changed += 1
        return changed
