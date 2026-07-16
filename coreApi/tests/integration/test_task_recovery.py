from __future__ import annotations

from datetime import timedelta
import threading
import pytest

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from core_api.database import Base, create_database_engine
from core_api.tasks.dispatch import DispatchOutboxPublisher
from core_api.tasks.models import (
    AttemptStatus,
    CoreDispatchOutbox,
    CoreTaskAttempt,
    CoreTaskStatus,
    DispatchStatus,
    utc_now,
)
from core_api.tasks.service import TaskService
from core_api.tasks.handlers import AtomicTaskHandler
from core_api.tasks.recovery import TaskRecoveryScanner


class MessageRecorder:
    """记录完整 fenced dispatch 消息。"""

    def __init__(self) -> None:
        self.messages: list[dict[str, object]] = []

    def dispatch(
        self,
        task_id: str,
        *,
        expected_state_version: int,
        not_before,
        dispatch_id: str,
    ) -> None:
        self.messages.append(
            {
                "task_id": task_id,
                "expected_state_version": expected_state_version,
                "not_before": not_before,
                "dispatch_id": dispatch_id,
            }
        )


def _task(service: TaskService, key: str):
    return service.create_core_task(
        caller="narrato-api",
        route="/api/v1/media-probe/tasks",
        task_type="media_probe",
        idempotency_key=key,
        input_snapshot={},
    )


def test_dispatch_message_is_fenced_and_future_event_cannot_be_forced(session):
    service = TaskService(session)
    task = _task(service, "fenced-dispatch")
    DispatchOutboxPublisher(session).publish_pending(MessageRecorder())
    attempt = service.start_attempt(task.id)
    future = utc_now() + timedelta(minutes=5)
    service.fail_attempt(
        attempt.id,
        attempt.lease_token,
        {"code": "TEMP"},
        retryable=True,
        lease_version=attempt.lease_version,
        retry_delay_seconds=300,
    )
    row = session.scalar(
        select(CoreDispatchOutbox).where(
            CoreDispatchOutbox.core_task_id == task.id,
            CoreDispatchOutbox.status == DispatchStatus.PENDING,
        )
    )
    row.available_at = future
    session.commit()

    recorder = MessageRecorder()
    assert DispatchOutboxPublisher(session).publish_task(
        task.id, recorder, now=utc_now()
    ) is False
    assert recorder.messages == []

    assert DispatchOutboxPublisher(session).publish_task(
        task.id, recorder, now=future
    ) is True
    assert recorder.messages == [
        {
            "task_id": task.id,
            "expected_state_version": task.state_version,
            "not_before": future,
            "dispatch_id": row.id,
        }
    ]


def test_fenced_claim_ignores_old_duplicate_and_future_wakes(session):
    service = TaskService(session)
    task = _task(service, "fenced-claim")
    not_before = utc_now()
    first = service.claim_dispatched_task(
        task.id,
        expected_state_version=task.state_version,
        not_before=not_before,
        now=not_before,
    )
    assert first is not None
    assert service.claim_dispatched_task(
        task.id,
        expected_state_version=0,
        not_before=not_before,
        now=not_before,
    ) is None

    retry_task = _task(service, "future-claim")
    assert service.claim_dispatched_task(
        retry_task.id,
        expected_state_version=retry_task.state_version,
        not_before=not_before + timedelta(seconds=60),
        now=not_before,
    ) is None
    assert retry_task.current_attempt_no == 0


def test_handler_does_not_run_adapter_for_stale_or_future_wake(session, tmp_path):
    class NeverRun:
        def __init__(self) -> None:
            self.calls = 0

        def run(self, **_kwargs):
            self.calls += 1
            return {}

    service = TaskService(session)
    task = _task(service, "handler-fence")
    adapter = NeverRun()
    handler = AtomicTaskHandler(
        task_service=service,
        work_root=tmp_path / "fence-work",
        media_probe_adapter=adapter,
    )
    handler.run(
        task.id,
        expected_state_version=task.state_version,
        not_before=utc_now() + timedelta(minutes=1),
        dispatch_id="dispatch_future",
    )
    assert adapter.calls == 0
    assert task.current_attempt_no == 0

    first = service.start_attempt(task.id)
    handler.run(
        task.id,
        expected_state_version=0,
        not_before=utc_now() - timedelta(seconds=1),
        dispatch_id="dispatch_stale",
    )
    assert adapter.calls == 0
    assert first.status == AttemptStatus.RUNNING


