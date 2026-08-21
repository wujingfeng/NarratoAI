from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from core_api.api.routes.tasks import get_task_dispatcher
from core_api.capabilities.models import CoreProvider, CoreVoice
from core_api.database import Base, get_engine
from core_api.tasks.models import CoreTask, CoreTaskStatus
from core_api.tasks.service import TaskService


class RecordingDispatcher:
    """记录首次可靠 dispatch。"""

    def __init__(self):
        self.ids = []

    def dispatch(self, task_id, **_fence):
        self.ids.append(task_id)


def seed_voice(settings):
    Base.metadata.create_all(get_engine(settings))
    with Session(get_engine(settings)) as session:
        provider = CoreProvider(
            id="provider_tts_fake",
            code="fake",
            name="Fake TTS",
            enabled=True,
            secret_ref="fake_tts",
        )
        voice = CoreVoice(
            id="voice_fake",
            provider=provider,
            provider_voice_code="fake-v1",
            name="Fake Voice",
            languages=["zh-CN"],
            supported_formats=["wav"],
            supported_sample_rates=[16000],
            styles=[],
            enabled=True,
        )
        session.add_all([provider, voice])
        session.commit()


def headers(key):
    return {"Authorization": "Bearer test-service-token", "X-Idempotency-Key": key}


def test_tts_subtitle_render_routes_freeze_and_replay(app, settings):
    settings.provider_secrets["fake_tts"] = "fake-secret"
    seed_voice(settings)
    dispatcher = RecordingDispatcher()
    app.dependency_overrides[get_task_dispatcher] = lambda: dispatcher
    with TestClient(app) as client:
        tts = {
            "voice_id": "voice_fake",
            "segments": [{"text": "测试", "start": 0, "end": 1}],
        }
        first = client.post("/api/v1/tts/tasks", headers=headers("tts-1"), json=tts)
        second = client.post("/api/v1/tts/tasks", headers=headers("tts-1"), json=tts)
        assert first.status_code == second.status_code == 202
        assert first.json()["data"] == second.json()["data"]

        subtitle = client.post(
            "/api/v1/subtitle/tasks",
            headers=headers("sub-1"),
            json={
                "snapshot_id": "revision_1",
                "timeline": [{"start": 0, "end": 1, "text": "字幕"}],
            },
        )
        assert subtitle.status_code == 202

        render_body = {
            "snapshot_id": "revision_1",
            "voice_id": "voice_fake",
            "sources": [
                {
                    "source_asset_id": "asset_a",
                    "video_url": "https://cdn.example.test/narrato/api/a.mp4",
                }
            ],
            "timeline": [
                {"source_asset_id": "asset_a", "start": 0, "end": 1, "narration": "A"}
            ],
            "render_config": {
                "video_ratio": "9:16",
                "subtitle_style": "classic_white",
                "source_subtitle_layouts": {
                    "asset_a": {
                        "status": "confirmed",
                        "region": {"x": 0, "y": 0.7, "width": 1, "height": 0.2},
                    }
                },
                "narration_subtitle_position": {"y": 0.78, "font_scale": 1.0},
                "background_music": {
                    "asset_id": "bgm_1",
                    "audio_url": "https://cdn.example.test/narrato/api/bgm.mp3",
                    "volume": 30,
                },
            },
        }
        render = client.post(
            "/api/v1/video-render/tasks", headers=headers("render-1"), json=render_body
        )
        assert render.status_code == 202
        assert len(dispatcher.ids) == 3
        with Session(get_engine(settings)) as session:
            task = session.get(CoreTask, render.json()["data"]["core_task_id"])
        assert task is not None
        assert task.input_snapshot["render_config"] == {
            **render_body["render_config"],
            "voice_volume": 100,
            "voice_rate": 1.0,
            "original_sound_volume": 0,
        }


