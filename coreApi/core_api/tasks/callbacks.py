from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from core_api.ids import new_time_ordered_id
from core_api.tasks.models import CallbackOutbox, CoreTask


class OutboxEventConflictError(RuntimeError):
    """event_id 已被另一逻辑状态事件占用。"""


def enqueue_state_callback(
    session: Session, task: CoreTask, *, event_id: str
) -> CallbackOutbox:
    """为任务当前状态版本幂等写入回调 Outbox。"""

    event_row = session.scalar(
        select(CallbackOutbox).where(CallbackOutbox.event_id == event_id)
    )
    if event_row is not None:
        if (
            event_row.core_task_id == task.id
            and event_row.state_version == task.state_version
        ):
            return event_row
        raise OutboxEventConflictError("OUTBOX_EVENT_CONFLICT")

    state_row = session.scalar(
        select(CallbackOutbox).where(
            CallbackOutbox.core_task_id == task.id,
            CallbackOutbox.state_version == task.state_version,
        )
    )
    if state_row is not None:
        return state_row
    row = CallbackOutbox(
        id=new_time_ordered_id("cb_"),
        event_id=event_id,
        core_task_id=task.id,
        attempt_no=task.current_attempt_no,
        state_version=task.state_version,
        payload={
            "event_id": event_id,
            "core_task_id": task.id,
            "attempt_no": task.current_attempt_no,
            "state_version": task.state_version,
            "status": task.status.value,
            "phase": task.phase,
            "progress": task.progress,
            "result": task.result,
            "error": task.error,
        },
    )
    session.add(row)
    return row
