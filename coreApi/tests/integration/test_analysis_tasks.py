from __future__ import annotations


import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from core_api.api.routes.tasks import get_task_dispatcher
from core_api.capabilities.models import CoreModel, CoreProvider
from core_api.database import Base, get_engine
from core_api.tasks.models import CoreTask


class RecordingDispatcher:
    """记录 API 首次可靠唤醒。"""

    def __init__(self) -> None:
        self.task_ids: list[str] = []

    def dispatch(self, task_id: str, **_fence) -> None:
        self.task_ids.append(task_id)


def seed_fake_models(settings) -> tuple[str, str]:
    """写入可调用的分析和文案 Fake 模型。"""

    engine = get_engine(settings)
    Base.metadata.create_all(engine)
    from sqlalchemy.orm import Session

    with Session(engine) as session:
        provider = CoreProvider(
            id="provider_fake",
            code="fake",
            name="Fake Provider",
            enabled=True,
            secret_ref="fake_llm",
        )
        analysis = CoreModel(
            id="model_analysis",
            provider=provider,
            provider_model_code="analysis-v1",
            name="Fake Analysis",
            capability_types=["audio_understanding", "video_analysis"],
            languages=["zh-CN"],
            limits={},
            enabled=True,
        )
        script = CoreModel(
            id="model_script",
            provider=provider,
            provider_model_code="script-v1",
            name="Fake Script",
            capability_types=["script_generation"],
            languages=["zh-CN"],
            limits={},
            enabled=True,
        )
        session.add_all([provider, analysis, script])
        session.commit()
    return "model_analysis", "model_script"


@pytest.fixture
def analysis_client(app, settings):
    settings.provider_secrets["fake_llm"] = "fake-only-not-a-real-secret"
    analysis_model, script_model = seed_fake_models(settings)
    dispatcher = RecordingDispatcher()
    app.dependency_overrides[get_task_dispatcher] = lambda: dispatcher
    with TestClient(app) as client:
        yield client, dispatcher, analysis_model, script_model


def analysis_body(model_id: str) -> dict[str, object]:
    """返回合法分析 POST。"""

    return {
        "model_id": model_id,
        "language": "zh-CN",
        "sources": [
            {
                "source_asset_id": "asset_b",
                "video_url": "https://cdn.example.test/narrato/api/b.mp4",
                "video_name": "episode-b.mp4",
                "subtitle_name": "episode-b.srt",
                "subtitle_url": "https://cdn.example.test/narrato/api/b.srt",
                "duration_seconds": 10,
            },
            {
                "source_asset_id": "asset_a",
                "video_url": "https://cdn.example.test/narrato/api/a.mp4",
                "video_name": "episode-a.mp4",
                "subtitle_name": "episode-a.srt",
                "subtitle_artifact": {
                    "artifact_id": "art_subtitle_a",
                    "url": "https://cdn.example.test/narrato/coreApi/a.srt",
                },
                "duration_seconds": 9,
            },
        ],
        "config_snapshot": {"drama_genre": "复仇", "original_sound_ratio": 30},
        "caller_task_id": "node_analysis_1",
    }


def headers(key: str = "analysis-key") -> dict[str, str]:
    return {
        "Authorization": "Bearer test-service-token",
        "X-Idempotency-Key": key,
    }


def test_analysis_post_requires_auth_and_model_capability(analysis_client):
    client, _, analysis_model, script_model = analysis_client
    body = analysis_body(analysis_model)
    assert client.post("/api/v1/video-analysis/tasks", json=body).status_code == 401

    unavailable = client.post(
        "/api/v1/video-analysis/tasks",
        headers=headers("unavailable"),
        json={**body, "model_id": "model_missing"},
    )
    wrong_capability = client.post(
        "/api/v1/video-analysis/tasks",
        headers=headers("wrong-capability"),
        json={**body, "model_id": script_model},
    )
    assert unavailable.status_code == wrong_capability.status_code == 409
    assert unavailable.json()["code"] == "CAPABILITY_UNAVAILABLE"


