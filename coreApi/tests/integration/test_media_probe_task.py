from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from core_api.adapters.narrato.media_probe import MediaProbeAdapter
from core_api.api.routes.tasks import get_task_dispatcher
from core_api.database import Base, get_engine
from core_api.infrastructure.oss_client import DownloadReceipt
from core_api.tasks.handlers import AtomicTaskHandler
from core_api.tasks.dispatch import DispatchOutboxPublisher
from core_api.tasks.models import (
    CallbackOutbox,
    CoreDispatchOutbox,
    CoreTask,
    CoreTaskStatus,
    DispatchStatus,
)
from core_api.tasks.service import TaskService


AUTH = {"Authorization": "Bearer test-service-token", "X-Idempotency-Key": "idem-1"}


class RecordingDispatcher:
    def __init__(self) -> None:
        self.task_ids: list[str] = []

    def dispatch(self, task_id: str, **_fence) -> None:
        self.task_ids.append(task_id)


class FailingDispatcher(RecordingDispatcher):
    def dispatch(self, task_id: str, **_fence) -> None:
        self.task_ids.append(task_id)
        raise RuntimeError("broker unavailable with secret body")


class FixtureDownloader:
    def __init__(self, source: Path) -> None:
        self.source = source

    def download(
        self, url: str, destination: Path, *, max_bytes: int
    ) -> DownloadReceipt:
        assert url.startswith("https://cdn.example.test/narrato/api/")
        assert self.source.stat().st_size <= max_bytes
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(self.source, destination)
        return DownloadReceipt(
            url=url, size=destination.stat().st_size, content_type="video/mp4"
        )


@pytest.fixture
def api_client(app, settings):
    Base.metadata.create_all(get_engine(settings))
    dispatcher = RecordingDispatcher()
    app.dependency_overrides[get_task_dispatcher] = lambda: dispatcher
    with TestClient(app) as client:
        yield client, dispatcher


def test_media_probe_post_requires_auth_and_idempotency(api_client):
    client, _ = api_client
    body = {
        "source_url": "https://cdn.example.test/narrato/api/video.mp4",
        "media_type": "video",
        "declared_extension": "mp4",
    }
    assert client.post("/api/v1/media-probe/tasks", json=body).status_code == 401
    response = client.post(
        "/api/v1/media-probe/tasks",
        headers={"Authorization": AUTH["Authorization"]},
        json=body,
    )
    assert response.status_code == 422

    rejected = client.post(
        "/api/v1/media-probe/tasks",
        headers=AUTH,
        json={**body, "source_url": "/private/tmp/local.mp4"},
    )
    assert rejected.status_code == 422
    assert rejected.json()["code"] == "SOURCE_URL_REJECTED"

    blank_key = client.post(
        "/api/v1/media-probe/tasks",
        headers={"Authorization": AUTH["Authorization"], "X-Idempotency-Key": "   "},
        json=body,
    )
    assert blank_key.status_code == 422

    unknown = client.post(
        "/api/v1/media-probe/tasks",
        headers={**AUTH, "X-Idempotency-Key": "unknown-field"},
        json={**body, "provider_private_field": "ignored-before"},
    )
    assert unknown.status_code == 422


def test_media_probe_post_is_202_idempotent_and_dispatches_once(api_client):
    client, dispatcher = api_client
    body = {
        "source_url": "https://cdn.example.test/narrato/api/video.mp4",
        "media_type": "video",
        "declared_extension": "mp4",
        "caller_task_id": "asset_01",
    }
    first = client.post("/api/v1/media-probe/tasks", headers=AUTH, json=body)
    task_id = first.json()["data"]["core_task_id"]
    # 幂等 POST 必须返回首次 202 快照，而不是重放时的当前运行状态。
    with Session(get_engine(api_client[0].app.state.settings)) as database:
        TaskService(database).start_attempt(task_id)
    second = client.post("/api/v1/media-probe/tasks", headers=AUTH, json=body)

    assert first.status_code == second.status_code == 202
    assert first.json()["code"] == "TASK_CREATED"
    assert first.json()["data"] == second.json()["data"]
    assert first.json()["data"]["status"] == "queued"
    assert dispatcher.task_ids == [task_id]

    status = client.get(
        f"/api/v1/tasks/{task_id}", headers={"Authorization": AUTH["Authorization"]}
    )
    assert status.status_code == 200
    assert status.json()["data"]["artifacts"] == []