def test_manifest_route_is_authenticated_stateless_and_rejects_bad_paths(app):
    body = {
        "snapshot_id": "revision_1",
        "timeline": [
            {"source_asset_id": "asset_a", "start": 0, "end": 1, "narration": "A"}
        ],
        "resources": [
            {
                "kind": kind,
                "zip_path": f"assets/{kind}/final.{extension}",
                "url": f"https://cdn.example.test/narrato/coreApi/{kind}.{extension}",
                "size": 10,
                "checksum": "sha256:" + "a" * 64,
                "content_type": content_type,
                **(
                    {"width": 640, "height": 360, "duration": 1.0}
                    if kind == "video"
                    else {}
                ),
            }
            for kind, extension, content_type in (
                ("video", "mp4", "video/mp4"),
                ("subtitle", "srt", "application/x-subrip"),
                ("voice", "wav", "audio/wav"),
                ("timeline", "json", "application/json"),
            )
        ],
    }
    with TestClient(app) as client:
        assert (
            client.post("/api/v1/jianying/manifests/build", json=body).status_code
            == 401
        )
        response = client.post(
            "/api/v1/jianying/manifests/build",
            headers={"Authorization": "Bearer test-service-token"},
            json=body,
        )
        assert response.status_code == 200
        assert response.json()["data"]["package_name"] == "NarratoAI_revision_1.zip"
        bad = {**body, "resources": [{**body["resources"][0], "zip_path": "../escape"}]}
        rejected = client.post(
            "/api/v1/jianying/manifests/build",
            headers={"Authorization": "Bearer test-service-token"},
            json=bad,
        )
        assert rejected.status_code == 422
        assert rejected.json()["code"] == "JIANYING_MANIFEST_INVALID"


def test_original_sound_contract_defaults_to_audible_and_respects_explicit_zero(
    app, settings
):
    settings.provider_secrets["fake_tts"] = "fake-secret"
    seed_voice(settings)
    dispatcher = RecordingDispatcher()
    app.dependency_overrides[get_task_dispatcher] = lambda: dispatcher
    body = {
        "snapshot_id": "revision_original_sound",
        "voice_id": "voice_fake",
        "sources": [
            {
                "source_asset_id": "asset_a",
                "video_url": "https://cdn.example.test/narrato/api/a.mp4",
            }
        ],
        "timeline": [
            {
                "source_asset_id": "asset_a",
                "start": 0,
                "end": 1,
                "narration": "播放原片1",
                "original_sound": True,
            }
        ],
    }
    with TestClient(app) as client:
        audible = client.post(
            "/api/v1/video-render/tasks",
            headers=headers("render-original-audible"),
            json=body,
        )
        muted = client.post(
            "/api/v1/video-render/tasks",
            headers=headers("render-original-muted"),
            json={**body, "render_config": {"original_sound_volume": 0}},
        )

    assert audible.status_code == muted.status_code == 202
    with Session(get_engine(settings)) as session:
        audible_task = session.get(CoreTask, audible.json()["data"]["core_task_id"])
        muted_task = session.get(CoreTask, muted.json()["data"]["core_task_id"])
    assert audible_task is not None and muted_task is not None
    assert audible_task.input_snapshot["timeline"][0]["original_sound"] is True
    assert audible_task.input_snapshot["render_config"]["original_sound_volume"] == 100
    assert muted_task.input_snapshot["render_config"]["original_sound_volume"] == 0


