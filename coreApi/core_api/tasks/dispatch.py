from __future__ import annotations

from datetime import datetime, timedelta
from typing import Protocol

from sqlalchemy import case, select
from sqlalchemy.orm import Session

from core_api.ids import new_time_ordered_id
from core_api.tasks.models import (
    CoreDispatchOutbox,
    CoreTask,
    CoreTaskStatus,
    DispatchStatus,
    utc_now,
)


class TaskDispatcher(Protocol):
    """发送可重复 Core Task 唤醒的 Broker 协议。"""

    def dispatch(
        self,
        task_id: str,
        *,
        expected_state_version: int,
        not_before: datetime,
        dispatch_id: str,
    ) -> None:
        """发送带状态版本、到期时间和事件 ID 的 fenced wake。"""

        ...


def enqueue_task_dispatch(
    session: Session,
    task: CoreTask,
    *,
    available_at: datetime | None = None,
) -> CoreDispatchOutbox:
    """在调用方事务中幂等写入当前状态版本的唤醒事件。"""

    existing = session.scalar(
        select(CoreDispatchOutbox).where(
            CoreDispatchOutbox.core_task_id == task.id,
            CoreDispatchOutbox.state_version == task.state_version,
        )
    )
    if existing is not None:
        return existing
    row = CoreDispatchOutbox(
        id=new_time_ordered_id("dispatch_"),
        core_task_id=task.id,
        state_version=task.state_version,
        status=DispatchStatus.PENDING,
        available_at=available_at or utc_now(),
    )
    session.add(row)
    return row


class DispatchOutboxPublisher:
    """发布持久唤醒事件；发送后崩溃最多造成安全重复投递。"""

    def __init__(
        self,
        session: Session,
        *,
        failure_delay_seconds: float = 1.0,
        visibility_timeout_seconds: float = 300.0,
        max_visibility_timeout_seconds: float = 3600.0,
    ) -> None:
        self.session = session
        self.failure_delay_seconds = failure_delay_seconds
        self.visibility_timeout_seconds = visibility_timeout_seconds
        self.max_visibility_timeout_seconds = max_visibility_timeout_seconds

    def publish_task(
        self,
        task_id: str,
        dispatcher: TaskDispatcher,
        *,
        now: datetime | None = None,
    ) -> bool:
        """发布某任务最早 pending 事件并原子标记发送成功。"""

        observed_at = now or utc_now()
        statement = (
            select(CoreDispatchOutbox)
            .where(
                CoreDispatchOutbox.core_task_id == task_id,
                CoreDispatchOutbox.status == DispatchStatus.PENDING,
            )
            .order_by(CoreDispatchOutbox.available_at, CoreDispatchOutbox.created_at)
            .with_for_update()
        )
        # 所有入口都只能发布到期事件；幂等重放不能绕过 retry backoff。
        statement = statement.where(CoreDispatchOutbox.available_at <= observed_at)
        row = self.session.scalar(statement)
        if row is None:
            return False
        try:
            dispatcher.dispatch(
                task_id,
                expected_state_version=row.state_version,
                not_before=row.available_at,
                dispatch_id=row.id,
            )
        except Exception:
            # Broker 原始异常可能含 URI/凭据，只持久化稳定分类。
            row.attempt_count += 1
            row.last_error = "DISPATCH_FAILED"
            row.available_at = observed_at + timedelta(seconds=self.failure_delay_seconds)
            row.recover_after = None
            self.session.commit()
            return False
        row.attempt_count += 1
        row.status = DispatchStatus.SENT
        row.last_error = None
        row.sent_at = observed_at
        visibility = min(
            self.max_visibility_timeout_seconds,
            self.visibility_timeout_seconds * (2 ** max(0, row.attempt_count - 1)),
        )
        row.recover_after = observed_at + timedelta(seconds=visibility)
        self.session.commit()
        return True

    def publish_pending(
        self,
        dispatcher: TaskDispatcher,
        *,
        now: datetime | None = None,
        limit: int = 100,
    ) -> int:
        """扫描到期 pending 事件，供 Beat/独立调度器重复调用。"""

        observed_at = now or utc_now()
        ids = self.session.scalars(
            select(CoreDispatchOutbox.core_task_id)
            .join(CoreTask, CoreTask.id == CoreDispatchOutbox.core_task_id)
            .where(
                CoreDispatchOutbox.status == DispatchStatus.PENDING,
                CoreDispatchOutbox.available_at <= observed_at,
            )
            .order_by(
                case((CoreTask.status == CoreTaskStatus.RETRY_WAIT, 0), else_=1),
                CoreDispatchOutbox.available_at,
            )
            .limit(limit)
        ).all()
        sent = 0
        for task_id in ids:
            sent += int(
                self.publish_task(
                    task_id, dispatcher, now=observed_at
                )
            )
        return sent
