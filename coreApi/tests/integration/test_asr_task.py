from __future__ import annotations

from pathlib import Path
from datetime import timedelta
import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy import create_engine, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from core_api.adapters.narrato.asr import AsrAdapter
from core_api.api.routes.tasks import get_task_dispatcher
from core_api.database import Base, get_engine
from core_api.infrastructure.oss_client import DownloadReceipt, OssUploadResult
from core_api.runtime.artifact_store import ArtifactStore
from core_api.runtime.artifact_store import ArtifactSecurityError
from core_api.runtime.workspace import CoreTaskWorkspace, WorkspaceSecurityError
from core_api.tasks.handlers import AtomicTaskHandler
from core_api.tasks.models import CoreArtifact, CoreTask, CoreTaskStatus
from core_api.tasks.models import utc_now
from core_api.tasks.service import StaleLeaseError, TaskService


class RecordingDispatcher:
    def __init__(self) -> None:
        self.task_ids: list[str] = []

    def dispatch(self, task_id: str, **_fence) -> None:
        self.task_ids.append(task_id)


def test_asr_post_creates_async_task_once(app, settings):
    Base.metadata.create_all(get_engine(settings))
    dispatcher = RecordingDispatcher()
    app.dependency_overrides[get_task_dispatcher] = lambda: dispatcher
    body = {
        "source_url": "https://cdn.example.test/narrato/api/audio.mp4",
        "declared_extension": "mp4",
        "caller_task_id": "node_asr_01",
    }
    headers = {
        "Authorization": "Bearer test-service-token",
        "X-Idempotency-Key": "asr-idem",
    }
    with TestClient(app) as client:
        first = client.post("/api/v1/asr/tasks", json=body, headers=headers)
        second = client.post("/api/v1/asr/tasks", json=body, headers=headers)

    assert first.status_code == second.status_code == 202
    assert first.json()["data"] == second.json()["data"]
    assert dispatcher.task_ids == [first.json()["data"]["core_task_id"]]

    with TestClient(app) as client:
        assert (
            client.post(
                "/api/v1/asr/tasks",
                json={**body, "unknown": "field"},
                headers={**headers, "X-Idempotency-Key": "asr-unknown"},
            ).status_code
            == 422
        )
        assert (
            client.post(
                "/api/v1/asr/tasks",
                json=body,
                headers={**headers, "X-Idempotency-Key": "\t "},
            ).status_code
            == 422
        )


def test_asr_post_accepts_ordered_batch_sources(app, settings):
    Base.metadata.create_all(get_engine(settings))
    dispatcher = RecordingDispatcher()
    app.dependency_overrides[get_task_dispatcher] = lambda: dispatcher
    body = {
        "sources": [
            {
                "source_asset_id": "asset_a",
                "source_url": "https://cdn.example.test/narrato/api/a.mp4",
                "declared_extension": "mp4",
            },
            {
                "source_asset_id": "asset_b",
                "source_url": "https://cdn.example.test/narrato/api/b.mov",
                "declared_extension": "mov",
            },
        ],
        "caller_task_id": "node_asr_batch",
    }
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/asr/tasks",
            json=body,
            headers={
                "Authorization": "Bearer test-service-token",
                "X-Idempotency-Key": "asr-batch",
            },
        )
    assert response.status_code == 202
    with Session(get_engine(settings)) as session:
        task = session.get(CoreTask, response.json()["data"]["core_task_id"])
    assert task is not None
    assert [item["source_asset_id"] for item in task.input_snapshot["sources"]] == [
        "asset_a",
        "asset_b",
    ]


class FakeDownloader:
    def download(
        self, url: str, destination: Path, *, max_bytes: int
    ) -> DownloadReceipt:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"fake-media")
        return DownloadReceipt(url=url, size=10, content_type="video/mp4")


class FakeOss:
    public_base_url = "https://cdn.example.test"

    def __init__(self) -> None:
        self.keys: list[str] = []

    def upload_stream(
        self, stream, object_key: str, *, content_type: str, size: int
    ) -> OssUploadResult:
        assert stream.read().decode("utf-8").startswith("1\n")
        assert size > 0
        assert object_key.startswith("narrato/coreApi/") and object_key.endswith(".srt")
        self.keys.append(object_key)
        return OssUploadResult(
            bucket="core-test",
            object_key=object_key,
            url=f"https://cdn.example.test/{object_key}",
        )


