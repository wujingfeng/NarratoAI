from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError

from core_api.tasks.models import (
    CoreDispatchOutbox,
    CoreTaskAttempt,
    CoreTaskStatus,
    DispatchStatus,
    utc_now,
)
from core_api.tasks.service import (
    IdempotencyConflictError,
    InvalidTaskTransitionError,
    StaleLeaseError,
)


def test_idempotent_create_returns_original_task(task_service):
    """相同作用域和请求体只创建一个任务。"""

    kwargs = {
        "caller": "narrato-api",
        "route": "/api/v1/tasks/asr",
        "task_type": "asr",
        "idempotency_key": "same-request",
        "input_snapshot": {"asset_id": "asset_1"},
    }
    first = task_service.create_core_task(**kwargs)
    second = task_service.create_core_task(**kwargs)
    assert second.id == first.id
    assert first.id.startswith("ctask_")
    assert first.input_snapshot == {"asset_id": "asset_1"}


def test_idempotent_create_rejects_changed_body(task_service):
    """相同作用域的不同请求体产生稳定幂等冲突。"""

    base = {
        "caller": "narrato-api",
        "route": "/api/v1/tasks/asr",
        "task_type": "asr",
        "idempotency_key": "changed-request",
    }
    task_service.create_core_task(**base, input_snapshot={"asset_id": "asset_1"})
    with pytest.raises(IdempotencyConflictError, match="IDEMPOTENCY_CONFLICT"):
        task_service.create_core_task(
            **base, input_snapshot={"asset_id": "asset_2"}
        )


def test_stale_attempt_cannot_complete_task(task_service, task, session):
    """过期 attempt 的迟到结果不覆盖当前 attempt。"""

    first = task_service.start_attempt(task.id)
    first.lease_expires_at = utc_now() - timedelta(seconds=1)
    session.commit()
    assert task_service.expire_and_restart(first.id, retry_delay_seconds=0) is None
    with pytest.raises(StaleLeaseError):
        task_service.complete_attempt(
            first.id, first.lease_token, [], lease_version=first.lease_version
        )

    session.refresh(task)
    first_audit = session.get(CoreTaskAttempt, first.id)
    assert task.status == CoreTaskStatus.RETRY_WAIT
    assert task.current_attempt_no == first.attempt_no
    assert first_audit is not None
    assert first_audit.late_result_audit["outcome"] == "rejected_stale"

    second = task_service.claim_dispatched_task(
        task.id,
        expected_state_version=task.state_version,
        not_before=utc_now() - timedelta(seconds=1),
    )
    assert second is not None
    task_service.complete_attempt(
        second.id, second.lease_token, [], lease_version=second.lease_version
    )
    session.refresh(task)
    assert task.status == CoreTaskStatus.SUCCEEDED


def test_retry_limit_means_initial_plus_three_automatic_retries(task_service):
    """默认三次自动重试允许四个 attempt。"""

    core_task = task_service.create_core_task(
        caller="narrato-api",
        route="/api/v1/tasks/tts",
        task_type="tts",
        idempotency_key="retry-limit",
        input_snapshot={"text": "hello"},
    )
    attempt = task_service.start_attempt(core_task.id)
    for expected_no in (2, 3, 4):
        attempt.lease_expires_at = utc_now() - timedelta(seconds=1)
        task_service.session.commit()
        assert task_service.expire_and_restart(
            attempt.id, retry_delay_seconds=0
        ) is None
        current = task_service.get_task(core_task.id)
        attempt = task_service.claim_dispatched_task(
            core_task.id,
            expected_state_version=current.state_version,
            not_before=utc_now() - timedelta(seconds=1),
        )
        assert attempt is not None
        assert attempt.attempt_no == expected_no

    attempt.lease_expires_at = utc_now() - timedelta(seconds=1)
    task_service.session.commit()
    assert task_service.expire_and_restart(
        attempt.id, retry_delay_seconds=0
    ) is None
    session_task = task_service.get_task(core_task.id)
    assert session_task.status == CoreTaskStatus.FAILED
    assert session_task.current_attempt_no == 4


def test_terminal_task_cannot_return_to_running(task_service, task):
    """终态任务禁止重新领取。"""

    attempt = task_service.start_attempt(task.id)
    task_service.complete_attempt(
        attempt.id, attempt.lease_token, [], lease_version=attempt.lease_version
    )
    with pytest.raises(InvalidTaskTransitionError):
        task_service.start_attempt(task.id)