def test_recovery_scanner_rearms_lost_queued_and_expires_running(session):
    from core_api.tasks.recovery import TaskRecoveryScanner

    service = TaskService(session)
    queued = _task(service, "lost-queued")
    recorder = MessageRecorder()
    assert DispatchOutboxPublisher(session).publish_pending(recorder) == 1
    queued_dispatch = session.scalar(
        select(CoreDispatchOutbox).where(CoreDispatchOutbox.core_task_id == queued.id)
    )
    observed = utc_now() + timedelta(minutes=2)
    queued_dispatch.sent_at = observed - timedelta(minutes=2)
    queued_dispatch.recover_after = observed - timedelta(seconds=1)

    running = _task(service, "expired-running")
    running_attempt = service.start_attempt(running.id, lease_seconds=1)
    running_attempt.lease_expires_at = observed - timedelta(seconds=1)
    session.commit()

    scanner = TaskRecoveryScanner(
        session,
        queued_timeout_seconds=30,
        heartbeat_timeout_seconds=30,
        retry_delay_seconds=0,
    )
    assert scanner.recover(now=observed) == 2
    session.refresh(queued_dispatch)
    session.refresh(running_attempt)
    session.refresh(running)
    assert queued_dispatch.status == DispatchStatus.PENDING
    assert queued_dispatch.available_at.replace(tzinfo=observed.tzinfo) <= observed
    assert running_attempt.status == AttemptStatus.EXPIRED
    assert running.status == CoreTaskStatus.RETRY_WAIT
    assert running.current_attempt_no == 1
    assert session.scalar(
        select(CoreDispatchOutbox).where(
            CoreDispatchOutbox.core_task_id == running.id,
            CoreDispatchOutbox.state_version == running.state_version,
            CoreDispatchOutbox.status == DispatchStatus.PENDING,
        )
    ) is not None
    assert scanner.recover(now=observed) == 0


def test_recovery_scanner_never_rearms_terminal_success(session):
    from core_api.tasks.recovery import TaskRecoveryScanner

    service = TaskService(session)
    task = _task(service, "terminal-skip")
    attempt = service.start_attempt(task.id)
    service.complete_attempt(
        attempt.id,
        attempt.lease_token,
        {},
        lease_version=attempt.lease_version,
    )
    assert TaskRecoveryScanner(session).recover(now=utc_now() + timedelta(days=1)) == 0
    assert service.get_task(task.id).status == CoreTaskStatus.SUCCEEDED


def test_production_recovery_task_rearms_and_dispatches_in_one_scan(
    settings, monkeypatch
):
    from core_api.database import get_engine
    from core_api.tasks import celery_tasks

    engine = get_engine(settings)
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as database:
        task = _task(TaskService(database), "production-recovery")
        assert DispatchOutboxPublisher(database).publish_pending(MessageRecorder()) == 1
        row = database.scalar(
            select(CoreDispatchOutbox).where(CoreDispatchOutbox.core_task_id == task.id)
        )
        row.sent_at = utc_now() - timedelta(minutes=5)
        row.recover_after = utc_now() - timedelta(seconds=1)
        database.commit()
        task_id = task.id

    delivered: list[tuple[object, ...]] = []
    monkeypatch.setattr(celery_tasks, "get_cached_settings", lambda: settings)
    monkeypatch.setattr(
        celery_tasks.wake_core_task,
        "delay",
        lambda *args: delivered.append(args),
    )
    celery_tasks.recover_stalled_core_tasks.run()
    assert len(delivered) == 1
    assert delivered[0][0] == task_id
    assert delivered[0][1] == 0


def test_concurrent_fenced_claim_creates_exactly_one_attempt(tmp_path):
    database = tmp_path / "claim.db"
    engine = create_database_engine(f"sqlite:///{database}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as setup:
        task = _task(TaskService(setup), "concurrent-claim")
        task_id = task.id
        version = task.state_version

    barrier = threading.Barrier(2)
    outcomes: list[str] = []
    errors: list[BaseException] = []

    def worker() -> None:
        try:
            with factory() as database_session:
                barrier.wait()
                claimed = TaskService(database_session).claim_dispatched_task(
                    task_id,
                    expected_state_version=version,
                    not_before=utc_now() - timedelta(seconds=1),
                )
                outcomes.append("claimed" if claimed is not None else "ignored")
        except BaseException as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)
    assert errors == []
    assert sorted(outcomes) == ["claimed", "ignored"]
    with Session(engine) as verify:
        attempts = verify.scalars(
            select(CoreTaskAttempt).where(CoreTaskAttempt.core_task_id == task_id)
        ).all()
        assert len(attempts) == 1


