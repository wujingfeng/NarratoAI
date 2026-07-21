from __future__ import annotations

from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor
import asyncio
import threading
import time

import httpx
from sqlalchemy import func, select

import pytest

from core_api.tasks.callbacks import (
    CallbackDeliveryResult,
    HttpCallbackClient,
    CallbackOutboxPublisher,
    OutboxEventConflictError,
)
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
    """租约过期只写 retry_wait；新 running 必须由到期 wake 领取。"""

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


class RecordingCallbackClient:
    """记录回调并允许注入稳定投递结果。"""

    def __init__(self, *results: CallbackDeliveryResult) -> None:
        self.results = list(results)
        self.events: list[dict[str, object]] = []

    def deliver(self, event: dict[str, object]) -> CallbackDeliveryResult:
        self.events.append(event)
        return self.results.pop(0)


def test_callback_publisher_claims_before_network_and_retries_with_backoff(
    session, task_service, task
):
    """网络调用前先持久 claim，临时失败按指数退避重试。"""

    task_service.mark_succeeded(task.id, event_id="evt_retry")
    now = utc_now()
    client = RecordingCallbackClient(CallbackDeliveryResult.RETRY)
    publisher = CallbackOutboxPublisher(
        session, base_backoff_seconds=2, minimum_claim_seconds=0
    )

    assert publisher.publish_pending(client, now=now) == 0
    row = session.scalar(select(CallbackOutbox))
    assert row is not None
    assert row.attempt_count == 1
    assert row.next_attempt_at.replace(tzinfo=now.tzinfo) == now + timedelta(seconds=2)
    assert row.status.value == "pending"
    assert client.events == [row.payload]
    assert publisher.publish_pending(client, now=now) == 0
    assert len(client.events) == 1


def test_callback_publisher_keeps_4xx_pending_until_receiver_recovers(
    session, task_service, task
):
    """接收端拒绝不得伪装 sent，配置修复后仍可重放。"""

    task_service.mark_succeeded(task.id, event_id="evt_sent")
    client = RecordingCallbackClient(CallbackDeliveryResult.RETRY)
    now = utc_now()

    publisher = CallbackOutboxPublisher(
        session, base_backoff_seconds=1, minimum_claim_seconds=0
    )
    assert publisher.publish_pending(client, now=now) == 0
    row = session.scalar(select(CallbackOutbox))
    assert row is not None
    assert row.status.value == "pending"
    assert row.sent_at is None
    recovered = RecordingCallbackClient(CallbackDeliveryResult.SUCCESS)
    assert publisher.publish_pending(recovered, now=now + timedelta(seconds=1)) == 1
    session.refresh(row)
    assert row.status.value == "sent"


def test_callback_publisher_limit_is_fair(session, task_service):
    """有限批次按到期时间稳定推进，不在同一事件上热循环。"""

    for index in range(3):
        item = task_service.create_core_task(
            caller="narrato-api",
            route="/api/v1/tasks/asr",
            task_type="asr",
            idempotency_key=f"callback-fair-{index}",
            input_snapshot={"asset": str(index)},
        )
        task_service.mark_succeeded(item.id, event_id=f"evt_fair_{index}")
    client = RecordingCallbackClient(
        CallbackDeliveryResult.RETRY,
        CallbackDeliveryResult.RETRY,
        CallbackDeliveryResult.RETRY,
    )
    publisher = CallbackOutboxPublisher(session)
    now = utc_now()

    publisher.publish_pending(client, now=now, limit=2)
    publisher.publish_pending(client, now=now, limit=2)

    assert {event["event_id"] for event in client.events} == {
        "evt_fair_0",
        "evt_fair_1",
        "evt_fair_2",
    }