def test_video_translation_render_contract_freezes_continuous_source_and_timing(
    app, settings
):
    settings.provider_secrets["fake_tts"] = "fake-secret"
    seed_voice(settings)
    dispatcher = RecordingDispatcher()
    app.dependency_overrides[get_task_dispatcher] = lambda: dispatcher
    body = {
        "snapshot_id": "translation_revision_1",
        "voice_id": "voice_fake",
        "sources": [
            {
                "source_asset_id": "asset_a",
                "video_url": "https://cdn.example.test/narrato/api/a.mp4",
                "non_vocal_audio_url": "https://cdn.example.test/narrato/api/a-non-vocal.wav",
                "duration_seconds": 12.5,
            }
        ],
        "timeline": [
            {
                "segment_id": "seg_1",
                "segment_index": 0,
                "source_asset_id": "asset_a",
                "start": 1,
                "end": 2,
                "narration": "A complete translated sentence.",
                "voice_id": "voice_fake",
                "speed": 1.1,
                "volume": 80,
                "allowed_duration_ms": 1400,
                "timing_tolerance_ms": 200,
                "max_fit_speed": 1.25,
            }
        ],
        "render_config": {
            "render_mode": "video_translation",
            "translation_audio_mode": "voice_replacement",
            "video_ratio": "original",
            "translated_subtitle_region": {
                "x": 0.05,
                "y": 0.72,
                "width": 0.9,
                "height": 0.2,
            },
        },
    }
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/video-render/tasks",
            headers=headers("translation-render-contract"),
            json=body,
        )

    assert response.status_code == 202
    with Session(get_engine(settings)) as session:
        task = session.get(CoreTask, response.json()["data"]["core_task_id"])
    assert task is not None
    assert task.input_snapshot["source_order"] == ["asset_a"]
    assert task.input_snapshot["sources"][0]["duration_seconds"] == 12.5
    assert task.input_snapshot["render_config"]["render_mode"] == "video_translation"
    assert task.input_snapshot["timeline"][0]["voice_id"] == "voice_fake"
    assert task.input_snapshot["timeline"][0]["allowed_duration_ms"] == 1400
    assert task.input_snapshot["voice_snapshots"]["voice_fake"]["voice_id"] == "voice_fake"


def test_render_route_rejects_source_that_timeline_never_uses(app):
    body = {
        "snapshot_id": "revision_unused_source",
        "voice_id": "voice_fake",
        "sources": [
            {
                "source_asset_id": asset_id,
                "video_url": f"https://cdn.example.test/narrato/api/{asset_id}.mp4",
            }
            for asset_id in ("asset_a", "asset_b")
        ],
        "timeline": [
            {
                "source_asset_id": "asset_a",
                "start": 0,
                "end": 1,
                "narration": "A",
            }
        ],
    }

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/video-render/tasks",
            headers=headers("render-unused-source"),
            json=body,
        )

    assert response.status_code == 422


def test_failed_task_can_be_resumed_without_replacing_immutable_snapshot(
    app, settings
):
    """显式 resume 重新入队同一任务，供 Worker 使用既有 checkpoint。"""

    settings.provider_secrets["fake_tts"] = "fake-secret"
    seed_voice(settings)
    dispatcher = RecordingDispatcher()
    app.dependency_overrides[get_task_dispatcher] = lambda: dispatcher
    body = {
        "snapshot_id": "revision_resume",
        "voice_id": "voice_fake",
        "sources": [
            {
                "source_asset_id": "asset_a",
                "video_url": "https://cdn.example.test/narrato/api/a.mp4",
            }
        ],
        "timeline": [
            {"source_asset_id": "asset_a", "start": 0, "end": 1, "narration": "A"}
        ],
    }
    with TestClient(app) as client:
        created = client.post(
            "/api/v1/video-render/tasks",
            headers=headers("render-resume"),
            json=body,
        )
        task_id = created.json()["data"]["core_task_id"]
        with Session(get_engine(settings), expire_on_commit=False) as session:
            service = TaskService(session)
            attempt = service.start_attempt(task_id)
            service.fail_attempt(
                attempt.id,
                attempt.lease_token,
                {"code": "RENDER_MEDIA_INVALID"},
                retryable=False,
                lease_version=attempt.lease_version,
            )
            frozen_snapshot = dict(service.get_task(task_id).input_snapshot)

        resumed = client.post(
            f"/api/v1/tasks/{task_id}/resume",
            headers={"Authorization": "Bearer test-service-token"},
        )
        assert resumed.status_code == 202
        assert resumed.json()["code"] == "TASK_RESUMED"
        with Session(get_engine(settings)) as session:
            task = session.get(CoreTask, task_id)
            assert task is not None
            assert task.status == CoreTaskStatus.QUEUED
            assert task.retry_count == 0
            assert task.input_snapshot == frozen_snapshot
        assert dispatcher.ids.count(task_id) == 2