def test_dispatch_outbox_recovers_first_broker_failure(app, settings):
    Base.metadata.create_all(get_engine(settings))
    failing = FailingDispatcher()
    app.dependency_overrides[get_task_dispatcher] = lambda: failing
    body = {
        "source_url": "https://cdn.example.test/narrato/api/video.mp4",
        "media_type": "video",
        "declared_extension": "mp4",
    }
    headers = {**AUTH, "X-Idempotency-Key": "broker-recovery"}
    with TestClient(app) as client:
        first = client.post("/api/v1/media-probe/tasks", headers=headers, json=body)
    assert first.status_code == 202
    task_id = first.json()["data"]["core_task_id"]

    with Session(get_engine(settings), expire_on_commit=False) as database:
        row = database.scalar(
            select(CoreDispatchOutbox).where(CoreDispatchOutbox.core_task_id == task_id)
        )
        assert row is not None
        assert row.status == DispatchStatus.PENDING
        assert row.attempt_count == 1
        assert "secret body" not in str(row.last_error)

    recovered = RecordingDispatcher()
    app.dependency_overrides[get_task_dispatcher] = lambda: recovered
    with TestClient(app) as client:
        replay = client.post("/api/v1/media-probe/tasks", headers=headers, json=body)
    assert replay.status_code == 202
    assert replay.json()["data"]["core_task_id"] == task_id
    # 同 key 重放也不得绕过 Broker 失败后的持久 backoff。
    assert recovered.task_ids == []

    with Session(get_engine(settings), expire_on_commit=False) as database:
        row = database.scalar(
            select(CoreDispatchOutbox).where(CoreDispatchOutbox.core_task_id == task_id)
        )
        row.available_at = row.created_at
        database.commit()
        assert DispatchOutboxPublisher(database).publish_pending(recovered) == 1
    assert recovered.task_ids == [task_id]

    with Session(get_engine(settings), expire_on_commit=False) as database:
        row = database.scalar(
            select(CoreDispatchOutbox).where(CoreDispatchOutbox.core_task_id == task_id)
        )
        assert row.status == DispatchStatus.SENT


def test_dispatch_scanner_replays_pending_and_duplicate_wake_is_safe(session, tmp_path):
    from core_api.tasks.service import TaskService

    service = TaskService(session)
    task = service.create_core_task(
        caller="narrato-api",
        route="/api/v1/media-probe/tasks",
        task_type="media_probe",
        idempotency_key="scanner-replay",
        input_snapshot={
            "source_url": "https://cdn.example.test/narrato/api/a.mp4",
            "media_type": "video",
            "declared_extension": "mp4",
        },
    )
    dispatcher = RecordingDispatcher()
    publisher = DispatchOutboxPublisher(session)
    assert publisher.publish_pending(dispatcher) == 1
    assert publisher.publish_pending(dispatcher) == 0
    assert dispatcher.task_ids == [task.id]


def test_dispatch_publisher_crash_after_send_replays_as_safe_duplicate(session):
    from core_api.tasks.service import TaskService

    service = TaskService(session)
    task = service.create_core_task(
        caller="narrato-api",
        route="/api/v1/media-probe/tasks",
        task_type="media_probe",
        idempotency_key="publisher-crash-after-send",
        input_snapshot={},
    )
    delivered: list[str] = []

    class DeliveredThenCrash:
        def dispatch(self, task_id: str, **_fence) -> None:
            delivered.append(task_id)
            raise RuntimeError("publisher crashed after broker accepted")

    publisher = DispatchOutboxPublisher(session, failure_delay_seconds=0)
    assert publisher.publish_pending(DeliveredThenCrash()) == 0
    assert delivered == [task.id]
    recovered = RecordingDispatcher()
    assert publisher.publish_pending(recovered) == 1
    assert recovered.task_ids == [task.id]
    assert publisher.publish_pending(recovered) == 0


class FailOnceMediaAdapter:
    def __init__(self) -> None:
        self.calls = 0

    def run(self, **kwargs):
        from core_api.infrastructure.oss_client import DownloadTemporaryError

        self.calls += 1
        if self.calls == 1:
            raise DownloadTemporaryError("temporary")
        return {"media_type": "video", "duration_seconds": 1.0}


