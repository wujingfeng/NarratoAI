from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from core_api.adapters.narrato.short_drama import (
    NarratoShortDramaProvider,
    ProviderResponseError,
    ShortDramaSource,
    _safe_video_understanding,
    short_drama_provider_supported,
)
from core_api.config import load_settings
from core_api.tasks.celery_tasks import _short_drama_provider_arguments


def test_volcengine_ark_llm_reads_model_id_from_private_toml(tmp_path) -> None:
    config_path = tmp_path / "core-api.toml"
    config_path.write_text(
        "\n".join(
            (
                'volcengine_ark_base_url = "https://ark.example.test/api/v3"',
                'volcengine_ark_api_key = "ark-test-key"',
                'volcengine_ark_model_id = "ep-configured-by-operator"',
            )
        ),
        encoding="utf-8",
    )

    settings = load_settings(config_path)

    assert settings.volcengine_ark_model_id == "ep-configured-by-operator"
    assert settings.resolved_provider_secrets["volcengine_ark"] == "ark-test-key"
    assert short_drama_provider_supported("volcengine_ark") is True


def test_volcengine_ark_llm_overrides_catalog_placeholder_with_toml_model_id(
    settings,
) -> None:
    configured = settings.model_copy(
        update={
            "volcengine_ark_base_url": "https://ark.example.test/api/v3",
            "volcengine_ark_api_key": "ark-test-key",
            "volcengine_ark_model_id": "ep-configured-by-operator",
        }
    )

    arguments = _short_drama_provider_arguments(
        settings=configured,
        provider_code="volcengine_ark",
        provider_model_code="__configured_in_toml__",
        secret_ref="volcengine_ark",
        provider_settings={"base_url": "https://database.example.test/v1"},
    )

    assert arguments == {
        "provider_code": "volcengine_ark",
        "provider_model_code": "ep-configured-by-operator",
        "api_key": "ark-test-key",
        "base_url": "https://ark.example.test/api/v3",
        "prompt_category": "short_drama_narration",
    }


def test_volcengine_ark_capability_stays_hidden_until_all_private_fields_exist(
    settings,
) -> None:
    incomplete = settings.model_copy(
        update={
            "volcengine_ark_base_url": "https://ark.example.test/api/v3",
            "volcengine_ark_api_key": "ark-test-key",
        }
    )

    assert "volcengine_ark" not in incomplete.resolved_provider_secrets


def test_volcengine_ark_multimodal_uses_public_video_url_and_strict_schema() -> None:
    calls: list[dict[str, object]] = []
    responses = [
        {
            "language": "zh-CN",
            "full_text": "台词",
            "segments": [{
                "start": 0.0, "end": 1.0, "speaker": "甲", "text": "台词",
                "emotion": "中性", "confidence": 0.9,
            }],
        },
        {
            "summary": "剧情摘要",
            "characters": ["甲"],
            "events": [{
                "event_id": "event_1", "start_time": 0.0, "anchor_time": 0.5,
                "end_time": 1.0, "recommended_clip_start": 0.0,
                "recommended_clip_end": 1.0, "characters": ["甲"],
                "action": "抬头", "emotion": "惊讶", "dialogue": "台词",
                "visual_evidence": "人物抬头", "audio_evidence": "说出台词",
                "importance": 0.8, "confidence": 0.9,
            }],
        },
    ]

    def client_factory(*, api_key, base_url):
        assert api_key == "secret" and base_url == "https://ark.example/api/v3"

        def create(**kwargs):
            calls.append(kwargs)
            return SimpleNamespace(choices=[SimpleNamespace(
                message=SimpleNamespace(content=json.dumps(responses.pop(0)))
            )])

        return SimpleNamespace(chat=SimpleNamespace(
            completions=SimpleNamespace(create=create)
        ))

    provider = NarratoShortDramaProvider(
        provider_code="volcengine_ark",
        provider_model_code="ep-model",
        api_key="secret",
        base_url="https://ark.example/api/v3",
        client_factory=client_factory,
    )
    source = ShortDramaSource(
        source_asset_id="asset", video_url="https://cdn.example/video.mp4",
        duration_seconds=10,
    )
    provider.understand_audio(source, language="zh-CN", config={})
    provider.analyze_video(
        source, subtitle_text="00:00 台词", language="zh-CN", config={}
    )

    assert len(calls) == 2
    for request in calls:
        media = request["messages"][1]["content"][0]  # type: ignore[index]
        assert media == {
            "type": "video_url",
            "video_url": {"url": "https://cdn.example/video.mp4", "fps": 1},
        }
        assert "min_frame_tokens" not in json.dumps(request, ensure_ascii=False)
        assert request["response_format"]["type"] == "json_schema"  # type: ignore[index]
        assert request["response_format"]["json_schema"]["strict"] is True  # type: ignore[index]
        assert "stream" not in request
    video_schema = calls[1]["response_format"]["json_schema"]["schema"]  # type: ignore[index]
    event_properties = video_schema["properties"]["events"]["items"]["properties"]
    assert event_properties["action"]["minLength"] == 1
    assert event_properties["visual_evidence"]["minLength"] == 1


@pytest.mark.parametrize(
    "event_patch",
    [
        {"action": "   "},
        {"visual_evidence": ""},
        {"recommended_clip_start": 0.6},
        {"recommended_clip_end": 0.8},
    ],
)
def test_video_event_rejects_blank_evidence_and_ranges_outside_recommended_clip(
    event_patch,
) -> None:
    event = {
        "event_id": "event_1",
        "start_time": 0.5,
        "anchor_time": 1.0,
        "end_time": 1.5,
        "recommended_clip_start": 0.25,
        "recommended_clip_end": 2.0,
        "characters": ["甲"],
        "action": "抬头",
        "emotion": "惊讶",
        "dialogue": "台词",
        "visual_evidence": "人物抬头",
        "audio_evidence": "说出台词",
        "importance": 0.8,
        "confidence": 0.9,
        **event_patch,
    }

    with pytest.raises(ProviderResponseError, match="PROVIDER_RESPONSE_INVALID"):
        _safe_video_understanding(
            {"summary": "剧情摘要", "characters": ["甲"], "events": [event]},
            duration_seconds=10,
        )