def test_audio_understanding_freezes_public_video_sampling_without_unknown_field(
    analysis_client, settings
):
    client, dispatcher, analysis_model, _ = analysis_client
    body = {
        "model_id": analysis_model,
        "language": "zh-CN",
        "sources": [{
            "source_asset_id": "asset_audio",
            "video_url": "https://cdn.example.test/narrato/api/audio-source.mp4",
            "video_name": "audio-source.mp4",
            "duration_seconds": 120,
        }],
        "fps": 1,
        "min_frame_tokens": 64,
        "min_frame_tokens_mode": "provider_default",
        "caller_task_id": "node_audio_1",
    }
    response = client.post(
        "/api/v1/audio-understanding/tasks",
        headers=headers("audio-understanding"),
        json=body,
    )
    assert response.status_code == 202
    task_id = response.json()["data"]["core_task_id"]
    assert dispatcher.task_ids[-1] == task_id
    from sqlalchemy.orm import Session

    with Session(get_engine(settings)) as session:
        task = session.get(CoreTask, task_id)
        assert task is not None and task.task_type == "audio_understanding"
        assert task.input_snapshot["config_snapshot"] == {
            "fps": 1,
            "min_frame_tokens": 64,
            "min_frame_tokens_mode": "provider_default",
        }
        assert task.input_snapshot["sources"][0]["video_url"].startswith("https://")

    too_long = {
        **body,
        "sources": [{**body["sources"][0], "duration_seconds": 601}],
    }
    rejected = client.post(
        "/api/v1/audio-understanding/tasks",
        headers=headers("audio-too-long"),
        json=too_long,
    )
    assert rejected.status_code == 422


def test_analysis_rejects_max_tokens_above_frozen_model_limit(
    analysis_client, settings
):
    client, _, analysis_model, _ = analysis_client
    from sqlalchemy.orm import Session

    with Session(get_engine(settings)) as session:
        from sqlalchemy import update

        session.execute(
            update(CoreModel)
            .where(CoreModel.id == analysis_model)
            .values(limits={"max_tokens": 512})
        )
        session.commit()
    body = analysis_body(analysis_model)
    body["config_snapshot"] = {"max_tokens": 513}
    response = client.post(
        "/api/v1/video-analysis/tasks", headers=headers("tokens-over-limit"), json=body
    )
    assert response.status_code == 422
    assert response.json()["code"] == "MAX_TOKENS_EXCEEDED"


def test_analysis_accepts_any_integer_original_sound_ratio_in_range(analysis_client):
    client, _, analysis_model, _ = analysis_client
    body = analysis_body(analysis_model)
    body["config_snapshot"] = {"original_sound_ratio": 35}
    response = client.post(
        "/api/v1/video-analysis/tasks",
        headers=headers("arbitrary-original-sound-ratio"),
        json=body,
    )
    assert response.status_code == 202

    body["config_snapshot"] = {"original_sound_ratio": 101}
    rejected = client.post(
        "/api/v1/video-analysis/tasks",
        headers=headers("out-of-range-original-sound-ratio"),
        json=body,
    )
    assert rejected.status_code == 422


def test_analysis_post_is_idempotent_and_extra_forbid(analysis_client, settings):
    client, dispatcher, analysis_model, _ = analysis_client
    body = analysis_body(analysis_model)
    first = client.post("/api/v1/video-analysis/tasks", headers=headers(), json=body)
    second = client.post("/api/v1/video-analysis/tasks", headers=headers(), json=body)

    assert first.status_code == second.status_code == 202
    assert first.json()["data"] == second.json()["data"]
    assert dispatcher.task_ids == [first.json()["data"]["core_task_id"]]

    conflict = client.post(
        "/api/v1/video-analysis/tasks",
        headers=headers(),
        json={**body, "config_snapshot": {"drama_genre": "different"}},
    )
    extra = client.post(
        "/api/v1/video-analysis/tasks",
        headers=headers("extra"),
        json={**body, "provider_model_code": "raw-model"},
    )
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "IDEMPOTENCY_CONFLICT"
    assert extra.status_code == 422

    from sqlalchemy.orm import Session

    with Session(get_engine(settings)) as session:
        task = session.scalar(
            select(CoreTask).where(CoreTask.id == first.json()["data"]["core_task_id"])
        )
        assert task is not None
        assert task.input_snapshot["source_order"] == ["asset_b", "asset_a"]
        assert [source["video_name"] for source in task.input_snapshot["sources"]] == [
            "episode-b.mp4",
            "episode-a.mp4",
        ]
        assert [
            source["subtitle_name"] for source in task.input_snapshot["sources"]
        ] == ["episode-b.srt", "episode-a.srt"]
        assert task.input_snapshot["model_snapshot"]["model_id"] == analysis_model
        assert task.input_snapshot["model_snapshot"]["catalog_version"].startswith(
            "catalog_"
        )
        assert task.input_snapshot["model_snapshot"] | {} == {
            **task.input_snapshot["model_snapshot"],
            "provider_code": "fake",
            "provider_model_code": "analysis-v1",
            "secret_ref": "fake_llm",
            "provider_settings": {},
            "provider_limits": {},
            "model_limits": {},
            "capability_types": ["audio_understanding", "video_analysis"],
            "languages": ["zh-CN"],
        }


