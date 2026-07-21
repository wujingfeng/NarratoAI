from __future__ import annotations

from collections.abc import Callable

from sqlalchemy import update
from sqlalchemy.orm import Session

from narrato_api.workflows.models import WorkflowOutbox, utc_now

WorkflowWakeUp = Callable[[str, str], None]


class WorkflowOutboxDispatcher:
    """认领单个工作流 Outbox 事件，并唤醒一个窄注入的后续执行器。"""

    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self.session_factory = session_factory

    def dispatch(self, event_id: str, wake_up: WorkflowWakeUp) -> bool:
        """仅认领一次 pending 事件；唤醒失败时将事件持久化回 pending。"""

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
                    )
                    .returning(WorkflowOutbox.id, WorkflowOutbox.idempotency_key)
                ).one_or_none()

        if claimed is None:
            return False

        try:
            wake_up(claimed.id, claimed.idempotency_key)
        except Exception:
            with self.session_factory() as session:
                with session.begin():
                    session.execute(
                        update(WorkflowOutbox)
                        .where(
                            WorkflowOutbox.id == event_id,
                            WorkflowOutbox.status == "sending",
                        )
                        .values(status="pending")
                    )
            return False

        with self.session_factory() as session:
            with session.begin():
                session.execute(
                    update(WorkflowOutbox)
                    .where(
                        WorkflowOutbox.id == event_id,
                        WorkflowOutbox.status == "sending",
                    )
                    .values(status="sent", sent_at=utc_now())
                )
        return True
