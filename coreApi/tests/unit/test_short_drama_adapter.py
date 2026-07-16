from __future__ import annotations

import json
import math
import httpx
from dataclasses import replace
import concurrent.futures
import logging
import os
import subprocess
import sys
from types import SimpleNamespace

import pytest

from core_api.adapters.narrato.short_drama import (
    FakeShortDramaProvider,
    ScriptValidationError,
    ShortDramaAdapter,
    ShortDramaSource,
    validate_timeline,
    _safe_analysis,
    create_short_drama_provider,
    NarratoShortDramaProvider,
    UnavailableShortDramaProvider,
    ProviderTemporaryError,
    ProviderResponseError,
    ShortDramaInputError,
)


def valid_script_fixture(source_asset_id: str = "asset_a") -> list[dict[str, object]]:
    """返回一个最小合法时间线。"""

    return [
        {
            "source_asset_id": source_asset_id,
            "start": 0.0,
            "end": 1.5,
            "narration": "剧情开始。",
        }
    ]


def request_sources(order: list[str] | None = None) -> list[ShortDramaSource]:
    """按显式顺序构造稳定来源 DTO。"""

    return [
        ShortDramaSource(
            source_asset_id=asset_id,
            video_url=f"https://cdn.example.test/narrato/api/{asset_id}.mp4",
            subtitle_url=f"https://cdn.example.test/narrato/api/{asset_id}.srt",
            duration_seconds=10.0,
        )
        for asset_id in (order or ["asset_a"])
    ]


@pytest.mark.parametrize("value", ["1", True, math.nan, math.inf, -math.inf])
def test_timeline_rejects_non_finite_or_non_numeric_times(value):
    item = valid_script_fixture()[0]
    item["end"] = value
    with pytest.raises(ScriptValidationError):
        validate_timeline([item], request_sources())


def test_timeline_validator_builds_public_allowlisted_dto():
    item = valid_script_fixture()[0] | {
        "picture": "镜头",
        "provider_raw": "private",
        "local_path": "/tmp/private",
    }
    assert validate_timeline([item], request_sources()) == [
        valid_script_fixture()[0] | {"picture": "镜头"}
    ]


def test_timeline_accepts_exact_duration_boundary():
    item = valid_script_fixture()[0]
    item["end"] = 10
    assert validate_timeline([item], request_sources())[0]["end"] == 10.0


def test_production_resolver_wraps_existing_narrato_adapter_without_network():
    calls = {}

    class Analyzer:
        def __init__(self, **kwargs):
            calls["init"] = kwargs

        def analyze_subtitle(self, content):
            calls["analyze"] = content
            return {"status": "success", "analysis": "剧情分析"}

        def generate_narration_copy(self, **kwargs):
            calls["generate"] = kwargs
            return {"status": "success", "narration_copy": "解说"}

        def match_narration_copy_to_script(self, **kwargs):
            calls["match"] = kwargs
            return {
                "status": "success",
                "narration_script": json.dumps(
                    [
                        {
                            "video_id": 1,
                            "timestamp": "00:00:00,000-00:00:01,000",
                            "narration": "解说",
                        }
                    ]
                ),
            }

        def repair_narration_script(self, **kwargs):
            calls["repair"] = kwargs
            return self.match_narration_copy_to_script(**kwargs)

    provider = create_short_drama_provider(
        "openai",
        provider_model_code="gpt-frozen",
        api_key="secret",
        base_url="https://llm.test/v1",
        analyzer_factory=Analyzer,
    )
    assert isinstance(provider, NarratoShortDramaProvider)
    analysis = provider.analyze_story(
        [{"source_asset_id": "asset_a", "subtitle_text": "字幕"}],
        language="zh-CN",
        config={},
    )
    generated = provider.generate_script(
        analysis,
        sources=request_sources(),
        language="zh-CN",
        config={},
    )
    matched = provider.match_script(generated, sources=request_sources())
    assert matched[0]["source_asset_id"] == "asset_a"
    assert calls["init"] == {
        "api_key": "secret",
        "model": "gpt-frozen",
        "base_url": "https://llm.test/v1",
        "provider": "openai",
        "prompt_category": "short_drama_narration",
    }
    assert set(calls) >= {"analyze", "generate", "match"}
    assert isinstance(
        create_short_drama_provider("unknown"), UnavailableShortDramaProvider
    )