def fake_transcriber(local_file: str, subtitle_file: str) -> str:
    assert Path(local_file).read_bytes() == b"fake-media"
    Path(subtitle_file).write_text(
        "1\n00:00:00,000 --> 00:00:01,000\nhello\n", encoding="utf-8"
    )
    return subtitle_file


def test_asr_handler_uploads_and_registers_srt_artifact(session, tmp_path):
    task_service = TaskService(session)
    task = task_service.create_core_task(
        caller="narrato-api",
        route="/api/v1/asr/tasks",
        task_type="asr",
        idempotency_key="handler-asr",
        input_snapshot={
            "source_url": "https://cdn.example.test/narrato/api/audio.mp4",
            "declared_extension": "mp4",
        },
    )
    fake_oss = FakeOss()
    handler = AtomicTaskHandler(
        task_service=task_service,
        work_root=tmp_path / "work",
        asr_adapter=AsrAdapter(
            downloader=FakeDownloader(),
            transcriber=fake_transcriber,
            artifact_store=ArtifactStore(fake_oss),
        ),
    )

    handler.run(task.id)

    finished = task_service.get_task(task.id)
    assert finished.status == CoreTaskStatus.SUCCEEDED
    artifact = finished.result["artifacts"][0]
    assert artifact["kind"] == "subtitle"
    assert artifact["object_key"] == fake_oss.keys[0]
    assert "local_path" not in artifact and "/private/" not in str(artifact)
    row = session.scalar(
        select(CoreArtifact).where(CoreArtifact.core_task_id == task.id)
    )
    assert row is not None and row.object_key == artifact["object_key"]


def test_asr_handler_returns_subtitle_artifact_for_each_source(session, tmp_path):
    task_service = TaskService(session)
    task = task_service.create_core_task(
        caller="narrato-api",
        route="/api/v1/asr/tasks",
        task_type="asr",
        idempotency_key="handler-asr-batch",
        input_snapshot={
            "sources": [
                {
                    "source_asset_id": "asset_a",
                    "source_url": "https://cdn.example.test/narrato/api/a.mp4",
                    "declared_extension": "mp4",
                },
                {
                    "source_asset_id": "asset_b",
                    "source_url": "https://cdn.example.test/narrato/api/b.mp4",
                    "declared_extension": "mp4",
                },
            ]
        },
    )
    handler = AtomicTaskHandler(
        task_service=task_service,
        work_root=tmp_path / "work-batch",
        asr_adapter=AsrAdapter(
            downloader=FakeDownloader(),
            transcriber=fake_transcriber,
            artifact_store=ArtifactStore(FakeOss()),
        ),
    )
    handler.run(task.id)
    result = task_service.get_task(task.id).result
    assert [item["source_asset_id"] for item in result["subtitles"]] == [
        "asset_a",
        "asset_b",
    ]
    assert len(result["artifacts"]) == 2
    assert all(item["artifact"]["kind"] == "subtitle" for item in result["subtitles"])


@pytest.mark.parametrize(
    "srt", ["", "invalid", "1\n00:00:02,000 --> 00:00:01,000\nbad\n"]
)
def test_asr_handler_rejects_empty_or_invalid_srt(session, tmp_path, srt):
    task_service = TaskService(session)
    task = task_service.create_core_task(
        caller="narrato-api",
        route="/api/v1/asr/tasks",
        task_type="asr",
        idempotency_key=f"invalid-asr-{len(srt)}-{srt[:1]}",
        input_snapshot={
            "source_url": "https://cdn.example.test/narrato/api/audio.mp4",
            "declared_extension": "mp4",
        },
    )

    def broken_transcriber(local_file: str, subtitle_file: str) -> str:
        Path(subtitle_file).write_text(srt, encoding="utf-8")
        return subtitle_file

    handler = AtomicTaskHandler(
        task_service=task_service,
        work_root=tmp_path / "work",
        asr_adapter=AsrAdapter(
            downloader=FakeDownloader(),
            transcriber=broken_transcriber,
            artifact_store=ArtifactStore(FakeOss()),
        ),
    )
    handler.run(task.id)

    failed = task_service.get_task(task.id)
    assert failed.status == CoreTaskStatus.FAILED
    assert failed.error["code"] == "ASR_INVALID_SRT"
    assert failed.error["retryable"] is False