def test_callback_publisher_replays_after_process_crash(session, task_service, task):
    """网络调用时进程退出后，持久 claim 到期可安全重复投递。"""

    task_service.mark_succeeded(task.id, event_id="evt_crash")
    now = utc_now()

    class CrashClient:
        def deliver(self, event: dict[str, object]) -> CallbackDeliveryResult:
            raise SystemExit("worker lost")

    with pytest.raises(SystemExit, match="worker lost"):
        CallbackOutboxPublisher(
            session, base_backoff_seconds=1, minimum_claim_seconds=0
        ).publish_pending(CrashClient(), now=now)
    row = session.scalar(select(CallbackOutbox))
    assert row is not None and row.attempt_count == 1 and row.status.value == "pending"
    replay = RecordingCallbackClient(CallbackDeliveryResult.SUCCESS)
    assert (
        CallbackOutboxPublisher(session).publish_pending(
            replay, now=now + timedelta(seconds=1)
        )
        == 1
    )
    assert replay.events[0]["event_id"] == "evt_crash"


def test_two_publishers_atomically_claim_one_event(tmp_path):
    """两个独立 Session 同时扫描时同轮只有一个网络调用。"""

    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from core_api.database import Base
    from core_api.tasks.service import TaskService

    engine = create_engine(
        f"sqlite:///{tmp_path / 'callback.db'}",
        connect_args={"check_same_thread": False, "timeout": 5},
    )
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as seed:
        service = TaskService(seed)
        item = service.create_core_task(
            caller="narrato-api",
            route="/probe",
            task_type="asr",
            idempotency_key="callback-concurrent",
            input_snapshot={"asset": "one"},
        )
        service.mark_succeeded(item.id, event_id="evt_concurrent")
    lock = threading.Lock()
    delivered: list[str] = []

    class ConcurrentClient:
        def deliver(self, event: dict[str, object]) -> CallbackDeliveryResult:
            with lock:
                delivered.append(str(event["event_id"]))
            return CallbackDeliveryResult.SUCCESS

    def publish() -> int:
        with Session(engine, expire_on_commit=False) as current:
            return CallbackOutboxPublisher(current).publish_pending(ConcurrentClient())

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _index: publish(), range(2)))
    assert sorted(results) == [0, 1]
    assert delivered == ["evt_concurrent"]


def test_claim_heartbeat_prevents_second_publisher_during_slow_delivery(tmp_path):
    """慢投递跨过初始 claim 时限后，心跳仍须阻止第二个 Publisher 重复认领。"""

    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from core_api.database import Base
    from core_api.tasks.service import TaskService

    engine = create_engine(
        f"sqlite:///{tmp_path / 'callback-heartbeat.db'}",
        connect_args={"check_same_thread": False, "timeout": 5},
    )
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as seed:
        service = TaskService(seed)
        item = service.create_core_task(
            caller="narrato-api",
            route="/probe",
            task_type="asr",
            idempotency_key="callback-heartbeat",
            input_snapshot={"asset": "one"},
        )
        service.mark_succeeded(item.id, event_id="evt_heartbeat")

    entered = threading.Event()
    release = threading.Event()
    delivered: list[str] = []
    baseline_heartbeat_threads = {
        thread.ident
        for thread in threading.enumerate()
        if thread.name.startswith("core-callback-claim-")
    }

    class SlowClient:
        def deliver(self, event: dict[str, object]) -> CallbackDeliveryResult:
            delivered.append(str(event["event_id"]))
            entered.set()
            assert release.wait(timeout=2)
            return CallbackDeliveryResult.SUCCESS

    class DuplicateClient:
        def deliver(self, event: dict[str, object]) -> CallbackDeliveryResult:
            delivered.append(f"duplicate:{event['event_id']}")
            return CallbackDeliveryResult.SUCCESS

    def publish_slow() -> int:
        with Session(engine, expire_on_commit=False) as current:
            return CallbackOutboxPublisher(
                current,
                base_backoff_seconds=0.05,
                minimum_claim_seconds=0.05,
            ).publish_pending(SlowClient())

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(publish_slow)
        assert entered.wait(timeout=2)
        time.sleep(0.12)
        with Session(engine, expire_on_commit=False) as second:
            duplicate_result = CallbackOutboxPublisher(
                second,
                base_backoff_seconds=0.05,
                minimum_claim_seconds=0.05,
            ).publish_pending(DuplicateClient())
        release.set()
        assert future.result(timeout=2) == 1

    assert duplicate_result == 0
    assert delivered == ["evt_heartbeat"]
    assert {
        thread.ident
        for thread in threading.enumerate()
        if thread.name.startswith("core-callback-claim-")
    } == baseline_heartbeat_threads


