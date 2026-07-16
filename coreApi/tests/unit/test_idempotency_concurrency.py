from __future__ import annotations

import threading

from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session

from core_api.database import Base
from core_api.tasks.models import CoreTask
from core_api.tasks.service import IdempotencyConflictError, TaskService


def _race_create(tmp_path, payloads):
    engine = create_engine(
        f"sqlite+pysqlite:///{tmp_path / 'idempotency-race.db'}",
        connect_args={"check_same_thread": False, "timeout": 10},
    )
    with engine.begin() as connection:
        connection.exec_driver_sql("PRAGMA journal_mode=WAL")
    Base.metadata.create_all(engine)

    barrier = threading.Barrier(2)
    synchronized_threads: set[int] = set()
    guard = threading.Lock()

    def synchronize_initial_lookup(
        _connection, _cursor, statement, _parameters, _context, _many
    ):
        if not (
            statement.lstrip().upper().startswith("SELECT")
            and "FROM core_tasks" in statement
            and "core_tasks.idempotency_scope" in statement
        ):
            return
        identity = threading.get_ident()
        with guard:
            if identity in synchronized_threads:
                return
            synchronized_threads.add(identity)
        barrier.wait(timeout=5)

    event.listen(engine, "after_cursor_execute", synchronize_initial_lookup)
    results: list[CoreTask] = []
    errors: list[BaseException] = []

    def create(payload):
        with Session(engine, expire_on_commit=False) as session:
            try:
                task = TaskService(session).create_core_task(
                    caller="narrato-api",
                    route="/api/v1/tasks/asr",
                    task_type="asr",
                    idempotency_key="concurrent-key",
                    input_snapshot=payload,
                )
                with guard:
                    results.append(task)
            except BaseException as exc:
                session.rollback()
                with guard:
                    errors.append(exc)

    threads = [threading.Thread(target=create, args=(payload,)) for payload in payloads]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=15)
        assert not thread.is_alive()
    with Session(engine) as session:
        persisted = session.scalar(select(func.count(CoreTask.id)))
    return results, errors, persisted


def test_concurrent_identical_create_returns_first_task(tmp_path):
    """并发同体请求的 loser 回读并返回首次任务。"""

    results, errors, persisted = _race_create(
        tmp_path, [{"asset": "asset_1"}, {"asset": "asset_1"}]
    )
    assert errors == []
    assert len(results) == 2
    assert results[0].id == results[1].id
    assert persisted == 1


def test_concurrent_changed_create_returns_stable_conflict(tmp_path):
    """并发异体请求的 loser 返回稳定幂等冲突而非 IntegrityError。"""

    results, errors, persisted = _race_create(
        tmp_path, [{"asset": "asset_1"}, {"asset": "asset_2"}]
    )
    assert len(results) == 1
    assert len(errors) == 1
    assert isinstance(errors[0], IdempotencyConflictError)
    assert str(errors[0]) == "IDEMPOTENCY_CONFLICT"
    assert persisted == 1
