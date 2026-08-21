from __future__ import annotations

import pytest

from narrato_api.products.model_generation import Model, ModelPlayMode, ModelPlayModeProvider
from narrato_api.products.providers import (
    AnyFastProviderAdapter,
    DuoyuanxProviderAdapter,
    ProviderRegistry,
)


def _mode() -> ModelPlayMode:
    return ModelPlayMode(id="mode", model_id="model", code="reference", display_name="参考生成")


def _provider(*, code: str, submit_url: str, status_url: str | None = None) -> ModelPlayModeProvider:
    return ModelPlayModeProvider(
        id=f"provider-{code}",
        play_mode_id="mode",
        provider_code=code,
        provider_model_id="seedance-2.5",
        submit_url=submit_url,
        status_query_url=status_url,
        status_query_method="GET",
        api_key="key",
    )


@pytest.mark.parametrize(
    ("adapter", "provider"),
    [
        (
            AnyFastProviderAdapter(),
            _provider(
                code="anyfast",
                submit_url="https://www.anyfast.ai/v1/images/generations",
            ),
        ),
        (
            DuoyuanxProviderAdapter(),
            _provider(
                code="duoyuanx",
                submit_url="https://duoyuanx.com/v1/images/generations",
            ),
        ),
    ],
)
def test_external_image_adapters_send_openai_style_image_request(monkeypatch: pytest.MonkeyPatch, adapter: object, provider: ModelPlayModeProvider) -> None:
    captured: dict[str, object] = {}

    def request(**kwargs: object) -> dict[str, object]:
        captured.update(kwargs)
        return {"data": [{"url": "https://cdn.example/result.png"}]}

    monkeypatch.setattr("narrato_api.products.providers._safe_https_url", lambda value, **kwargs: value)
    monkeypatch.setattr("narrato_api.products.providers._json_request", request)
    result = adapter.submit(
        model=Model(id="model", display_name="Seedream", model_type="image"),
        play_mode=_mode(),
        provider=provider,
        task_id="local-task",
        prompt="一只猫",
        assets={"image": [{"url": "https://cdn.example/reference.png"}], "video": [], "audio": []},
        resolution="2048x2048",
        ratio=None,
        duration_seconds=None,
        audio_enabled=False,
    )

    assert captured["body"] == {
        "model": "seedance-2.5",
        "prompt": "一只猫",
        "image": "https://cdn.example/reference.png",
        "size": "2048x2048",
    }
    assert result.status == "succeeded"
    assert result.outputs[0].url == "https://cdn.example/result.png"


