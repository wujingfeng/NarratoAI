from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from core_api.api.routes.tasks import get_task_dispatcher
from core_api.capabilities.models import CoreProvider, CoreVoice
from core_api.database import Base, get_engine


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
        }
        render = client.post(
            "/api/v1/video-render/tasks", headers=headers("render-1"), json=render_body
        )
        assert render.status_code == 202
        assert len(dispatcher.ids) == 3


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
