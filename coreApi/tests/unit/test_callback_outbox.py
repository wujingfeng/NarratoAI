from __future__ import annotations

from datetime import timedelta

from sqlalchemy import func, select

import pytest

from core_api.tasks.callbacks import OutboxEventConflictError
from core_api.tasks.models import CallbackOutbox, CoreTaskStatus, utc_now


def test_terminal_callback_is_written_once(session, task_service, task):
    """重复终态事件只写一个 Outbox。"""

    task_service.mark_succeeded(task.id, event_id="evt_1")
    task_service.mark_succeeded(task.id, event_id="evt_1")
    assert session.scalar(select(func.count(CallbackOutbox.id))) == 1


def test_same_state_version_with_different_event_is_written_once(
    session, task_service, task
):
    """同一状态版本即使 event_id 不同也只写一次。"""

    task_service.mark_succeeded(task.id, event_id="evt_first")
    task_service.mark_succeeded(task.id, event_id="evt_duplicate")
    rows = session.scalars(select(CallbackOutbox)).all()
    assert len(rows) == 1
    assert rows[0].event_id == "evt_first"
    assert rows[0].payload["status"] == "succeeded"


def test_outbox_records_attempt_and_state_version(session, task_service, task):
    """运行中和终态回调均携带 attempt 与单调状态版本。"""

    attempt = task_service.start_attempt(task.id)
    task_service.complete_attempt(
        attempt.id,
        attempt.lease_token,
        [{"id": "art_1"}],
        lease_version=attempt.lease_version,
    )
    rows = session.scalars(
        select(CallbackOutbox).order_by(CallbackOutbox.state_version)
    ).all()
    assert [(row.attempt_no, row.state_version) for row in rows] == [(1, 1), (1, 2)]
    assert rows[0].payload["status"] == "running"
    assert rows[1].core_task_id == task.id
    assert rows[1].payload["status"] == "succeeded"
    assert rows[1].payload["result"] == [{"id": "art_1"}]


def test_retry_transitions_each_write_one_state_event(session, task_service, task):
    """租约过期的 retry_wait 与新 running 状态均可靠入 Outbox。"""

    first = task_service.start_attempt(task.id)
    first.lease_expires_at = utc_now() - timedelta(seconds=1)
    session.commit()
    task_service.expire_and_restart(first.id)
    rows = session.scalars(
        select(CallbackOutbox).order_by(CallbackOutbox.state_version)
    ).all()
    assert [(row.state_version, row.payload["status"]) for row in rows] == [
        (1, "running"),
        (2, "retry_wait"),
        (3, "running"),
    ]


def test_event_id_collision_rolls_back_second_task(session, task_service, task):
    """跨任务 event_id 碰撞不得提交第二任务终态。"""

    other = task_service.create_core_task(
        caller="narrato-api",
        route="/api/v1/tasks/asr",
        task_type="asr",
        idempotency_key="event-collision-other",
        input_snapshot={"asset": "asset_2"},
    )
    task_service.mark_succeeded(task.id, event_id="evt_shared")
    with pytest.raises(OutboxEventConflictError, match="OUTBOX_EVENT_CONFLICT"):
        task_service.mark_succeeded(other.id, event_id="evt_shared")
    session.refresh(other)
    assert other.status == CoreTaskStatus.QUEUED
    assert other.state_version == 0
    assert session.scalar(select(func.count(CallbackOutbox.id))) == 1


def test_same_event_id_cannot_represent_later_state(session, task_service, task):
    """同任务不同 state_version 复用 event_id 也必须回滚。"""

    attempt = task_service.start_attempt(task.id)
    running_event = session.scalar(select(CallbackOutbox))
    assert running_event is not None
    with pytest.raises(OutboxEventConflictError, match="OUTBOX_EVENT_CONFLICT"):
        task_service.complete_attempt(
            attempt.id,
            attempt.lease_token,
            [],
            lease_version=attempt.lease_version,
            event_id=running_event.event_id,
        )
    session.refresh(task)
    session.refresh(attempt)
    assert task.status == CoreTaskStatus.RUNNING
    assert task.state_version == 1
    assert attempt.status.value == "running"
