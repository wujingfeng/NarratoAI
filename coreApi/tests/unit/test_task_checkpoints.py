from __future__ import annotations

import wave

from core_api.runtime.checkpoint_store import FilesystemCheckpointStore
from core_api.runtime.workspace import CoreTaskWorkspace
from core_api.tasks.checkpoints import TaskCheckpointService
from core_api.tasks.models import CheckpointStatus


def _write_wav(path) -> None:
    with wave.open(str(path), "wb") as output:
        output.setparams((1, 2, 16_000, 1_600, "NONE", "not compressed"))
        output.writeframes(b"\0\0" * 1_600)


def test_corrupt_checkpoint_is_quarantined_instead_of_reused(
    tmp_path, task_service, session
):
    """校验不通过的缓存必须失效，不能把损坏媒体交给新的 attempt。"""

    task = task_service.create_core_task(
        caller="narrato-api",
        route="/api/v1/video-render/tasks",
        task_type="video_render",
        idempotency_key="corrupt-checkpoint",
        input_snapshot={"snapshot_id": "revision_1"},
    )
    digest = "a" * 64
    store = FilesystemCheckpointStore(tmp_path)
    service = TaskCheckpointService(session, store)
    first = CoreTaskWorkspace.create(tmp_path, task.id, 1)
    voice = first.output_dir / "voice.wav"
    _write_wav(voice)
    row = service.commit(
        workspace=first,
        core_task_id=task.id,
        attempt_no=1,
        stage="render_tts_segment",
        stage_version=1,
        input_digest=digest,
        files={"voice": (voice, "voice_segment.wav", "audio/wav")},
        manifest={"schema_version": "render-tts-segment.v1"},
    )

    stored = store.load(
        core_task_id=task.id,
        stage="render_tts_segment",
        stage_version=1,
        input_digest=digest,
    )
    assert stored is not None
    (stored.root / "voice_segment.wav").write_bytes(b"corrupt")

    second = CoreTaskWorkspace.create(tmp_path, task.id, 2)
    assert (
        service.restore(
            workspace=second,
            core_task_id=task.id,
            stage="render_tts_segment",
            stage_version=1,
            input_digest=digest,
            targets={"voice": "voice_cached.wav"},
        )
        is None
    )
    session.refresh(row)
    assert row.status == CheckpointStatus.INVALID
    assert not stored.root.exists()
    assert not (second.output_dir / "voice_cached.wav").exists()

    third = CoreTaskWorkspace.create(tmp_path, task.id, 3)
    replacement = third.output_dir / "voice.wav"
    _write_wav(replacement)
    repaired = service.commit(
        workspace=third,
        core_task_id=task.id,
        attempt_no=3,
        stage="render_tts_segment",
        stage_version=1,
        input_digest=digest,
        files={"voice": (replacement, "voice_segment.wav", "audio/wav")},
        manifest={"schema_version": "render-tts-segment.v1"},
    )
    assert repaired.id == row.id
    assert repaired.status == CheckpointStatus.READY
