from sqlalchemy import select
import shutil
import wave

import pytest

from core_api.adapters.narrato.render import (
    FakeRenderBackend,
    FfmpegRenderBackend,
    RenderAdapter,
)
from core_api.adapters.narrato.tts import FakeTtsProvider
from core_api.infrastructure.oss_client import DownloadReceipt, OssUploadResult
from core_api.runtime.artifact_store import ArtifactStore
from core_api.runtime.process_runner import ProcessRunner
from core_api.tasks.handlers import AtomicTaskHandler
from core_api.tasks.callbacks import OutboxEventConflictError
from core_api.tasks.models import CoreArtifact, CoreTaskStatus
from core_api.tasks.service import TaskService


class MemoryIO:
    public_base_url = "https://cdn.example.test"

    def __init__(self):
        self.uploaded = []
        self.deleted = []

    def download(self, url, destination, *, max_bytes):
        destination.write_bytes(b"video")
        return DownloadReceipt(url, 5, "video/mp4")

    def upload_stream(self, stream, object_key, *, content_type, size):
        assert len(stream.read()) == size
        self.uploaded.append(object_key)
        return OssUploadResult(
            "fake", object_key, f"https://cdn.example.test/{object_key}"
        )

    def delete_object(self, object_key):
        self.deleted.append(object_key)


def test_render_task_duplicate_wake_registers_once(session, tmp_path):
    service = TaskService(session)
    io = MemoryIO()
    handler = AtomicTaskHandler(
        task_service=service,
        work_root=tmp_path,
        render_adapter=RenderAdapter(io, FakeRenderBackend(), ArtifactStore(io)),
    )
    task = service.create_core_task(
        caller="narrato-api",
        route="/api/v1/video-render/tasks",
        task_type="video_render",
        idempotency_key="render-1",
        input_snapshot={
            "snapshot_id": "revision_1",
            "source_order": ["asset_a"],
            "sources": [
                {
                    "source_asset_id": "asset_a",
                    "video_url": "https://cdn.example.test/narrato/api/a.mp4",
                }
            ],
            "timeline": [
                {"source_asset_id": "asset_a", "start": 0, "end": 1, "narration": "A"}
            ],
            "voice_id": "voice_fake",
            "voice_snapshot": {"voice_id": "voice_fake"},
        },
    )
    handler.run(task.id)
    handler.run(task.id)
    task = service.get_task(task.id)
    assert task.status == CoreTaskStatus.SUCCEEDED
    assert {item["kind"] for item in task.result["artifacts"]} == {
        "video",
        "subtitle",
        "voice",
        "timeline",
    }
    rows = session.scalars(
        select(CoreArtifact).where(CoreArtifact.core_task_id == task.id)
    ).all()
    assert len(rows) == 4


def test_render_compensates_all_uploads_when_terminal_transaction_fails(
    session, tmp_path, monkeypatch
):
    service = TaskService(session)
    io = MemoryIO()
    handler = AtomicTaskHandler(
        task_service=service,
        work_root=tmp_path,
        render_adapter=RenderAdapter(io, FakeRenderBackend(), ArtifactStore(io)),
    )
    task = service.create_core_task(
        caller="narrato-api",
        route="/api/v1/video-render/tasks",
        task_type="video_render",
        idempotency_key="render-db-fail",
        input_snapshot={
            "snapshot_id": "revision_1",
            "source_order": ["asset_a"],
            "sources": [
                {
                    "source_asset_id": "asset_a",
                    "video_url": "https://cdn.example.test/narrato/api/a.mp4",
                }
            ],
            "timeline": [
                {"source_asset_id": "asset_a", "start": 0, "end": 1, "narration": "A"}
            ],
            "voice_id": "voice_fake",
            "voice_snapshot": {"voice_id": "voice_fake"},
        },
    )
    monkeypatch.setattr(
        service,
        "complete_attempt",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("db failed")),
    )
    with pytest.raises(RuntimeError, match="db failed"):
        handler.run(task.id)
    assert len(io.uploaded) == 4
    assert io.deleted == list(reversed(io.uploaded))
    assert (
        session.scalars(
            select(CoreArtifact).where(CoreArtifact.core_task_id == task.id)
        ).all()
        == []
    )