def test_factory_constructs_request_local_openai_client_without_global_registration():
    from app.services.llm.manager import LLMServiceManager
    from openai import OpenAI

    LLMServiceManager._text_providers.clear()
    provider = create_short_drama_provider(
        "openai",
        provider_model_code="gpt-frozen",
        api_key="secret",
        base_url="https://llm.test/v1",
    )
    assert isinstance(provider, NarratoShortDramaProvider)
    assert provider.analyzer is None
    assert isinstance(provider.client, OpenAI)
    assert set(LLMServiceManager._text_providers) == set()
    for unsupported in ("azure", "deepseek", "qwen"):
        assert isinstance(
            create_short_drama_provider(
                unsupported, provider_model_code="model", api_key="secret"
            ),
            UnavailableShortDramaProvider,
        )


def test_request_local_openai_four_stage_contract_with_fake_transport():
    calls = {"json": 0, "requests": []}

    def client_factory(**settings):
        calls["settings"] = settings

        def create(**kwargs):
            calls["requests"].append(kwargs)
            prompt = kwargs["messages"][-1]["content"]
            if "生成解说正文" in prompt:
                content = "真实解说正文"
            elif "匹配画面" in prompt or "修复脚本" in prompt:
                calls["json"] += 1
                content = (
                    json.dumps({"items": [{"bad": True}]}, ensure_ascii=False)
                    if calls["json"] == 1
                    else json.dumps(
                        {
                            "items": [
                                {
                                    "video_id": 1,
                                    "timestamp": "00:00:00,000-00:00:01,000",
                                    "narration": "修复后的真实契约",
                                }
                            ]
                        },
                        ensure_ascii=False,
                    )
                )
            else:
                content = "真实剧情分析"
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
            )

        return SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=create))
        )

    provider = create_short_drama_provider(
        "openai",
        provider_model_code="gpt-frozen",
        api_key="secret",
        base_url="https://llm.test/v1",
        model_limits={"max_tokens": 2048},
        client_factory=client_factory,
    )
    subtitles = [{"source_asset_id": "asset_a", "subtitle_text": "真实字幕内容"}]
    analysis = provider.analyze_story(
        subtitles, language="zh-CN", config={"temperature": 0.77, "max_tokens": 1024}
    )
    result = ShortDramaAdapter(provider=provider).generate_script(
        analysis=analysis,
        sources=[replace(request_sources()[0], subtitle_text="真实字幕内容")],
        language="zh-CN",
        config={"original_sound_ratio": 77, "temperature": 0.77, "max_tokens": 1024},
    )
    assert result[0]["narration"] == "修复后的真实契约"
    assert calls["json"] == 2
    assert calls["settings"] == {"api_key": "secret", "base_url": "https://llm.test/v1"}
    assert [item["temperature"] for item in calls["requests"]] == [0.77] * 4
    assert [item["max_tokens"] for item in calls["requests"]] == [1024] * 4
    for request in calls["requests"][2:]:
        prompt = request["messages"][-1]["content"]
        assert request["response_format"] == {"type": "json_object"}
        for required in (
            "items",
            "source_asset_id",
            "start",
            "end",
            "narration",
            "有限数",
            "source_order",
            "duration_seconds",
        ):
            assert required in prompt


def test_request_max_tokens_cannot_exceed_frozen_model_limit():
    provider = create_short_drama_provider(
        "openai",
        provider_model_code="gpt-frozen",
        api_key="secret",
        model_limits={"max_tokens": 512},
        client_factory=lambda **_: None,
    )
    with pytest.raises(ShortDramaInputError):
        provider.analyze_story(
            [{"source_asset_id": "asset_a", "subtitle_text": "subtitle"}],
            language="zh-CN",
            config={"max_tokens": 513},
        )


def test_real_unified_provider_chain_never_logs_sensitive_exception(monkeypatch):
    import asyncio
    from loguru import logger
    from app.services.llm.manager import LLMServiceManager
    from app.services.llm.openai_compatible_provider import OpenAICompatibleTextProvider
    from app.services.llm.unified_service import UnifiedLLMService

    sensitive = "UNIQUE_RESPONSE_SUBTITLE_SECRET_R5_91ac"
    provider = OpenAICompatibleTextProvider(
        api_key="UNIQUE_SECRET_R5", model_name="model", base_url="https://llm.test/v1"
    )

    async def fail(**_):
        raise RuntimeError(sensitive)

    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=fail)))
    monkeypatch.setattr(provider, "_build_client", lambda **_: client)
    monkeypatch.setattr(LLMServiceManager, "get_text_provider", lambda *_: provider)
    captured = []
    sink = logger.add(lambda message: captured.append(str(message)), level="DEBUG")
    try:
        with pytest.raises(Exception):
            asyncio.run(UnifiedLLMService.generate_text(sensitive))
    finally:
        logger.remove(sink)
    assert sensitive not in "".join(captured)