def test_recovery_prioritizes_expired_running_over_101_stale_sent(session):
    service = TaskService(session)
    observed = utc_now() + timedelta(hours=2)
    for index in range(101):
        task = _task(service, f"stale-{index}")
        DispatchOutboxPublisher(session).publish_pending(MessageRecorder())
        row = session.scalar(
            select(CoreDispatchOutbox).where(CoreDispatchOutbox.core_task_id == task.id)
        )
        row.sent_at = observed - timedelta(hours=1)
        row.recover_after = observed - timedelta(seconds=1)
        session.commit()
    running = _task(service, "fair-running")
    attempt = service.start_attempt(running.id, lease_seconds=1)
    attempt.lease_expires_at = observed - timedelta(seconds=1)
    session.commit()

    changed = TaskRecoveryScanner(
        session, queued_timeout_seconds=60, retry_delay_seconds=0
    ).recover(now=observed, limit=100)
    session.refresh(running)
    assert changed == 100
    assert running.status == CoreTaskStatus.RETRY_WAIT
    assert attempt.status == AttemptStatus.EXPIRED


def test_sent_visibility_uses_exponential_attempt_window(session):
    service = TaskService(session)
    task = _task(service, "visibility-window")
    publisher = DispatchOutboxPublisher(session)
    recorder = MessageRecorder()
    observed = utc_now() + timedelta(minutes=10)
    assert publisher.publish_pending(recorder) == 1
    row = session.scalar(
        select(CoreDispatchOutbox).where(CoreDispatchOutbox.core_task_id == task.id)
    )
    row.sent_at = observed - timedelta(seconds=301)
    row.recover_after = observed - timedelta(seconds=1)
    session.commit()
    scanner = TaskRecoveryScanner(session, queued_timeout_seconds=300)
    assert scanner.recover(now=observed) == 1
    assert publisher.publish_pending(recorder, now=observed) == 1
    assert row.attempt_count == 2
    assert scanner.recover(now=observed + timedelta(seconds=599)) == 0
    assert scanner.recover(now=observed + timedelta(seconds=600)) == 1


def test_due_retry_wait_dispatch_is_prioritized_over_101_queued(session):
    service = TaskService(session)
    publisher = DispatchOutboxPublisher(session)
    for index in range(101):
        _task(service, f"pending-queued-{index}")
    retry = _task(service, "priority-retry")
    publisher.publish_task(retry.id, MessageRecorder())
    attempt = service.start_attempt(retry.id)
    service.fail_attempt(
        attempt.id,
        attempt.lease_token,
        {"code": "TEMP"},
        retryable=True,
        lease_version=attempt.lease_version,
        retry_delay_seconds=0,
    )
    recorder = MessageRecorder()
    assert publisher.publish_pending(recorder, limit=100) == 100
    assert retry.id in {message["task_id"] for message in recorder.messages}


@pytest.mark.parametrize("status", [CoreTaskStatus.QUEUED, CoreTaskStatus.RETRY_WAIT])
def test_recovery_sql_limit_selects_due_deadline_after_non_due_older_rows(
    session, status
):
    service = TaskService(session)
    observed = utc_now() + timedelta(hours=1)
    for index in range(4):
        task = _task(service, f"not-due-{status.value}-{index}")
        row = session.scalar(
            select(CoreDispatchOutbox).where(CoreDispatchOutbox.core_task_id == task.id)
        )
        task.status = status
        row.status = DispatchStatus.SENT
        row.attempt_count = 9
        row.sent_at = observed - timedelta(hours=2)
        row.recover_after = observed + timedelta(hours=1)
        session.commit()
    due = _task(service, f"due-{status.value}")
    due.status = status
    due_row = session.scalar(
        select(CoreDispatchOutbox).where(CoreDispatchOutbox.core_task_id == due.id)
    )
    due_row.status = DispatchStatus.SENT
    due_row.attempt_count = 1
    due_row.sent_at = observed - timedelta(minutes=10)
    due_row.recover_after = observed - timedelta(seconds=1)
    session.commit()

    assert TaskRecoveryScanner(session).recover(now=observed, limit=1) == 1
    session.refresh(due_row)
    assert due_row.status == DispatchStatus.PENDING
