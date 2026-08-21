from __future__ import annotations

import secrets
from collections.abc import Callable
from datetime import timedelta

from sqlalchemy import update
from sqlalchemy.orm import Session

from narrato_api.workflows.models import WorkflowOutbox, utc_now

WorkflowWakeUp = Callable[[str, str], bool]


class WorkflowOutboxDispatcher:
    """认领单个工作流 Outbox 事件，并唤醒一个窄注入的后续执行器。"""

    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self.session_factory = session_factory

    def dispatch(self, event_id: str, wake_up: WorkflowWakeUp) -> bool:
        """仅认领一次 pending 事件；唤醒失败时将事件持久化回 pending。"""

        lease_id = secrets.token_hex(16)
        with self.session_factory() as session:
            with session.begin():
                claimed = session.execute(
                    update(WorkflowOutbox)
                    .where(
                        WorkflowOutbox.id == event_id,
                        WorkflowOutbox.status == "pending",
                        WorkflowOutbox.available_at <= utc_now(),
                    )
                    .values(
                        status="sending",
                        attempt_count=WorkflowOutbox.attempt_count + 1,
                        dispatch_lease_id=lease_id,
                        dispatch_started_at=utc_now(),
                    )
                    .returning(WorkflowOutbox.id, WorkflowOutbox.idempotency_key)
                ).one_or_none()

        if claimed is None:
            return False

        try:
            # 工作流在事件被领取前可能已由回调/另一事件推进。此时没有 ready
            # 节点是合法 no-op；把事件标记 sent，不能无限退回 pending 并热循环。
            wake_up(claimed.id, claimed.idempotency_key)
        except Exception:
            with self.session_factory() as session:
                with session.begin():
                    session.execute(
                        update(WorkflowOutbox)
                        .where(
                            WorkflowOutbox.id == event_id,
                            WorkflowOutbox.status == "sending",
                            WorkflowOutbox.dispatch_lease_id == lease_id,
                        )
                        .values(
                            status="pending",
                            dispatch_lease_id=None,
                            dispatch_started_at=None,
                        )
                    )
            return False

        with self.session_factory() as session:
            with session.begin():
                session.execute(
                    update(WorkflowOutbox)
                    .where(
                        WorkflowOutbox.id == event_id,
                        WorkflowOutbox.status == "sending",
                        WorkflowOutbox.dispatch_lease_id == lease_id,
                    )
                    .values(
                        status="sent",
                        sent_at=utc_now(),
                        dispatch_lease_id=None,
                        dispatch_started_at=None,
                    )
                )
        return True

    def requeue_expired_sending(self, *, lease_seconds: float) -> int:
        """回收进程崩溃遗留的发送租约，重新交由 Outbox 重放。"""

        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")
        expired_before = utc_now() - timedelta(seconds=lease_seconds)
        with self.session_factory() as session:
            with session.begin():
                result = session.execute(
                    update(WorkflowOutbox)
                    .where(
                        WorkflowOutbox.status == "sending",
                        WorkflowOutbox.dispatch_started_at.is_not(None),
                        WorkflowOutbox.dispatch_started_at <= expired_before,
                    )
                    .values(
                        status="pending",
                        available_at=utc_now(),
                        dispatch_lease_id=None,
                        dispatch_started_at=None,
                    )
                )
                return int(result.rowcount or 0)