def test_legacy_adapter_logs_metadata_not_prompt_or_response(monkeypatch):
    from app.services.llm.migration_adapter import SubtitleAnalyzerAdapter
    from loguru import logger

    secret_prompt = "UNIQUE_PROMPT_CONTENT_7f63"
    secret_response = "UNIQUE_PROVIDER_RESPONSE_9b21"
    captured: list[str] = []
    sink = logger.add(lambda message: captured.append(str(message)), level="INFO")
    try:
        adapter = SubtitleAnalyzerAdapter(
            api_key="secret", model="model", base_url="https://llm.test/v1"
        )
        monkeypatch.setattr(
            adapter, "_generate_plain_text", lambda *args, **kwargs: secret_response
        )
        result = adapter.generate_narration_copy(
            "短剧", secret_prompt, subtitle_content=secret_prompt
        )
        assert result["status"] == "success"
    finally:
        logger.remove(sink)
    log_text = "".join(captured)
    assert secret_prompt not in log_text
    assert secret_response not in log_text


@pytest.mark.parametrize(
    ("method_name", "call"),
    [
        ("analyze_subtitle", lambda adapter: adapter.analyze_subtitle("subtitle")),
        (
            "generate_narration_copy",
            lambda adapter: adapter.generate_narration_copy("name", "plot", "subtitle"),
        ),
        (
            "match_narration_copy_to_script",
            lambda adapter: adapter.match_narration_copy_to_script(
                "name", "plot", "subtitle", "copy"
            ),
        ),
        (
            "repair_narration_script",
            lambda adapter: adapter.repair_narration_script(
                "name", "plot", "subtitle", "invalid", "errors"
            ),
        ),
    ],
)
def test_legacy_four_stage_errors_never_log_or_return_sensitive_message(
    monkeypatch, method_name, call
):
    from app.services.llm.migration_adapter import SubtitleAnalyzerAdapter
    from loguru import logger

    unique = f"UNIQUE_ERROR_{method_name}_e14b"
    captured: list[str] = []
    sink = logger.add(lambda message: captured.append(str(message)), level="ERROR")
    adapter = SubtitleAnalyzerAdapter("secret", "model", "https://llm.test/v1")
    if method_name == "analyze_subtitle":
        monkeypatch.setattr(
            adapter,
            "_run_async_safely",
            lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError(unique)),
        )
    elif method_name == "generate_narration_copy":
        monkeypatch.setattr(
            adapter,
            "_generate_plain_text",
            lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError(unique)),
        )
    else:
        monkeypatch.setattr(
            adapter,
            "_generate_json_text",
            lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError(unique)),
        )
    try:
        result = call(adapter)
    finally:
        logger.remove(sink)
    assert unique not in "".join(captured)
    assert unique not in json.dumps(result, ensure_ascii=False)