def test_retryable_failure_waits_for_due_dispatch_then_succeeds(session, tmp_path):
    from core_api.tasks.service import TaskService

    service = TaskService(session)
    task = service.create_core_task(
        caller="narrato-api",
        route="/api/v1/media-probe/tasks",
        task_type="media_probe",
        idempotency_key="retry-then-success",
        input_snapshot={
            "source_url": "https://cdn.example.test/narrato/api/a.mp4",
            "media_type": "video",
            "declared_extension": "mp4",
        },
    )
    # 初次 dispatch 已由测试 publisher 视为发送成功。
    DispatchOutboxPublisher(session).publish_pending(RecordingDispatcher())
    adapter = FailOnceMediaAdapter()
    handler = AtomicTaskHandler(
        task_service=service,
        work_root=tmp_path / "work",
        media_probe_adapter=adapter,
    )
    handler.run(task.id)
    retrying = service.get_task(task.id)
    assert retrying.status == CoreTaskStatus.RETRY_WAIT
    assert retrying.current_attempt_no == 1
    assert [(item.attempt_no, item.status.value) for item in retrying.attempts] == [
        (1, "failed")
    ]

    pending = session.scalar(
        select(CoreDispatchOutbox).where(
            CoreDispatchOutbox.core_task_id == task.id,
            CoreDispatchOutbox.status == DispatchStatus.PENDING,
        )
    )
    assert pending is not None and pending.available_at > pending.created_at
    pending.available_at = pending.created_at
    session.commit()
    dispatched = RecordingDispatcher()
    assert DispatchOutboxPublisher(session).publish_pending(dispatched) == 1
    assert dispatched.task_ids == [task.id]

    handler.run(task.id)
    assert adapter.calls == 2
    assert service.get_task(task.id).status == CoreTaskStatus.SUCCEEDED
    handler.run(task.id)
    assert adapter.calls == 2


def test_retryable_failure_exhausts_after_initial_plus_three_retries(session, tmp_path):
    from core_api.infrastructure.oss_client import DownloadTemporaryError
    from core_api.tasks.service import TaskService

    class AlwaysTemporary:
        def run(self, **kwargs):
            raise DownloadTemporaryError("temporary")

    service = TaskService(session)
    task = service.create_core_task(
        caller="narrato-api",
        route="/api/v1/media-probe/tasks",
        task_type="media_probe",
        idempotency_key="retry-exhaustion-handler",
        input_snapshot={"source_url": "https://cdn.example.test/narrato/api/a.mp4"},
    )
    publisher = DispatchOutboxPublisher(session)
    publisher.publish_pending(RecordingDispatcher())
    handler = AtomicTaskHandler(
        task_service=service,
        work_root=tmp_path / "retry-exhaustion",
        media_probe_adapter=AlwaysTemporary(),
    )
    for expected_attempt in range(1, 5):
        handler.run(task.id)
        current = service.get_task(task.id)
        assert current.current_attempt_no == expected_attempt
        if expected_attempt < 4:
            assert current.status == CoreTaskStatus.RETRY_WAIT
            pending = session.scalar(
                select(CoreDispatchOutbox).where(
                    CoreDispatchOutbox.core_task_id == task.id,
                    CoreDispatchOutbox.state_version == current.state_version,
                )
            )
            pending.available_at = pending.created_at
            session.commit()
            assert publisher.publish_pending(RecordingDispatcher()) == 1
    assert service.get_task(task.id).status == CoreTaskStatus.FAILED
    assert [attempt.status.value for attempt in service.get_task(task.id).attempts] == [
        "failed",
        "failed",
        "failed",
        "failed",
    ]


def test_media_probe_idempotency_conflict_and_missing_status(api_client):
    client, _ = api_client
    body = {
        "source_url": "https://cdn.example.test/narrato/api/video.mp4",
        "media_type": "video",
        "declared_extension": "mp4",
    }
    assert (
        client.post("/api/v1/media-probe/tasks", headers=AUTH, json=body).status_code
        == 202
    )
    body["source_url"] = "https://cdn.example.test/narrato/api/other.mp4"
    conflict = client.post("/api/v1/media-probe/tasks", headers=AUTH, json=body)
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "IDEMPOTENCY_CONFLICT"

    distinct_header = {**AUTH, "X-Idempotency-Key": "caller-conflict"}
    caller_body = {**body, "caller_task_id": "asset_01"}
    assert (
        client.post(
            "/api/v1/media-probe/tasks", headers=distinct_header, json=caller_body
        ).status_code
        == 202
    )
    caller_conflict = client.post(
        "/api/v1/media-probe/tasks",
        headers=distinct_header,
        json={**caller_body, "caller_task_id": "asset_02"},
    )
    assert caller_conflict.status_code == 409

    missing = client.get(
        "/api/v1/tasks/ctask_missing",
        headers={"Authorization": AUTH["Authorization"]},
    )
    assert missing.status_code == 404
    assert missing.json()["code"] == "CORE_TASK_NOT_FOUND"