def test_render_does_not_delete_objects_when_commit_succeeded_then_signal_failed(
    session, tmp_path, monkeypatch
):
    service = TaskService(session)
    io = MemoryIO()
    handler = AtomicTaskHandler(
        task_service=service,
        work_root=tmp_path,
        render_adapter=RenderAdapter(io, FakeRenderBackend(), ArtifactStore(io)),
    )
    task = service.create_core_task(
        caller="narrato-api",
        route="/api/v1/video-render/tasks",
        task_type="video_render",
        idempotency_key="render-commit-signal",
        input_snapshot={
            "snapshot_id": "revision_1",
            "source_order": ["asset_a"],
            "sources": [
                {
                    "source_asset_id": "asset_a",
                    "video_url": "https://cdn.example.test/narrato/api/a.mp4",
                }
            ],
            "timeline": [
                {"source_asset_id": "asset_a", "start": 0, "end": 1, "narration": "A"}
            ],
            "voice_id": "voice_fake",
            "voice_snapshot": {"voice_id": "voice_fake"},
        },
    )
    original = service.complete_attempt

    def complete_then_signal(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("late signal")

    monkeypatch.setattr(service, "complete_attempt", complete_then_signal)
    with pytest.raises(RuntimeError, match="late signal"):
        handler.run(task.id)
    assert service.get_task(task.id).status == CoreTaskStatus.SUCCEEDED
    assert io.deleted == []


def test_render_preserves_objects_when_commit_outcome_cannot_be_confirmed(
    session, tmp_path, monkeypatch
):
    service = TaskService(session)
    io = MemoryIO()
    handler = AtomicTaskHandler(
        task_service=service,
        work_root=tmp_path,
        render_adapter=RenderAdapter(io, FakeRenderBackend(), ArtifactStore(io)),
    )
    task = service.create_core_task(
        caller="narrato-api",
        route="/api/v1/video-render/tasks",
        task_type="video_render",
        idempotency_key="render-ambiguous-commit",
        input_snapshot={
            "snapshot_id": "revision_1",
            "source_order": ["asset_a"],
            "sources": [
                {
                    "source_asset_id": "asset_a",
                    "video_url": "https://cdn.example.test/a.mp4",
                }
            ],
            "timeline": [
                {"source_asset_id": "asset_a", "start": 0, "end": 1, "narration": "A"}
            ],
            "voice_id": "voice_fake",
            "voice_snapshot": {"voice_id": "voice_fake"},
        },
    )
    original_complete = service.complete_attempt
    original_get = service.get_task
    committed = False

    def complete_then_disconnect(*args, **kwargs):
        nonlocal committed
        original_complete(*args, **kwargs)
        committed = True
        raise RuntimeError("commit acknowledgement lost")

    def unavailable_after_commit(task_id):
        if committed:
            raise RuntimeError("database unavailable")
        return original_get(task_id)

    monkeypatch.setattr(service, "complete_attempt", complete_then_disconnect)
    monkeypatch.setattr(service, "get_task", unavailable_after_commit)
    with pytest.raises(RuntimeError, match="acknowledgement lost"):
        handler.run(task.id)
    assert io.deleted == []
    journals = list((tmp_path / ".artifact_reconciliation").glob("pending-*.json"))
    assert len(journals) == 1
    journal = journals[0]
    payload = __import__("json").loads(journal.read_text())
    assert payload["task_id"] == task.id and payload["attempt_no"] == 1
    monkeypatch.setattr(service, "get_task", original_get)
    assert handler.reconcile_pending_artifacts() == 1
    assert not journal.exists()
    assert io.deleted == []


def test_render_compensates_known_rollback_even_when_confirmation_read_fails(
    session, tmp_path, monkeypatch
):
    service = TaskService(session)
    io = MemoryIO()
    handler = AtomicTaskHandler(
        task_service=service,
        work_root=tmp_path,
        render_adapter=RenderAdapter(io, FakeRenderBackend(), ArtifactStore(io)),
    )
    task = service.create_core_task(
        caller="narrato-api",
        route="/api/v1/video-render/tasks",
        task_type="video_render",
        idempotency_key="render-known-rollback",
        input_snapshot={
            "snapshot_id": "revision_1",
            "source_order": ["asset_a"],
            "sources": [
                {
                    "source_asset_id": "asset_a",
                    "video_url": "https://cdn.example.test/a.mp4",
                }
            ],
            "timeline": [
                {"source_asset_id": "asset_a", "start": 0, "end": 1, "narration": "A"}
            ],
            "voice_id": "voice_fake",
            "voice_snapshot": {"voice_id": "voice_fake"},
        },
    )
    initial_get = service.get_task
    completion_called = False

    def rollback(*_args, **_kwargs):
        nonlocal completion_called
        completion_called = True
        raise OutboxEventConflictError("OUTBOX_EVENT_CONFLICT")

    def fail_confirmation(task_id):
        if completion_called:
            raise RuntimeError("database unavailable")
        return initial_get(task_id)

    monkeypatch.setattr(service, "complete_attempt", rollback)
    monkeypatch.setattr(service, "get_task", fail_confirmation)
    with pytest.raises(OutboxEventConflictError):
        handler.run(task.id)
    assert io.deleted == list(reversed(io.uploaded))
    assert list((tmp_path / ".artifact_reconciliation").glob("pending-*.json")) == []


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="FFmpeg 未安装")
def test_fake_tts_with_real_ffmpeg_renders_explicit_source_order(tmp_path):
    runner = ProcessRunner(heartbeat_interval_seconds=0.05)
    sources = []
    for name, color, size, fps in (
        ("b", "red", "160x90", 10),
        ("a", "blue", "320x180", 24),
    ):
        target = tmp_path / f"{name}.mp4"
        result = runner.run(
            [
                "ffmpeg",
                "-nostdin",
                "-y",
                "-f",
                "lavfi",
                "-i",
                f"color=c={color}:s={size}:d=2:r={fps}",
                "-pix_fmt",
                "yuv420p",
                str(target),
            ],
            timeout_seconds=30,
        )
        assert result.exit_code == 0
        sources.append(target)
    backend = FfmpegRenderBackend(
        provider=FakeTtsProvider(),
        voice_snapshot={"voice_id": "voice_fake"},
        runner=runner,
        timeout_seconds=30,
    )
    result = backend.render(
        sources=sources,
        source_order=["asset_b", "asset_a"],
        timeline=[
            {"source_asset_id": "asset_b", "start": 0, "end": 2, "narration": "B"},
            {"source_asset_id": "asset_a", "start": 0, "end": 2, "narration": "A"},
        ],
        output_dir=tmp_path,
    )
    assert result["video"].is_file() and result["video"].stat().st_size > 0
    duration = runner.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "csv=p=0",
            str(result["video"]),
        ],
        timeout_seconds=30,
    )
    assert 3.9 <= float(duration.stdout.strip()) <= 4.1
    with wave.open(str(result["voice"]), "rb") as voice:
        assert 3.9 <= voice.getnframes() / voice.getframerate() <= 4.1
    assert result["subtitle"].read_text(encoding="utf-8").index("B") < result[
        "subtitle"
    ].read_text(encoding="utf-8").index("A")


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="FFmpeg 未安装")
def test_real_ffmpeg_preserves_long_voice_and_updates_timeline(tmp_path):
    class TwoSecondTts:
        def synthesize(self, text, destination, *, voice_snapshot):
            with wave.open(str(destination), "wb") as output:
                output.setparams((1, 2, 16_000, 32_000, "NONE", "not compressed"))
                output.writeframes(b"\0\0" * 32_000)

    runner = ProcessRunner(heartbeat_interval_seconds=0.05)
    source = tmp_path / "source.mp4"
    created = runner.run(
        [
            "ffmpeg",
            "-nostdin",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=black:s=160x90:d=2:r=10",
            "-pix_fmt",
            "yuv420p",
            str(source),
        ],
        timeout_seconds=30,
    )
    assert created.exit_code == 0
    result = FfmpegRenderBackend(
        provider=TwoSecondTts(),
        voice_snapshot={"voice_id": "voice"},
        runner=runner,
        timeout_seconds=30,
    ).render(
        sources=[source],
        source_order=["asset"],
        timeline=[
            {"source_asset_id": "asset", "start": 0, "end": 1, "narration": "A"},
            {"source_asset_id": "asset", "start": 1, "end": 2, "narration": "B"},
        ],
        output_dir=tmp_path,
    )
    with wave.open(str(result["voice"]), "rb") as voice:
        assert 3.9 <= voice.getnframes() / voice.getframerate() <= 4.1
    video_duration = runner.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "csv=p=0",
            str(result["video"]),
        ],
        timeout_seconds=30,
    )
    assert 3.9 <= float(video_duration.stdout.strip()) <= 4.1
    assert [(item["start"], item["end"]) for item in result["timeline"]] == [
        (0.0, 2.0),
        (2.0, 4.0),
    ]
    assert "00:00:04,000" in result["subtitle"].read_text(encoding="utf-8")