def test_real_provider_dict_items_ratio_prompt_limits_and_exactly_one_repair(
    monkeypatch,
):
    from app.services.llm.migration_adapter import SubtitleAnalyzerAdapter

    provider = create_short_drama_provider(
        "openai",
        provider_model_code="gpt-frozen",
        api_key="secret",
        base_url="https://llm.test/v1",
        prompt_category="film_tv_narration",
        model_limits={"max_input_chars": 20, "max_output_items": 1},
        analyzer_factory=SubtitleAnalyzerAdapter,
    )
    assert isinstance(provider.analyzer, SubtitleAnalyzerAdapter)
    assert provider.analyzer.prompt_category == "film_tv_narration"
    calls = {"repair": 0}
    monkeypatch.setattr(
        provider.analyzer,
        "analyze_subtitle",
        lambda content: {"status": "success", "analysis": "剧情"},
    )
    monkeypatch.setattr(
        provider.analyzer,
        "generate_narration_copy",
        lambda **kwargs: (
            calls.__setitem__("generate", kwargs)
            or {"status": "success", "narration_copy": "文案"}
        ),
    )

    def match(**kwargs):
        calls["ratio"] = kwargs["original_sound_ratio"]
        return {"status": "success", "narration_script": {"items": [{"bad": True}]}}

    def repair(**kwargs):
        calls["repair"] += 1
        return {
            "status": "success",
            "narration_script": {
                "items": [
                    {
                        "video_id": 1,
                        "timestamp": "00:00:00,000-00:00:01,000",
                        "narration": "修复",
                    }
                ]
            },
        }

    monkeypatch.setattr(provider.analyzer, "match_narration_copy_to_script", match)
    monkeypatch.setattr(provider.analyzer, "repair_narration_script", repair)
    subtitles = [{"source_asset_id": "asset_a", "subtitle_text": "真实字幕"}]
    analysis = provider.analyze_story(subtitles, language="zh-CN", config={})
    result = ShortDramaAdapter(provider=provider).generate_script(
        analysis=analysis,
        sources=[replace(request_sources()[0], subtitle_text="真实字幕")],
        language="zh-CN",
        config={"original_sound_ratio": 77, "narration_style": "冷峻"},
    )
    assert result[0]["narration"] == "修复"
    assert calls["repair"] == 1
    assert calls["ratio"] == 77
    assert "风格：冷峻" in calls["generate"]["drama_genre"]


def test_frozen_model_limits_bound_input_and_output():
    class Analyzer:
        def __init__(self, **kwargs):
            pass

        def analyze_subtitle(self, content):
            return {"status": "success", "analysis": "剧情"}

    provider = create_short_drama_provider(
        "openai",
        provider_model_code="model",
        api_key="secret",
        model_limits={"max_input_chars": 5, "max_output_items": 1},
        analyzer_factory=Analyzer,
    )
    with pytest.raises(Exception) as caught:
        provider.analyze_story(
            [{"source_asset_id": "asset_a", "subtitle_text": "超过五个字符的字幕"}],
            language="zh-CN",
            config={},
        )
    assert getattr(caught.value, "code", None) == "SHORT_DRAMA_INPUT_INVALID"
    with pytest.raises(ProviderResponseError):
        provider._bounded_timeline(
            [valid_script_fixture()[0], valid_script_fixture()[0]], request_sources()
        )


def test_core_startup_imports_legacy_services_without_cwd_or_pythonpath(tmp_path):
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import core_api.tasks.celery_tasks; print('CORE_START_OK')",
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stderr
    assert "CORE_START_OK" in result.stdout


def test_concurrent_providers_use_frozen_model_secret_and_base_url_without_crosstalk():
    outgoing = []

    def client_factory(*, api_key, base_url):
        def create(**kwargs):
            outgoing.append((api_key, base_url, kwargs["model"]))
            prompt = kwargs["messages"][-1]["content"]
            if "匹配画面" in prompt:
                content = json.dumps(
                    {
                        "items": [
                            {
                                "video_id": 1,
                                "timestamp": "00:00:00,000-00:00:01,000",
                                "narration": "解说",
                            }
                        ]
                    }
                )
            elif "生成解说正文" in prompt:
                content = "解说正文"
            else:
                content = "剧情摘要"
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
            )

        return SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=create))
        )

    def run(model, secret, base):
        provider = create_short_drama_provider(
            "openai",
            provider_model_code=model,
            api_key=secret,
            base_url=base,
            client_factory=client_factory,
        )
        subtitles = [{"source_asset_id": "asset_a", "subtitle_text": "唯一字幕"}]
        analysis = provider.analyze_story(subtitles, language="zh-CN", config={})
        return ShortDramaAdapter(provider=provider).generate_script(
            analysis=analysis,
            sources=[replace(request_sources()[0], subtitle_text="唯一字幕")],
            config={},
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(run, "model-a", "secret-a", "https://a.test/v1")
        second = executor.submit(run, "model-b", "secret-b", "https://b.test/v1")
        assert first.result()[0]["narration"] == "解说"
        assert second.result()[0]["narration"] == "解说"
    assert set(outgoing) == {
        ("secret-a", "https://a.test/v1", "model-a"),
        ("secret-b", "https://b.test/v1", "model-b"),
    }


def test_core_provider_logs_only_redacted_metadata():
    unique_secret = "UNIQUE_CORE_KEY_a8f4"
    unique_prompt = "UNIQUE_CORE_SUBTITLE_c2d9"

    def client_factory(**settings):
        def create(**kwargs):
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="剧情摘要"))]
            )

        return SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=create))
        )

    records: list[logging.LogRecord] = []

    class Capture(logging.Handler):
        def emit(self, record):
            records.append(record)

    target = logging.getLogger("core_api.adapters.narrato.short_drama")
    handler = Capture()
    previous_level = target.level
    previous_disabled = target.disabled
    previous_disable = logging.root.manager.disable
    logging.disable(logging.NOTSET)
    target.setLevel(logging.INFO)
    target.disabled = False
    target.addHandler(handler)
    try:
        provider = create_short_drama_provider(
            "openai",
            provider_model_code="model",
            api_key=unique_secret,
            base_url="https://llm.test/v1",
            client_factory=client_factory,
        )
        provider.analyze_story(
            [{"source_asset_id": "asset_a", "subtitle_text": unique_prompt}],
            language="zh-CN",
            config={},
        )
    finally:
        target.removeHandler(handler)
        target.setLevel(previous_level)
        target.disabled = previous_disabled
        logging.disable(previous_disable)
    log_text = " ".join(record.getMessage() for record in records)
    assert unique_secret not in log_text
    assert unique_prompt not in log_text
    assert any(hasattr(record, "prompt_sha256") for record in records)