def test_heartbeat_database_failure_keeps_successful_delivery_pending(tmp_path):
    """claim 心跳数据库失败时，即使 HTTP 成功也不得写 SENT。"""

    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from core_api.database import Base
    from core_api.tasks.service import TaskService

    engine = create_engine(f"sqlite:///{tmp_path / 'callback-heartbeat-failure.db'}")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as seed:
        service = TaskService(seed)
        item = service.create_core_task(
            caller="narrato-api",
            route="/probe",
            task_type="asr",
            idempotency_key="callback-heartbeat-failure",
            input_snapshot={"asset": "one"},
        )
        service.mark_succeeded(item.id, event_id="evt_heartbeat_failure")

    def broken_heartbeat_session():
        raise RuntimeError("heartbeat database unavailable")

    with Session(engine, expire_on_commit=False) as current:
        completed = CallbackOutboxPublisher(
            current,
            minimum_claim_seconds=0.05,
            heartbeat_session_factory=broken_heartbeat_session,
        ).publish_pending(RecordingCallbackClient(CallbackDeliveryResult.SUCCESS))
        row = current.scalar(select(CallbackOutbox))

    assert completed == 0
    assert row is not None
    assert row.status.value == "pending"
    assert row.sent_at is None


def test_late_http_success_remains_pending_in_outbox(session, task_service, task):
    """超出总时限后才返回的 204 不能让持久 Outbox 进入 SENT。"""

    class CancellationResistantTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            try:
                await asyncio.sleep(0.14)
            except asyncio.CancelledError:
                await asyncio.sleep(0.12)
            return httpx.Response(204, request=request)

    task_service.mark_succeeded(task.id, event_id="evt_late_pending")
    client = HttpCallbackClient(
        "https://narrato.example.test/callback",
        "private-token",
        total_timeout=0.02,
        transport=CancellationResistantTransport(),
    )
    publisher = CallbackOutboxPublisher(
        session,
        base_backoff_seconds=0.01,
        minimum_claim_seconds=0,
    )

    assert publisher.publish_pending(client) == 0
    row = session.scalar(select(CallbackOutbox))
    assert row is not None
    assert row.status.value == "pending"
    assert row.sent_at is None


def test_claim_heartbeat_never_shortens_persisted_retry_backoff(
    session, task_service, task
):
    """心跳只能延长 claim，不得把高 attempt 的指数退避缩短为租约长度。"""

    task_service.mark_succeeded(task.id, event_id="evt_long_backoff")
    row = session.scalar(select(CallbackOutbox))
    assert row is not None
    row.attempt_count = 10
    session.commit()
    observed_at = utc_now()

    class SlowRetryClient:
        def deliver(self, event: dict[str, object]) -> CallbackDeliveryResult:
            time.sleep(0.05)
            return CallbackDeliveryResult.RETRY

    publisher = CallbackOutboxPublisher(
        session,
        base_backoff_seconds=5,
        max_backoff_seconds=3600,
        minimum_claim_seconds=0.3,
    )

    assert publisher.publish_pending(SlowRetryClient(), now=observed_at) == 0
    session.expire_all()
    persisted = session.get(CallbackOutbox, row.id)
    assert persisted is not None
    next_attempt_at = persisted.next_attempt_at.replace(tzinfo=observed_at.tzinfo)
    assert next_attempt_at >= observed_at + timedelta(seconds=3599)
