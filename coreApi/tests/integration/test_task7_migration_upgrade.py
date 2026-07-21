from __future__ import annotations

from datetime import timedelta

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from core_api.tasks.dispatch import DispatchOutboxPublisher
from core_api.tasks.models import CoreDispatchOutbox, CoreTask, CoreTaskStatus, utc_now
from core_api.tasks.recovery import TaskRecoveryScanner


class Recorder:
    def __init__(self) -> None:
        self.ids: list[str] = []

    def dispatch(self, task_id: str, **_fence) -> None:
        self.ids.append(task_id)


def test_upgrade_0003_backfills_existing_dispatch_and_response(tmp_path):
    database = tmp_path / "upgrade.db"
    url = f"sqlite:///{database}"
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", url)
    command.upgrade(config, "0003_core_capabilities")
    engine = create_engine(url)
    now = utc_now()
    base = {
        "task_type": "media_probe",
        "caller": "narrato-api",
        "caller_task_id": None,
        "idempotency_key": "legacy",
        "request_digest": "0" * 64,
        "input_snapshot": "{}",
        "phase": None,
        "progress": 0,
        "current_attempt_no": 0,
        "max_retries": 3,
        "error": None,
        "result": None,
        "created_at": now,
        "updated_at": now,
        "started_at": None,
        "finished_at": None,
    }
    with engine.begin() as connection:
        for task_id, status, version in (
            ("ctask_legacy_queued", "queued", 0),
            ("ctask_legacy_retry", "retry_wait", 2),
            ("ctask_legacy_running", "running", 1),
        ):
            connection.execute(
                text(
                    """INSERT INTO core_tasks
                    (id, task_type, caller, caller_task_id, idempotency_scope,
                     idempotency_key, request_digest, input_snapshot, status, phase,
                     progress, state_version, current_attempt_no, max_retries, error,
                     result, created_at, updated_at, started_at, finished_at)
                    VALUES (:id, :task_type, :caller, :caller_task_id, :scope,
                     :idempotency_key, :request_digest, :input_snapshot, :status, :phase,
                     :progress, :version, :current_attempt_no, :max_retries, :error,
                     :result, :created_at, :updated_at, :started_at, :finished_at)"""
                ),
                {
                    **base,
                    "id": task_id,
                    "scope": task_id,
                    "status": status,
                    "version": version,
                },
            )
        connection.execute(
            text(
                """INSERT INTO core_task_attempts
                (id, core_task_id, attempt_no, status, lease_token, lease_version,
                 lease_expires_at, heartbeat_at, started_at, finished_at, error,
                 late_result_audit)
                VALUES ('attempt_legacy', 'ctask_legacy_running', 1, 'running',
                 'token', 1, :expired, :expired, :expired, NULL, NULL, NULL)"""
            ),
            {"expired": now - timedelta(minutes=5)},
        )
        connection.execute(
            text(
                "UPDATE core_tasks SET current_attempt_no=1 WHERE id='ctask_legacy_running'"
            )
        )

    command.upgrade(config, "head")
    with Session(engine, expire_on_commit=False) as session:
        rows = session.scalars(select(CoreDispatchOutbox)).all()
        assert {(row.core_task_id, row.state_version) for row in rows} == {
            ("ctask_legacy_queued", 0),
            ("ctask_legacy_retry", 2),
        }
        for task_id in (
            "ctask_legacy_queued",
            "ctask_legacy_retry",
            "ctask_legacy_running",
        ):
            task = session.get(CoreTask, task_id)
            assert task.initial_response == {
                "core_task_id": task_id,
                "status": "queued",
            }
        recorder = Recorder()
        assert (
            DispatchOutboxPublisher(session).publish_pending(
                recorder, now=now + timedelta(seconds=1)
            )
            == 2
        )
        assert set(recorder.ids) == {"ctask_legacy_queued", "ctask_legacy_retry"}
        assert TaskRecoveryScanner(session, retry_delay_seconds=0).recover(now=now) == 1
        running = session.get(CoreTask, "ctask_legacy_running")
        assert running.status == CoreTaskStatus.RETRY_WAIT