@pytest.mark.parametrize(
    "failure",
    [
        httpx.ConnectTimeout("timeout"),
        httpx.ConnectError("connection refused"),
        RuntimeError("请求超时，请稍后重试"),
        RuntimeError("触发限流 429"),
        RuntimeError("upstream 503 service unavailable"),
        RuntimeError("502 bad gateway"),
        RuntimeError("connection reset by peer"),
        RuntimeError("上游服务暂时不可用"),
        {"status": "error", "status_code": 503, "message": "busy"},
    ],
)
def test_provider_retry_classifies_transient_failures(failure):
    class Analyzer:
        def __init__(self, **kwargs):
            pass

        def analyze_subtitle(self, content):
            if isinstance(failure, BaseException):
                raise failure
            return failure

    provider = create_short_drama_provider(
        "openai",
        provider_model_code="model",
        api_key="secret",
        analyzer_factory=Analyzer,
    )
    with pytest.raises(ProviderTemporaryError):
        provider.analyze_story(
            [{"source_asset_id": "asset_a", "subtitle_text": "字幕"}],
            language="zh-CN",
            config={},
        )


@pytest.mark.parametrize(
    "failure",
    [
        RuntimeError("validation failed"),
        {"status": "error", "status_code": 400, "message": "bad parameter"},
    ],
)
def test_provider_retry_keeps_validation_and_4xx_nonretryable(failure):
    class Analyzer:
        def __init__(self, **kwargs):
            pass

        def analyze_subtitle(self, content):
            if isinstance(failure, BaseException):
                raise failure
            return failure

    provider = create_short_drama_provider(
        "openai",
        provider_model_code="model",
        api_key="secret",
        analyzer_factory=Analyzer,
    )
    with pytest.raises(ProviderResponseError):
        provider.analyze_story(
            [{"source_asset_id": "asset_a", "subtitle_text": "字幕"}],
            language="zh-CN",
            config={},
        )


def test_invalid_script_is_repaired_once():
    fake_llm = FakeShortDramaProvider(
        match_results=[[{"invalid": True}]],
        repair_result=valid_script_fixture(),
    )
    adapter = ShortDramaAdapter(provider=fake_llm)

    result = adapter.generate_script(
        analysis={"summary": "测试剧情"}, sources=request_sources()
    )

    assert result == valid_script_fixture()
    assert fake_llm.repair_calls == 1


def test_script_preserves_explicit_video_source_order():
    sources = request_sources(["asset_b", "asset_a"])
    fake_llm = FakeShortDramaProvider(
        match_results=[
            [
                {"source_asset_id": "asset_b", "start": 0, "end": 1, "narration": "B"},
                {"source_asset_id": "asset_a", "start": 0, "end": 1, "narration": "A"},
            ]
        ]
    )

    result = ShortDramaAdapter(provider=fake_llm).generate_script(
        analysis={"summary": "测试剧情"}, sources=sources
    )

    assert [item["source_asset_id"] for item in result[:2]] == ["asset_b", "asset_a"]