@pytest.mark.parametrize(
    "mutator",
    [
        lambda body: body["sources"].append(dict(body["sources"][0])),
        lambda body: body["sources"].__setitem__(
            1, {**body["sources"][1], "source_asset_id": "asset_b"}
        ),
        lambda body: body["sources"][0].update({"video_url": "/private/tmp/a.mp4"}),
        lambda body: body["sources"][0].update(
            {"subtitle_url": None, "subtitle_artifact": None}
        ),
    ],
)
def test_analysis_post_rejects_source_contract_violations(analysis_client, mutator):
    client, _, analysis_model, _ = analysis_client
    body = analysis_body(analysis_model)
    mutator(body)
    response = client.post(
        "/api/v1/video-analysis/tasks", headers=headers(f"bad-{id(mutator)}"), json=body
    )
    assert response.status_code == 422


def test_script_generation_post_validates_analysis_url_and_model(analysis_client):
    client, dispatcher, _, script_model = analysis_client
    body = {
        "model_id": script_model,
        "language": "zh-CN",
        "analysis_artifact": {
            "artifact_id": "art_analysis",
            "url": "https://cdn.example.test/narrato/coreApi/analysis.json",
        },
        "sources": [
            {
                "source_asset_id": "asset_b",
                "video_url": "https://cdn.example.test/narrato/api/b.mp4",
                "video_name": "episode-b.mp4",
                "subtitle_name": "episode-b.srt",
                "duration_seconds": 10,
            },
            {
                "source_asset_id": "asset_a",
                "video_url": "https://cdn.example.test/narrato/api/a.mp4",
                "video_name": "episode-a.mp4",
                "subtitle_name": "episode-a.srt",
                "duration_seconds": 9,
            },
        ],
        "config_snapshot": {"drama_genre": "复仇", "original_sound_ratio": 30},
    }
    response = client.post(
        "/api/v1/script-generation/tasks", headers=headers("script-key"), json=body
    )
    assert response.status_code == 202
    assert dispatcher.task_ids[-1] == response.json()["data"]["core_task_id"]

    rejected = client.post(
        "/api/v1/script-generation/tasks",
        headers=headers("bad-analysis-url"),
        json={
            **body,
            "analysis_artifact": {
                "artifact_id": "art_bad",
                "url": "file:///tmp/a.json",
            },
        },
    )
    assert rejected.status_code == 422


def test_analysis_post_rejects_model_language_mismatch(analysis_client):
    client, _, analysis_model, _ = analysis_client
    response = client.post(
        "/api/v1/video-analysis/tasks",
        headers=headers("language-mismatch"),
        json={**analysis_body(analysis_model), "language": "en-US"},
    )
    assert response.status_code == 409
    assert response.json()["code"] == "CAPABILITY_UNAVAILABLE"


def test_idempotent_replay_uses_first_snapshot_after_capability_is_disabled(
    analysis_client, settings
):
    client, dispatcher, analysis_model, _ = analysis_client
    body = analysis_body(analysis_model)
    first = client.post(
        "/api/v1/video-analysis/tasks",
        headers=headers("frozen-capability"),
        json=body,
    )
    assert first.status_code == 202

    from sqlalchemy.orm import Session

    with Session(get_engine(settings)) as session:
        model = session.get(CoreModel, analysis_model)
        model.enabled = False
        session.commit()
    second = client.post(
        "/api/v1/video-analysis/tasks",
        headers=headers("frozen-capability"),
        json=body,
    )
    assert second.status_code == 202
    assert second.json()["data"] == first.json()["data"]
    assert dispatcher.task_ids == [first.json()["data"]["core_task_id"]]