def _small_video(path: Path, *, duration: float = 0.25) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"color=c=black:s=64x48:d={duration}",
            "-pix_fmt",
            "yuv420p",
            "-y",
            str(path),
        ],
        check=True,
    )


def test_media_handler_uses_real_probe_and_writes_terminal_outbox(session, tmp_path):
    from app.services.media_probe import probe_media
    from core_api.tasks.service import TaskService

    video = tmp_path / "fixture.mp4"
    _small_video(video)
    service = TaskService(session)
    task = service.create_core_task(
        caller="narrato-api",
        route="/api/v1/media-probe/tasks",
        task_type="media_probe",
        idempotency_key="handler-media",
        input_snapshot={
            "source_url": "https://cdn.example.test/narrato/api/fixture.mp4",
            "media_type": "video",
            "declared_extension": "mp4",
        },
    )
    adapter = MediaProbeAdapter(
        downloader=FixtureDownloader(video),
        probe=lambda _source: probe_media(str(video)),
    )
    handler = AtomicTaskHandler(
        task_service=service,
        work_root=tmp_path / "work",
        media_probe_adapter=adapter,
    )

    handler.run(task.id)

    assert service.get_task(task.id).status == CoreTaskStatus.SUCCEEDED
    result = service.get_task(task.id).result
    assert result["media_type"] == "video"
    assert result["duration_seconds"] > 0
    assert "/private/" not in str(result)
    outboxes = session.scalars(
        select(CallbackOutbox).where(CallbackOutbox.core_task_id == task.id)
    ).all()
    assert [row.payload["status"] for row in outboxes] == ["running", "succeeded"]


def test_media_handler_classifies_damaged_video_non_retryable(session, tmp_path):
    from app.services.media_probe import probe_media
    from core_api.tasks.service import TaskService

    damaged = tmp_path / "damaged.mp4"
    damaged.write_bytes(b"not a video")
    service = TaskService(session)
    task = service.create_core_task(
        caller="narrato-api",
        route="/api/v1/media-probe/tasks",
        task_type="media_probe",
        idempotency_key="handler-damaged",
        input_snapshot={
            "source_url": "https://cdn.example.test/narrato/api/damaged.mp4",
            "media_type": "video",
            "declared_extension": "mp4",
        },
    )
    handler = AtomicTaskHandler(
        task_service=service,
        work_root=tmp_path / "work",
        media_probe_adapter=MediaProbeAdapter(
            downloader=FixtureDownloader(damaged), probe=probe_media
        ),
    )

    handler.run(task.id)

    failed = service.get_task(task.id)
    assert failed.status == CoreTaskStatus.FAILED
    assert failed.error["code"] == "MEDIA_DAMAGED"
    assert failed.error["retryable"] is False


def test_media_handler_validates_srt_without_uploading_input(session, tmp_path):
    from core_api.tasks.service import TaskService

    subtitle = tmp_path / "fixture.srt"
    subtitle.write_text("1\n00:00:00,000 --> 00:00:01,500\n字幕\n", encoding="utf-8")
    service = TaskService(session)
    task = service.create_core_task(
        caller="narrato-api",
        route="/api/v1/media-probe/tasks",
        task_type="media_probe",
        idempotency_key="handler-srt",
        input_snapshot={
            "source_url": "https://cdn.example.test/narrato/api/fixture.srt",
            "media_type": "subtitle",
            "declared_extension": "srt",
        },
    )
    handler = AtomicTaskHandler(
        task_service=service,
        work_root=tmp_path / "work",
        media_probe_adapter=MediaProbeAdapter(
            downloader=FixtureDownloader(subtitle), probe=lambda _: None
        ),
    )

    handler.run(task.id)

    finished = service.get_task(task.id)
    assert finished.status == CoreTaskStatus.SUCCEEDED
    assert finished.result["cue_count"] == 1
    assert (
        session.scalar(select(CoreTask).where(CoreTask.id == task.id)).result.get(
            "artifacts"
        )
        is None
    )
