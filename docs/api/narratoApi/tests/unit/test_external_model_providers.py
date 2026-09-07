from __future__ import annotations

import pytest

from narrato_api.products.model_generation import (
    Model,
    ModelPlayMode,
    ModelPlayModeProvider,
)
from narrato_api.products.providers import (
    ApimartProviderAdapter,
    AnyFastProviderAdapter,
    DuoyuanxProviderAdapter,
    ProviderError,
    ProviderRegistry,
)


def _mode() -> ModelPlayMode:
    return ModelPlayMode(
        id="mode", model_id="model", code="reference", display_name="参考生成"
    )


def _provider(
    *,
    code: str,
    submit_url: str,
    status_url: str | None = None,
    request_profile: str = "default",
) -> ModelPlayModeProvider:
    return ModelPlayModeProvider(
        id=f"provider-{code}",
        play_mode_id="mode",
        provider_code=code,
        request_profile=request_profile,
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
def test_external_image_adapters_send_openai_style_image_request(
    monkeypatch: pytest.MonkeyPatch, adapter: object, provider: ModelPlayModeProvider
) -> None:
    captured: dict[str, object] = {}

    def request(**kwargs: object) -> dict[str, object]:
        captured.update(kwargs)
        return {"data": [{"url": "https://cdn.example/result.png"}]}

    monkeypatch.setattr(
        "narrato_api.products.providers._safe_https_url", lambda value, **kwargs: value
    )
    monkeypatch.setattr("narrato_api.products.providers._json_request", request)
    result = adapter.submit(
        model=Model(id="model", display_name="Seedream", model_type="image"),
        play_mode=_mode(),
        provider=provider,
        task_id="local-task",
        prompt="一只猫",
        assets={
            "image": [{"url": "https://cdn.example/reference.png"}],
            "video": [],
            "audio": [],
        },
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

    monkeypatch.setattr(
        "narrato_api.products.providers._safe_https_url", lambda value, **kwargs: value
    )
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
        assets={
            "image": [
                {"url": "https://cdn.example/reference.png", "role": "first_frame"}
            ],
            "video": [],
            "audio": [],
        },
        resolution="720p",
        ratio="16:9",
        duration_seconds=5,
        audio_enabled=True,
    )
    status = adapter.get_status(
        model=model,
        play_mode=_mode(),
        provider=provider,
        provider_task_id="anyfast-task",
    )

    assert submitted.provider_task_id == "anyfast-task"
    assert calls[0]["body"] == {
        "model": "seedance-2.5",
        "content": [
            {"type": "text", "text": "一只猫"},
            {
                "type": "image_url",
                "image_url": {"url": "https://cdn.example/reference.png"},
                "role": "first_frame",
            },
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

    monkeypatch.setattr(
        "narrato_api.products.providers._safe_https_url", lambda value, **kwargs: value
    )
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
        assets={
            "image": [],
            "video": [{"url": "https://cdn.example/source.mp4"}],
            "audio": [{"url": "https://cdn.example/music.mp3"}],
        },
        resolution="720P",
        ratio="9:16",
        duration_seconds=8,
        audio_enabled=False,
    )
    status = adapter.get_status(
        model=model,
        play_mode=_mode(),
        provider=provider,
        provider_task_id="duoyuanx-task",
    )

    assert submitted.provider_task_id == "duoyuanx-task"
    assert calls[0]["body"] == {
        "model": "seedance-2.5",
        "prompt": "一只狗",
        "content": [
            {"type": "text", "text": "一只狗"},
            {
                "type": "video_url",
                "video_url": {"url": "https://cdn.example/source.mp4"},
            },
            {
                "type": "audio_url",
                "audio_url": {"url": "https://cdn.example/music.mp3"},
            },
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


@pytest.mark.parametrize(
    ("profile", "model_id", "assets", "ratio", "audio_enabled", "options", "expected"),
    [
        (
            "seedance_2x",
            "seedance-2.5",
            {
                "image": [
                    {"url": "https://cdn.example/ref.png", "role": "reference_image"}
                ],
                "video": [{"url": "https://cdn.example/ref.mp4"}],
                "audio": [{"url": "https://cdn.example/ref.mp3"}],
            },
            "16:9",
            True,
            {"return_last_frame": True},
            {
                "size": "16:9",
                "generate_audio": True,
                "image_urls": ["https://cdn.example/ref.png"],
                "video_urls": ["https://cdn.example/ref.mp4"],
                "audio_urls": ["https://cdn.example/ref.mp3"],
                "return_last_frame": True,
            },
        ),
        (
            "seedance_15",
            "seedance-1-5-pro",
            {
                "image": [
                    {"url": "https://cdn.example/first.png", "role": "first_frame"}
                ],
                "video": [],
                "audio": [],
            },
            "9:16",
            True,
            {"camerafixed": True},
            {
                "aspect_ratio": "9:16",
                "audio": True,
                "image_with_roles": [
                    {"url": "https://cdn.example/first.png", "role": "first_frame"}
                ],
                "camerafixed": True,
            },
        ),
        (
            "minimax_h3",
            "MiniMax-H3",
            {
                "image": [
                    {"url": "https://cdn.example/first.png", "role": "first_frame"}
                ],
                "video": [],
                "audio": [],
            },
            "16:9",
            False,
            {},
            {
                "aspect_ratio": "16:9",
                "first_frame_image": "https://cdn.example/first.png",
            },
        ),
        (
            "wan_30",
            "wan3.0-video",
            {"image": [], "video": [], "audio": []},
            "adaptive",
            False,
            {"link_url": "https://example.com/article", "generation_type": "reference"},
            {
                "size": "adaptive",
                "link_url": "https://example.com/article",
                "generation_type": "reference",
            },
        ),
        (
            "kling_v3",
            "kling-v3",
            {
                "image": [
                    {"url": "https://cdn.example/first.png", "role": "first_frame"}
                ],
                "video": [],
                "audio": [],
            },
            "1:1",
            True,
            {"mode": "pro", "negative_prompt": "blur"},
            {
                "aspect_ratio": "1:1",
                "audio": True,
                "image_urls": ["https://cdn.example/first.png"],
                "mode": "pro",
                "negative_prompt": "blur",
            },
        ),
    ],
)
def test_apimart_profiles_map_documented_video_contracts(
    monkeypatch: pytest.MonkeyPatch,
    profile: str,
    model_id: str,
    assets: dict[str, list[dict[str, object]]],
    ratio: str,
    audio_enabled: bool,
    options: dict[str, object],
    expected: dict[str, object],
) -> None:
    adapter = ApimartProviderAdapter()
    calls: list[dict[str, object]] = []

    def request(**kwargs: object) -> dict[str, object]:
        calls.append(kwargs)
        if len(calls) == 1:
            return {
                "code": 200,
                "data": [{"status": "submitted", "task_id": "apimart-task"}],
            }
        return {
            "code": 200,
            "data": {
                "id": "apimart-task",
                "status": "completed",
                "result": {"videos": [{"url": ["https://cdn.example/result.mp4"]}]},
            },
        }

    # A deploy-specific edge hostname is valid: adapter selection comes from
    # provider_code, never from the hostname.
    monkeypatch.setattr(
        "narrato_api.products.providers._safe_https_url", lambda value, **kwargs: value
    )
    monkeypatch.setattr("narrato_api.products.providers._json_request", request)
    provider = _provider(
        code="apimart",
        request_profile=profile,
        submit_url="https://api-rolling.example/v1/videos/generations",
        status_url="https://api-rolling.example/v1/tasks/{task_id}",
    )
    provider.provider_model_id = model_id
    model = Model(id="model", display_name=model_id, model_type="video")

    submitted = adapter.submit(
        model=model,
        play_mode=_mode(),
        provider=provider,
        task_id="local-task",
        prompt="test prompt",
        assets=assets,
        resolution="720P",
        ratio=ratio,
        duration_seconds=5,
        audio_enabled=audio_enabled,
        options=options,
    )
    completed = adapter.get_status(
        model=model,
        play_mode=_mode(),
        provider=provider,
        provider_task_id="apimart-task",
    )

    assert submitted.status == "queued"
    assert submitted.provider_task_id == "apimart-task"
    base = {"model": model_id, "prompt": "test prompt", "duration": 5}
    if profile != "kling_v3":
        base["resolution"] = "720p"
    assert calls[0]["body"] == {**base, **expected}
    assert calls[1]["url"] == "https://api-rolling.example/v1/tasks/apimart-task"
    assert completed.status == "succeeded"
    assert completed.outputs[0].url == "https://cdn.example/result.mp4"


def test_apimart_rejects_profile_specific_unsupported_options(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "narrato_api.products.providers._safe_https_url", lambda value, **kwargs: value
    )
    provider = _provider(
        code="apimart",
        request_profile="seedance_2x",
        submit_url="https://rolling.example/v1/videos/generations",
    )
    with pytest.raises(Exception, match="options"):
        ApimartProviderAdapter().submit(
            model=Model(id="model", display_name="Seedance", model_type="video"),
            play_mode=_mode(),
            provider=provider,
            task_id="task",
            prompt="test",
            assets={"image": [], "video": [], "audio": []},
            resolution="720p",
            ratio="16:9",
            duration_seconds=5,
            audio_enabled=False,
            options={"negative_prompt": "not supported"},
        )


def test_duoyuanx_llm_submit_uses_non_streaming_openai_chat_completions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = DuoyuanxProviderAdapter()
    captured: dict[str, object] = {}

    def request(**kwargs: object) -> dict[str, object]:
        captured.update(kwargs)
        return {
            "id": "chatcmpl_123",
            "object": "chat.completion",
            "choices": [
                {
                    "message": {"role": "assistant", "content": "你好！"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 12, "completion_tokens": 4},
        }

    monkeypatch.setattr(
        "narrato_api.products.providers._safe_https_url", lambda value, **kwargs: value
    )
    monkeypatch.setattr("narrato_api.products.providers._json_request", request)
    provider = _provider(
        code="duoyuanx", submit_url="https://duoyuanx.com/v1/chat/completions"
    )
    provider.provider_model_id = "minimax-m2.5"
    messages = [
        {"role": "developer", "content": "回答要简洁。"},
        {"role": "user", "content": "你好"},
    ]

    result = adapter.submit(
        model=Model(id="model", display_name="MiniMax M2.5", model_type="llm"),
        play_mode=_mode(),
        provider=provider,
        task_id="local-chat-task",
        prompt="不应覆盖 messages",
        assets={"image": [], "video": [], "audio": []},
        resolution=None,
        ratio=None,
        duration_seconds=None,
        audio_enabled=False,
        messages=messages,
    )

    assert captured["method"] == "POST"
    assert captured["body"] == {
        "model": "minimax-m2.5",
        "messages": messages,
        "stream": False,
    }
    assert result.status == "succeeded"
    assert result.outputs[0].text == "你好！"
    assert result.input_token == 12
    assert result.output_token == 4


def test_duoyuanx_urls_use_fixed_host_allowlist_without_dns_resolution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = DuoyuanxProviderAdapter()
    provider = _provider(
        code="duoyuanx",
        submit_url="https://duoyuanx.com/v1/chat/completions",
        status_url="https://duoyuanx.com/v1/tasks/{task_id}",
    )
    monkeypatch.setattr(
        "narrato_api.products.providers.getaddrinfo",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("fixed provider host must not depend on local DNS mapping")
        ),
    )

    assert adapter._submit_url(provider) == provider.submit_url
    assert adapter._status_url(provider, "task/1") == (
        "https://duoyuanx.com/v1/tasks/task%2F1"
    )

    provider.submit_url = "https://attacker.example/v1/chat/completions"
    with pytest.raises(ProviderError, match="unsafe"):
        adapter._submit_url(provider)


def test_duoyuanx_llm_stream_uses_openai_sse_and_preserves_usage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = DuoyuanxProviderAdapter()
    captured: dict[str, object] = {}

    def request(**kwargs: object):
        captured.update(kwargs)
        return iter(
            [
                {"choices": [{"delta": {"role": "assistant", "content": "你"}}]},
                {"choices": [{"delta": {"content": "好"}}]},
                {"choices": [], "usage": {"prompt_tokens": 8, "completion_tokens": 2}},
            ]
        )

    monkeypatch.setattr(
        "narrato_api.products.providers._safe_https_url", lambda value, **kwargs: value
    )
    monkeypatch.setattr("narrato_api.products.providers._sse_json_request", request)
    provider = _provider(
        code="duoyuanx", submit_url="https://duoyuanx.com/v1/chat/completions"
    )
    provider.provider_model_id = "minimax-m2.5"
    deltas = list(
        adapter.stream_chat(
            model=Model(id="model", display_name="MiniMax M2.5", model_type="llm"),
            provider=provider,
            task_id="stream-task",
            prompt="你好",
            messages=[{"role": "user", "content": "你好"}],
        )
    )

    assert captured["body"] == {
        "model": "minimax-m2.5",
        "messages": [{"role": "user", "content": "你好"}],
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    assert "".join(delta.text for delta in deltas) == "你好"
    assert deltas[-1].input_token == 8
    assert deltas[-1].output_token == 2


def test_registry_contains_documented_external_media_adapters() -> None:
    registry = ProviderRegistry()
    assert isinstance(registry.get("anyfast"), AnyFastProviderAdapter)
    assert isinstance(registry.get("duoyuanx"), DuoyuanxProviderAdapter)
    assert isinstance(registry.get("apimart"), ApimartProviderAdapter)


def test_volcengine_seedance_keeps_video_and_audio_reference_roles(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from narrato_api.products.providers import VolcArkProviderAdapter

    captured: dict[str, object] = {}
    monkeypatch.setattr(
        "narrato_api.products.providers._safe_https_url", lambda value, **kwargs: value
    )
    monkeypatch.setattr(
        "narrato_api.products.providers._json_request",
        lambda **kwargs: (
            captured.update(kwargs) or {"data": {"id": "task", "status": "queued"}}
        ),
    )
    provider = _provider(
        code="volcengine",
        submit_url="https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks",
    )
    result = VolcArkProviderAdapter().submit(
        model=Model(id="model", display_name="Seedance", model_type="video"),
        play_mode=_mode(),
        provider=provider,
        task_id="local-task",
        prompt="@video1 参考动作",
        assets={
            "image": [
                {"url": "https://cdn.example/identity.png", "role": "reference_image"}
            ],
            "video": [
                {"url": "https://cdn.example/motion.mp4", "role": "reference_video"}
            ],
            "audio": [
                {"url": "https://cdn.example/voice.mp3", "role": "reference_audio"}
            ],
        },
        resolution="720p",
        ratio="16:9",
        duration_seconds=5,
        audio_enabled=True,
    )

    assert result.provider_task_id == "task"
    assert captured["body"] == {
        "model": "seedance-2.5",
        "content": [
            {"type": "text", "text": "@video1 参考动作"},
            {
                "type": "image_url",
                "image_url": {"url": "https://cdn.example/identity.png"},
                "role": "reference_image",
            },
            {
                "type": "video_url",
                "video_url": {"url": "https://cdn.example/motion.mp4"},
                "role": "reference_video",
            },
            {
                "type": "audio_url",
                "audio_url": {"url": "https://cdn.example/voice.mp3"},
                "role": "reference_audio",
            },
        ],
        "generate_audio": True,
        "resolution": "720p",
        "ratio": "16:9",
        "duration": 5,
    }