def test_anyfast_seedance_submit_and_query(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = AnyFastProviderAdapter()
    calls: list[dict[str, object]] = []

    def request(**kwargs: object) -> dict[str, object]:
        calls.append(kwargs)
        if len(calls) == 1:
            return {"id": "anyfast-task", "status": "queued"}
        return {
            "code": "success",
            "data": {
                "task_id": "anyfast-task",
                "status": "SUCCESS",
                "result_url": "https://cdn.example/anyfast.mp4",
                "data": {"duration": 5, "usage": {"total_tokens": 123}},
            },
        }

    monkeypatch.setattr("narrato_api.products.providers._safe_https_url", lambda value, **kwargs: value)
    monkeypatch.setattr("narrato_api.products.providers._json_request", request)
    provider = _provider(
        code="anyfast",
        submit_url="https://www.anyfast.ai/v1/video/generations",
        status_url="https://www.anyfast.ai/v1/video/generations/{task_id}",
    )
    model = Model(id="model", display_name="Seedance", model_type="video")
    submitted = adapter.submit(
        model=model,
        play_mode=_mode(),
        provider=provider,
        task_id="local-task",
        prompt="一只猫",
        assets={"image": [{"url": "https://cdn.example/reference.png", "role": "first_frame"}], "video": [], "audio": []},
        resolution="720p",
        ratio="16:9",
        duration_seconds=5,
        audio_enabled=True,
    )
    status = adapter.get_status(model=model, play_mode=_mode(), provider=provider, provider_task_id="anyfast-task")

    assert submitted.provider_task_id == "anyfast-task"
    assert calls[0]["body"] == {
        "model": "seedance-2.5",
        "content": [
            {"type": "text", "text": "一只猫"},
            {"type": "image_url", "image_url": {"url": "https://cdn.example/reference.png"}, "role": "first_frame"},
        ],
        "generate_audio": True,
        "resolution": "720p",
        "ratio": "16:9",
        "duration": 5,
    }
    assert calls[1]["method"] == "GET"
    assert status.status == "succeeded"
    assert status.outputs[0].url == "https://cdn.example/anyfast.mp4"
    assert status.output_token == 123


def test_duoyuanx_seedance_submit_and_query(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = DuoyuanxProviderAdapter()
    calls: list[dict[str, object]] = []

    def request(**kwargs: object) -> dict[str, object]:
        calls.append(kwargs)
        if len(calls) == 1:
            return {"task_id": "duoyuanx-task"}
        return {
            "code": "success",
            "data": {
                "task_id": "duoyuanx-task",
                "status": "SUCCESS",
                "data": {
                    "duration": 8,
                    "content": {"video_url": "https://cdn.example/duoyuanx.mp4"},
                    "usage": {"total_tokens": 456},
                },
            },
        }

    monkeypatch.setattr("narrato_api.products.providers._safe_https_url", lambda value, **kwargs: value)
    monkeypatch.setattr("narrato_api.products.providers._json_request", request)
    provider = _provider(
        code="duoyuanx",
        submit_url="https://duoyuanx.com/v1/video/generations",
        status_url="https://duoyuanx.com/v1/video/generations/{task_id}",
    )
    model = Model(id="model", display_name="Seedance", model_type="video")
    submitted = adapter.submit(
        model=model,
        play_mode=_mode(),
        provider=provider,
        task_id="local-task",
        prompt="一只狗",
        assets={"image": [], "video": [{"url": "https://cdn.example/source.mp4"}], "audio": [{"url": "https://cdn.example/music.mp3"}]},
        resolution="720P",
        ratio="9:16",
        duration_seconds=8,
        audio_enabled=False,
    )
    status = adapter.get_status(model=model, play_mode=_mode(), provider=provider, provider_task_id="duoyuanx-task")

    assert submitted.provider_task_id == "duoyuanx-task"
    assert calls[0]["body"] == {
        "model": "seedance-2.5",
        "prompt": "一只狗",
        "content": [
            {"type": "text", "text": "一只狗"},
            {"type": "video_url", "video_url": {"url": "https://cdn.example/source.mp4"}},
            {"type": "audio_url", "audio_url": {"url": "https://cdn.example/music.mp3"}},
        ],
        "metadata": {
            "generate_audio": False,
            "watermark": False,
            "duration": 8,
            "resolution": "720p",
            "ratio": "9:16",
        },
    }
    assert status.status == "succeeded"
    assert status.outputs[0].url == "https://cdn.example/duoyuanx.mp4"
    assert status.output_token == 456


def test_registry_contains_documented_external_media_adapters() -> None:
    registry = ProviderRegistry()
    assert isinstance(registry.get("anyfast"), AnyFastProviderAdapter)
    assert isinstance(registry.get("duoyuanx"), DuoyuanxProviderAdapter)


def test_volcengine_seedance_keeps_video_and_audio_reference_roles(monkeypatch: pytest.MonkeyPatch) -> None:
    from narrato_api.products.providers import VolcArkProviderAdapter

    captured: dict[str, object] = {}
    monkeypatch.setattr("narrato_api.products.providers._safe_https_url", lambda value, **kwargs: value)
    monkeypatch.setattr(
        "narrato_api.products.providers._json_request",
        lambda **kwargs: captured.update(kwargs) or {"data": {"id": "task", "status": "queued"}},
    )
    provider = _provider(code="volcengine", submit_url="https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks")
    result = VolcArkProviderAdapter().submit(
        model=Model(id="model", display_name="Seedance", model_type="video"),
        play_mode=_mode(), provider=provider, task_id="local-task", prompt="@video1 参考动作",
        assets={
            "image": [{"url": "https://cdn.example/identity.png", "role": "reference_image"}],
            "video": [{"url": "https://cdn.example/motion.mp4", "role": "reference_video"}],
            "audio": [{"url": "https://cdn.example/voice.mp3", "role": "reference_audio"}],
        },
        resolution="720p", ratio="16:9", duration_seconds=5, audio_enabled=True,
    )

    assert result.provider_task_id == "task"
    assert captured["body"] == {
        "model": "seedance-2.5",
        "content": [
            {"type": "text", "text": "@video1 参考动作"},
            {"type": "image_url", "image_url": {"url": "https://cdn.example/identity.png"}, "role": "reference_image"},
            {"type": "video_url", "video_url": {"url": "https://cdn.example/motion.mp4"}, "role": "reference_video"},
            {"type": "audio_url", "audio_url": {"url": "https://cdn.example/voice.mp3"}, "role": "reference_audio"},
        ],
        "generate_audio": True,
        "resolution": "720p",
        "ratio": "16:9",
        "duration": 5,
    }