def test_duplicate_claim_does_not_create_second_attempt(task_service, task, session):
    """同一 running 任务重复领取不会产生两个 current attempt。"""

    first = task_service.start_attempt(task.id)
    with pytest.raises(InvalidTaskTransitionError):
        task_service.start_attempt(task.id)
    attempts = session.scalars(
        select(CoreTaskAttempt).where(CoreTaskAttempt.core_task_id == task.id)
    ).all()
    assert [item.id for item in attempts] == [first.id]


def test_retryable_failure_preserves_error_and_schedules_retry(task_service, task, session):
    """临时错误进入 retry_wait，直到可靠调度后才领取新 attempt。"""

    first = task_service.start_attempt(task.id)
    second = task_service.fail_attempt(
        first.id,
        first.lease_token,
        {"code": "PROVIDER_RATE_LIMITED", "message": "稍后重试"},
        retryable=True,
        lease_version=first.lease_version,
    )
    assert second is None
    assert task_service.get_task(task.id).status == CoreTaskStatus.RETRY_WAIT
    assert task_service.get_task(task.id).current_attempt_no == 1
    persisted = session.get(CoreTaskAttempt, first.id)
    assert persisted is not None
    assert persisted.error == {
        "code": "PROVIDER_RATE_LIMITED",
        "message": "稍后重试",
        "retryable": True,
    }
    assert persisted.status.value == "failed"
    dispatch = session.scalar(
        select(CoreDispatchOutbox).where(
            CoreDispatchOutbox.core_task_id == task.id,
            CoreDispatchOutbox.state_version == task.state_version,
            CoreDispatchOutbox.status == DispatchStatus.PENDING,
        )
    )
    assert dispatch is not None and dispatch.available_at > dispatch.created_at


def test_deterministic_failure_enters_terminal_failed(task_service, task):
    """确定性错误不消耗自动重试预算。"""

    attempt = task_service.start_attempt(task.id)
    assert (
        task_service.fail_attempt(
            attempt.id,
            attempt.lease_token,
            {"code": "UNSUPPORTED_FORMAT"},
            retryable=False,
            lease_version=attempt.lease_version,
        )
        is None
    )
    failed = task_service.get_task(task.id)
    assert failed.status == CoreTaskStatus.FAILED
    assert failed.current_attempt_no == 1


def test_completion_and_failure_require_explicit_lease_version(task_service, task):
    """完成与失败协议都必须由调用方显式携带租约版本。"""

    attempt = task_service.start_attempt(task.id)
    with pytest.raises(TypeError):
        task_service.complete_attempt(attempt.id, attempt.lease_token, [])
    with pytest.raises(TypeError):
        task_service.fail_attempt(
            attempt.id,
            attempt.lease_token,
            {"code": "TEMPORARY"},
            retryable=True,
        )


def test_completion_and_failure_reject_wrong_lease_version(task_service, task):
    """完成与失败都拒绝调用方提供的错误租约版本。"""

    attempt = task_service.start_attempt(task.id)
    with pytest.raises(StaleLeaseError):
        task_service.complete_attempt(
            attempt.id,
            attempt.lease_token,
            [],
            lease_version=attempt.lease_version + 1,
        )
    with pytest.raises(StaleLeaseError):
        task_service.fail_attempt(
            attempt.id,
            attempt.lease_token,
            {"code": "TEMPORARY"},
            retryable=True,
            lease_version=attempt.lease_version + 1,
        )


def test_database_rejects_invalid_persisted_statuses(session, task_service, task):
    """事实数据库对 task、attempt 和 outbox 状态均有命名约束。"""

    attempt = task_service.start_attempt(task.id)
    constraints = {
        table: {item["name"] for item in inspect(session.bind).get_check_constraints(table)}
        for table in ("core_tasks", "core_task_attempts", "callback_outbox")
    }
    assert "core_task_status" in constraints["core_tasks"]
    assert "core_attempt_status" in constraints["core_task_attempts"]
    assert "callback_outbox_status" in constraints["callback_outbox"]

    with pytest.raises(IntegrityError):
        session.execute(
            text("UPDATE core_tasks SET status = 'cancelled' WHERE id = :task_id"),
            {"task_id": task.id},
        )
        session.commit()
    session.rollback()
    assert attempt.status.value == "running"