def test_stale_attempt_cannot_register_artifact(session):
    service = TaskService(session)
    task = service.create_core_task(
        caller="narrato-api",
        route="/api/v1/asr/tasks",
        task_type="asr",
        idempotency_key="stale-asr-artifact",
        input_snapshot={"source_url": "https://cdn.example.test/narrato/api/a.mp4"},
    )
    old = service.start_attempt(task.id, lease_seconds=1)
    service.expire_and_restart(old.id, now=utc_now() + timedelta(seconds=2))
    result = {
        "artifacts": [
            {
                "artifact_id": "art_stale",
                "kind": "subtitle",
                "bucket": "core-test",
                "object_key": "narrato/coreApi/2026/07/17/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.srt",
                "url": "https://cdn.example.test/stale.srt",
                "content_type": "application/x-subrip",
                "size": 1,
                "checksum": None,
            }
        ]
    }

    with pytest.raises(StaleLeaseError):
        service.complete_attempt(
            old.id,
            old.lease_token,
            result,
            lease_version=old.lease_version,
        )

    assert (
        session.scalar(select(CoreArtifact).where(CoreArtifact.id == "art_stale"))
        is None
    )


def test_workspace_rejects_output_directory_replaced_by_symlink(tmp_path):
    workspace = CoreTaskWorkspace.create(tmp_path / "work", "ctask_SAFE", 1)
    outside = tmp_path / "outside"
    outside.mkdir()
    workspace.output_dir.rmdir()
    workspace.output_dir.symlink_to(outside, target_is_directory=True)

    with pytest.raises(WorkspaceSecurityError):
        workspace.controlled_path("output", "subtitle", "srt")


def test_artifact_store_uses_opened_regular_file_when_path_is_replaced(tmp_path):
    workspace = CoreTaskWorkspace.create(tmp_path / "work", "ctask_RACE", 1)
    target = workspace.controlled_path("output", "subtitle", "srt")
    safe_content = b"1\n00:00:00,000 --> 00:00:01,000\nsafe\n"
    target.write_bytes(safe_content)
    outside = tmp_path / "secret.txt"
    outside.write_bytes(b"SECRET-OUTSIDE")

    class RacingOss:
        public_base_url = "https://cdn.test"
        uploaded = b""

        def upload_stream(self, stream, object_key, *, content_type, size):
            target.unlink()
            target.symlink_to(outside)
            self.uploaded = stream.read()
            return OssUploadResult(
                "bucket", object_key, f"https://cdn.test/{object_key}"
            )

    oss = RacingOss()
    artifact = ArtifactStore(oss).upload(
        workspace=workspace,
        local_path=target,
        core_task_id="ctask_RACE",
        attempt_no=1,
        kind="subtitle",
    )
    assert oss.uploaded == safe_content
    assert artifact.size == len(safe_content)


def test_artifact_store_rejects_file_symlink(tmp_path):
    workspace = CoreTaskWorkspace.create(tmp_path / "work", "ctask_LINK", 1)
    outside = tmp_path / "outside.srt"
    outside.write_text("secret", encoding="utf-8")
    target = workspace.output_dir / "subtitle.srt"
    target.symlink_to(outside)
    with pytest.raises(ArtifactSecurityError):
        ArtifactStore(FakeOss()).upload(
            workspace=workspace,
            local_path=target,
            core_task_id="ctask_LINK",
            attempt_no=1,
            kind="subtitle",
        )


