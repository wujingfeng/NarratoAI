from __future__ import annotations

from narrato_api.products.model_generation import Model, ModelPlayMode, ModelPlayModeProvider
from narrato_api.products.providers import VolcArkProviderAdapter


def _provider(*, submit_url: str, status_url: str | None = None) -> ModelPlayModeProvider:
    return ModelPlayModeProvider(id="provider", play_mode_id="mode", provider_code="volcengine", provider_model_id="endpoint-id", submit_url=submit_url, status_query_url=status_url, status_query_method="GET", api_key="key")


def _mode() -> ModelPlayMode:
    return ModelPlayMode(id="mode", model_id="model", code="reference", display_name="Reference")


def test_seedream_request_uses_actual_ark_shape(monkeypatch: object) -> None:
    adapter = VolcArkProviderAdapter()
    captured: dict[str, object] = {}

    def request(**kwargs: object) -> dict[str, object]:
        captured.update(kwargs)
        return {"data": [{"url": "https://result.example/image.png"}], "usage": {"generated_images": 1}}

    monkeypatch.setattr("narrato_api.products.providers._safe_https_url", lambda value, **kwargs: value)
    monkeypatch.setattr("narrato_api.products.providers._json_request", request)
    result = adapter.submit(model=Model(id="model", display_name="Seedream", model_type="image"), play_mode=_mode(), provider=_provider(submit_url="https://ark.cn-beijing.volces.com/api/v3/images/generations"), task_id="task", prompt="一只猫", assets={"image": [{"url": "https://cdn.example/ref.png"}], "video": [], "audio": []}, resolution="2K", ratio=None, duration_seconds=None, audio_enabled=False)
    assert captured["body"] == {"model": "endpoint-id", "prompt": "一只猫", "image": "https://cdn.example/ref.png", "size": "2K"}
    assert result.status == "succeeded" and result.generated_images == 1


def test_seedance_submit_and_status_use_ark_protocol(monkeypatch: object) -> None:
    adapter = VolcArkProviderAdapter()
    calls: list[dict[str, object]] = []

    def request(**kwargs: object) -> dict[str, object]:
        calls.append(kwargs)
        if len(calls) == 1:
            return {"id": "remote", "status": "queued"}
        return {"id": "remote", "status": "succeeded", "duration": 5, "content": {"video_url": "https://result.example/video.mp4"}}

    monkeypatch.setattr("narrato_api.products.providers._safe_https_url", lambda value, **kwargs: value)
    monkeypatch.setattr("narrato_api.products.providers._json_request", request)
    provider = _provider(submit_url="https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks", status_url="https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks/{task_id}")
    model = Model(id="model", display_name="Seedance", model_type="video")
    submitted = adapter.submit(model=model, play_mode=_mode(), provider=provider, task_id="local", prompt="cat", assets={"image": [{"url": "https://cdn.example/ref.png"}], "video": [], "audio": [{"url": "https://cdn.example/a.mp3"}]}, resolution="720p", ratio="16:9", duration_seconds=5, audio_enabled=True)
    status = adapter.get_status(model=model, play_mode=_mode(), provider=provider, provider_task_id="remote")
    assert submitted.provider_task_id == "remote"
    assert calls[0]["body"] == {"model": "endpoint-id", "content": [{"type": "text", "text": "cat"}, {"type": "image_url", "image_url": {"url": "https://cdn.example/ref.png"}}, {"type": "audio_url", "audio_url": {"url": "https://cdn.example/a.mp3"}}], "generate_audio": True, "resolution": "720p", "ratio": "16:9", "duration": 5}
    assert status.status == "succeeded"
    assert status.outputs[0].url == "https://result.example/video.mp4"