def test_invalid_repair_fails_without_second_repair():
    fake_llm = FakeShortDramaProvider(
        match_results=[[{"invalid": True}]],
        repair_result=[{"still_invalid": True}],
    )

    with pytest.raises(ScriptValidationError) as caught:
        ShortDramaAdapter(provider=fake_llm).generate_script(
            analysis={"summary": "测试剧情"}, sources=request_sources()
        )

    assert caught.value.code == "SCRIPT_VALIDATION_FAILED"
    assert caught.value.retryable is False
    assert fake_llm.repair_calls == 1


@pytest.mark.parametrize(
    "items",
    [
        [],
        [{"source_asset_id": "unknown", "start": 0, "end": 1, "narration": "x"}],
        [{"source_asset_id": "asset_a", "start": -1, "end": 1, "narration": "x"}],
        [{"source_asset_id": "asset_a", "start": 1, "end": 1, "narration": "x"}],
        [{"source_asset_id": "asset_a", "start": 0, "end": 11, "narration": "x"}],
        [{"source_asset_id": "asset_a", "start": 0, "end": 1, "narration": " "}],
        [
            {"source_asset_id": "asset_a", "start": 2, "end": 3, "narration": "a"},
            {"source_asset_id": "asset_a", "start": 1, "end": 2, "narration": "b"},
        ],
    ],
)
def test_validator_rejects_invalid_timeline(items):
    with pytest.raises(ScriptValidationError):
        validate_timeline(items, request_sources())


def test_validator_rejects_first_seen_source_order_change():
    items = [
        {"source_asset_id": "asset_a", "start": 0, "end": 1, "narration": "A"},
        {"source_asset_id": "asset_b", "start": 0, "end": 1, "narration": "B"},
    ]
    with pytest.raises(ScriptValidationError):
        validate_timeline(items, request_sources(["asset_b", "asset_a"]))


def test_unknown_provider_fields_are_not_preserved():
    fake_llm = FakeShortDramaProvider(
        match_results=[
            [
                {
                    **valid_script_fixture()[0],
                    "local_path": "/private/tmp/secret",
                    "provider_raw": "secret response",
                }
            ]
        ]
    )

    result = ShortDramaAdapter(provider=fake_llm).generate_script(
        analysis={"summary": "测试剧情"}, sources=request_sources()
    )

    assert result == valid_script_fixture()
    assert "private" not in json.dumps(result) and "provider_raw" not in str(result)


def test_fake_provider_analysis_is_deterministic_and_source_ordered():
    provider = FakeShortDramaProvider()
    subtitles = [
        {"source_asset_id": "asset_b", "subtitle_text": "第二集"},
        {"source_asset_id": "asset_a", "subtitle_text": "第一集"},
    ]
    first = provider.analyze_story(subtitles, language="zh-CN", config={})
    second = provider.analyze_story(subtitles, language="zh-CN", config={})
    assert first == second
    assert [item["source_asset_id"] for item in first["scenes"]] == [
        "asset_b",
        "asset_a",
    ]


def test_analysis_rejects_provider_scene_reordering():
    value = {
        "title": "bad",
        "summary": "bad order",
        "scenes": [
            {"source_asset_id": "asset_a", "summary": "A"},
            {"source_asset_id": "asset_b", "summary": "B"},
        ],
    }
    with pytest.raises(Exception) as caught:
        _safe_analysis(value, ["asset_b", "asset_a"])
    assert getattr(caught.value, "code", None) == "PROVIDER_RESPONSE_INVALID"


def test_subtitle_text_supports_valid_utf16_srt():
    from core_api.adapters.narrato.short_drama import _subtitle_text

    content = "1\n00:00:00,000 --> 00:00:01,000\n中文台词\n".encode("utf-16")
    assert _subtitle_text(content) == "中文台词"


def test_unavailable_provider_fails_inside_attempt_not_factory():
    from core_api.adapters.narrato.short_drama import create_short_drama_provider

    provider = create_short_drama_provider("not-configured")
    with pytest.raises(Exception) as caught:
        provider.analyze_story([], language="zh-CN", config={})
    assert getattr(caught.value, "code", None) == "PROVIDER_ADAPTER_UNAVAILABLE"