def test_asr_fences_lease_before_oss_upload(tmp_path):
    workspace = CoreTaskWorkspace.create(tmp_path / "work", "ctask_FENCE", 1)
    oss = FakeOss()
    adapter = AsrAdapter(
        downloader=FakeDownloader(),
        transcriber=fake_transcriber,
        artifact_store=ArtifactStore(oss),
    )

    def stale_guard() -> None:
        raise StaleLeaseError("STALE_LEASE")

    with pytest.raises(StaleLeaseError):
        adapter.run(
            source_url="https://cdn.example.test/narrato/api/audio.mp4",
            declared_extension="mp4",
            core_task_id="ctask_FENCE",
            attempt_no=1,
            workspace=workspace,
            lease_guard=stale_guard,
        )
    assert oss.keys == []


def test_handler_pumps_periodic_heartbeat_during_long_adapter(session, tmp_path):
    task_service = TaskService(session)
    task = task_service.create_core_task(
        caller="narrato-api",
        route="/api/v1/media-probe/tasks",
        task_type="media_probe",
        idempotency_key="periodic-heartbeat",
        input_snapshot={"source_url": "https://cdn.example.test/narrato/api/a.mp4"},
    )
    heartbeat_calls: list[int] = []

    def heartbeat_once(attempt_id, token, version, lease_seconds):
        heartbeat_calls.append(version)

    class SlowAdapter:
        def run(self, **kwargs):
            time.sleep(0.16)
            return {"media_type": "video"}

    handler = AtomicTaskHandler(
        task_service=task_service,
        work_root=tmp_path / "work",
        media_probe_adapter=SlowAdapter(),
        heartbeat_once=heartbeat_once,
        heartbeat_interval_seconds=0.04,
    )
    handler.run(task.id)

    assert len(heartbeat_calls) >= 2
    assert task_service.get_task(task.id).status == CoreTaskStatus.SUCCEEDED


def test_independent_heartbeat_keeps_task_alive_beyond_original_lease(tmp_path):
    from core_api.database import Base
    from sqlalchemy.orm import Session

    engine = create_engine(f"sqlite:///{tmp_path / 'heartbeat.db'}")

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as main_session:
        service = TaskService(main_session)
        task = service.create_core_task(
            caller="narrato-api",
            route="/api/v1/media-probe/tasks",
            task_type="media_probe",
            idempotency_key="heartbeat-over-lease",
            input_snapshot={"source_url": "https://cdn.example.test/narrato/api/a.mp4"},
        )

        def independent_heartbeat(attempt_id, token, version, lease_seconds):
            with Session(engine, expire_on_commit=False) as heartbeat_session:
                TaskService(heartbeat_session).heartbeat(
                    attempt_id, token, version, lease_seconds=lease_seconds
                )

        class SlowAdapter:
            def run(self, **kwargs):
                time.sleep(0.25)
                return {"media_type": "video"}

        handler = AtomicTaskHandler(
            task_service=service,
            work_root=tmp_path / "work-real-heartbeat",
            media_probe_adapter=SlowAdapter(),
            lease_seconds=0.12,
            heartbeat_once=independent_heartbeat,
            heartbeat_interval_seconds=0.03,
        )
        handler.run(task.id)
        main_session.expire_all()
        assert service.get_task(task.id).status == CoreTaskStatus.SUCCEEDED


def test_artifact_database_rejects_unknown_attempt_and_nonpositive_size(session):
    service = TaskService(session)
    task = service.create_core_task(
        caller="narrato-api",
        route="/api/v1/asr/tasks",
        task_type="asr",
        idempotency_key="artifact-constraints",
        input_snapshot={"source_url": "https://cdn.example.test/narrato/api/a.mp4"},
    )
    attempt = service.start_attempt(task.id)
    common = {
        "core_task_id": task.id,
        "kind": "subtitle",
        "bucket": "bucket",
        "url": "https://cdn.example.test/a.srt",
        "content_type": "application/x-subrip",
        "checksum": None,
    }
    session.add(
        CoreArtifact(
            id="art_bad_attempt",
            attempt_no=999,
            object_key="narrato/coreApi/bad-attempt.srt",
            size=1,
            **common,
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()

    session.add(
        CoreArtifact(
            id="art_bad_size",
            attempt_no=attempt.attempt_no,
            object_key="narrato/coreApi/bad-size.srt",
            size=0,
            **common,
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()
