"""Provider Adapter registry.

数据库只配置连接点、模型 ID 与价格；供应商的请求字段、POST 查询参数和
状态映射均由本模块中的代码完成。当前生产 Adapter 覆盖火山方舟、AnyFast、多元 x 与 APIMart。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from ipaddress import ip_address
from socket import getaddrinfo
from collections.abc import Iterator
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import quote as urlquote, urlsplit
from urllib.request import Request, urlopen

from narrato_api.products.model_generation import (
    Model,
    ModelPlayMode,
    ModelPlayModeProvider,
)


logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ProviderOutput:
    output_type: str
    url: str | None = None
    text: str | None = None
    content_type: str | None = None
    duration_seconds: float | None = None


@dataclass(frozen=True, slots=True)
class ProviderResult:
    status: str
    provider_task_id: str | None
    outputs: tuple[ProviderOutput, ...] = ()
    input_token: int | None = None
    output_token: int | None = None
    generated_images: int | None = None
    output_duration_seconds: float | None = None
    raw: dict[str, object] | None = None
    error_code: str | None = None
    error_message: str | None = None


@dataclass(frozen=True, slots=True)
class LlmStreamDelta:
    """One OpenAI-compatible SSE chunk, normalized for the assistant layer."""

    text: str
    input_token: int | None = None
    output_token: int | None = None
    raw: dict[str, object] | None = None


class ProviderError(RuntimeError):
    pass


def _provider_error_detail(error: HTTPError) -> str:
    """Return a bounded, secret-free error detail for server logs only."""

    try:
        raw = error.read(2048).decode("utf-8", errors="replace").strip()
    except OSError:
        return "<unavailable>"
    if not raw:
        return "<empty>"
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return raw[:512]
    if not isinstance(payload, dict):
        return raw[:512]

    # Do not log arbitrary upstream echo fields: they can contain the user's
    # prompt or submitted URLs.  The documented providers place diagnostics in
    # one of these scalar fields.
    fields = ("code", "error_code", "message", "error", "detail")
    safe = {
        key: value[:256] if isinstance(value, str) else value
        for key in fields
        if (value := payload.get(key)) is not None
        and isinstance(value, (str, int, float, bool))
    }
    return (
        json.dumps(safe, ensure_ascii=False, separators=(",", ":"))
        if safe
        else "<unrecognized-json-error>"
    )


class ModelProvider(Protocol):
    def submit(
        self,
        *,
        model: Model,
        play_mode: ModelPlayMode,
        provider: ModelPlayModeProvider,
        task_id: str,
        prompt: str | None,
        assets: dict[str, list[dict[str, object]]],
        resolution: str | None,
        ratio: str | None,
        duration_seconds: int | None,
        audio_enabled: bool,
        options: dict[str, object] | None = None,
        messages: list[dict[str, object]] | None = None,
    ) -> ProviderResult: ...

    def get_status(
        self,
        *,
        model: Model,
        play_mode: ModelPlayMode,
        provider: ModelPlayModeProvider,
        provider_task_id: str,
    ) -> ProviderResult: ...


def _safe_https_url(value: str, *, expected_host: str | None = None) -> str:
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
    ):
        raise ProviderError("provider URL is unsafe")

    # Adapter 已将供应商域名硬编码；精确匹配后交由 HTTPS 证书校验保证目标身份。
    if expected_host is not None:
        if parsed.hostname != expected_host:
            raise ProviderError("provider URL is unsafe")
        return value

    # 仅保留给未来“非固定域名”的场景做 DNS / SSRF 防护。
    try:
        addresses = {
            item[4][0]
            for item in getaddrinfo(parsed.hostname, parsed.port or 443, type=0)
        }
    except OSError as exc:
        raise ProviderError("provider host cannot be resolved") from exc

    if not addresses:
        raise ProviderError("provider host cannot be resolved")

    for address in addresses:
        try:
            if not ip_address(address).is_global:
                raise ProviderError("provider URL is unsafe")
        except ValueError as exc:
            raise ProviderError("provider host is invalid") from exc
    return value


def _json_request(
    *,
    url: str,
    method: str,
    api_key: str,
    body: object | None,
    task_id: str | None = None,
) -> dict[str, object]:
    if not api_key:
        raise ProviderError("provider API key is not configured")
    headers = {"Accept": "application/json", "Authorization": f"Bearer {api_key}"}
    data: bytes | None = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode(
            "utf-8"
        )
    if task_id:
        headers["X-Idempotency-Key"] = task_id
    try:
        request = Request(url, data=data, method=method, headers=headers)
        with urlopen(request, timeout=30) as response:
            loaded = json.loads(response.read() or b"{}")
    except HTTPError as exc:
        logger.warning(
            "model_provider_http_error status=%s task_id=%s detail=%s",
            exc.code,
            task_id,
            _provider_error_detail(exc),
        )
        raise ProviderError("provider request failed") from exc
    except (URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
        logger.warning(
            "model_provider_transport_error type=%s task_id=%s",
            type(exc).__name__,
            task_id,
        )
        raise ProviderError("provider request failed") from exc
    if not isinstance(loaded, dict):
        raise ProviderError("provider response is invalid")
    return loaded


def _sse_json_request(
    *, url: str, api_key: str, body: object, task_id: str | None = None
) -> Iterator[dict[str, object]]:
    """Yield JSON payloads from a provider's ``data:`` SSE frames.

    The helper deliberately accepts only the OpenAI-compatible `data:` framing
    used by 多元 X. It does not buffer the entire response, which keeps the
    browser SSE endpoint capable of forwarding each generated text delta.
    """

    if not api_key:
        raise ProviderError("provider API key is not configured")
    headers = {
        "Accept": "text/event-stream",
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Cache-Control": "no-cache",
    }
    if task_id:
        headers["X-Idempotency-Key"] = task_id
    data = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    try:
        request = Request(url, data=data, method="POST", headers=headers)
        with urlopen(request, timeout=90) as response:
            for line in response:
                frame = line.decode("utf-8", errors="replace").strip()
                if not frame or not frame.startswith("data:"):
                    continue
                payload = frame.removeprefix("data:").strip()
                if payload == "[DONE]":
                    return
                try:
                    decoded = json.loads(payload)
                except json.JSONDecodeError as exc:
                    raise ProviderError("provider SSE payload is invalid") from exc
                if not isinstance(decoded, dict):
                    raise ProviderError("provider SSE payload is invalid")
                yield decoded
    except HTTPError as exc:
        logger.warning(
            "model_provider_stream_http_error status=%s task_id=%s detail=%s",
            exc.code,
            task_id,
            _provider_error_detail(exc),
        )
        raise ProviderError("provider stream request failed") from exc
    except (URLError, TimeoutError, ValueError, OSError) as exc:
        logger.warning(
            "model_provider_stream_transport_error type=%s task_id=%s",
            type(exc).__name__,
            task_id,
        )
        raise ProviderError("provider stream request failed") from exc


def _ark_status(value: object) -> str:
    status = str(value or "").lower()
    if status in {"queued", "pending", "submitted", "created"}:
        return "queued"
    if status in {"running", "processing", "in_progress"}:
        return "processing"
    if status in {"succeeded", "success", "completed"}:
        return "succeeded"
    if status in {"failed", "failure", "cancelled", "expired", "error"}:
        return "failed"
    raise ProviderError("provider response has invalid status")


def _usage(raw: dict[str, object]) -> tuple[int | None, int | None, int | None]:
    usage = raw.get("usage")
    usage = usage if isinstance(usage, dict) else {}

    def integer(*keys: str) -> int | None:
        for key in keys:
            value = usage.get(key)
            if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                return value
        return None

    return (
        integer("prompt_tokens", "input_tokens"),
        integer("completion_tokens", "output_tokens", "total_tokens"),
        integer("generated_images"),
    )


def _object(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}


def _video_content(
    prompt: str | None, assets: dict[str, list[dict[str, object]]]
) -> list[dict[str, object]]:
    content: list[dict[str, object]] = []
    if prompt:
        content.append({"type": "text", "text": prompt})
    for asset_type, message_type, field_name in (
        ("image", "image_url", "image_url"),
        ("video", "video_url", "video_url"),
        ("audio", "audio_url", "audio_url"),
    ):
        for item in assets.get(asset_type, []):
            url = item.get("url")
            if not isinstance(url, str):
                continue
            value: dict[str, object] = {"type": message_type, field_name: {"url": url}}
            role = item.get("role")
            if isinstance(role, str):
                value["role"] = role
            content.append(value)
    return content


def _image_body(
    provider: ModelPlayModeProvider,
    prompt: str | None,
    assets: dict[str, list[dict[str, object]]],
    resolution: str | None,
) -> dict[str, object]:
    body: dict[str, object] = {
        "model": provider.provider_model_id,
        "prompt": prompt or "",
    }
    image_urls = [
        str(item["url"])
        for item in assets.get("image", [])
        if isinstance(item.get("url"), str)
    ]
    if image_urls:
        body["image"] = image_urls[0] if len(image_urls) == 1 else image_urls
    if resolution:
        body["size"] = resolution
    return body


def _image_result(raw: dict[str, object]) -> ProviderResult:
    data = raw.get("data")
    data = data if isinstance(data, list) else []
    outputs: list[ProviderOutput] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        url = item.get("url")
        if isinstance(url, str) and url:
            output_format = item.get("output_format")
            outputs.append(
                ProviderOutput(
                    output_type="image",
                    url=url,
                    content_type=output_format
                    if isinstance(output_format, str)
                    else None,
                )
            )
    _, output_token, generated_images = _usage(raw)
    if generated_images is None:
        generated_images = len(outputs)
    if generated_images < len(outputs):
        raise ProviderError("provider generated image count is inconsistent")
    if not outputs:
        raise ProviderError("provider returned no image outputs")
    return ProviderResult(
        status="succeeded",
        provider_task_id=None,
        outputs=tuple(outputs),
        output_token=output_token,
        generated_images=generated_images,
        raw=raw,
    )


def _status_url(
    provider: ModelPlayModeProvider, provider_task_id: str, *, host: str | None = None
) -> str:
    if not provider.status_query_url:
        raise ProviderError("provider status URL is not configured")
    url = provider.status_query_url.replace(
        "{task_id}", urlquote(provider_task_id, safe="")
    )
    return _safe_https_url(url, expected_host=host)


class VolcArkProviderAdapter:
    """火山方舟的 LLM、Seedream 与 Seedance 真实协议适配。"""

    code = "volcengine"

    def _submit_url(self, provider: ModelPlayModeProvider) -> str:
        return _safe_https_url(provider.submit_url)

    def _status_url(
        self, provider: ModelPlayModeProvider, provider_task_id: str
    ) -> str:
        if not provider.status_query_url:
            raise ProviderError("provider status URL is not configured")
        url = provider.status_query_url.replace(
            "{task_id}", urlquote(provider_task_id, safe="")
        )
        return _safe_https_url(url)

    def submit(
        self,
        *,
        model: Model,
        play_mode: ModelPlayMode,
        provider: ModelPlayModeProvider,
        task_id: str,
        prompt: str | None,
        assets: dict[str, list[dict[str, object]]],
        resolution: str | None,
        ratio: str | None,
        duration_seconds: int | None,
        audio_enabled: bool,
        options: dict[str, object] | None = None,
        messages: list[dict[str, object]] | None = None,
    ) -> ProviderResult:
        url = self._submit_url(provider)
        if model.model_type == "llm":
            body = {
                "model": provider.provider_model_id,
                "messages": messages or [{"role": "user", "content": prompt or ""}],
            }
            raw = _json_request(
                url=url,
                method="POST",
                api_key=provider.api_key,
                body=body,
                task_id=task_id,
            )
            return self._llm_result(raw)
        if model.model_type == "image":
            body: dict[str, object] = {
                "model": provider.provider_model_id,
                "prompt": prompt or "",
            }
            image_urls = [
                str(item["url"])
                for item in assets.get("image", [])
                if isinstance(item.get("url"), str)
            ]
            if image_urls:
                body["image"] = image_urls[0] if len(image_urls) == 1 else image_urls
            if resolution:
                body["size"] = resolution
            raw = _json_request(
                url=url,
                method="POST",
                api_key=provider.api_key,
                body=body,
                task_id=task_id,
            )
            return self._image_result(raw)
        if model.model_type == "video":
            # Prompt aliases and the content array both use the frozen
            # ModelTaskAsset order; every media item retains its provider role.
            body = {
                "model": provider.provider_model_id,
                "content": _video_content(prompt, assets),
                "generate_audio": audio_enabled,
            }
            if resolution:
                body["resolution"] = resolution
            if ratio:
                body["ratio"] = ratio
            if duration_seconds:
                body["duration"] = duration_seconds
            raw = _json_request(
                url=url,
                method="POST",
                api_key=provider.api_key,
                body=body,
                task_id=task_id,
            )
            data = raw.get("data", raw)
            if not isinstance(data, dict):
                raise ProviderError("provider response is invalid")
            provider_task_id = data.get("id") or data.get("task_id")
            if not isinstance(provider_task_id, str) or not provider_task_id:
                raise ProviderError("provider response lacks task id")
            return ProviderResult(
                status=_ark_status(data.get("status", "queued")),
                provider_task_id=provider_task_id,
                raw=raw,
            )
        raise ProviderError("unsupported model type")

    def get_status(
        self,
        *,
        model: Model,
        play_mode: ModelPlayMode,
        provider: ModelPlayModeProvider,
        provider_task_id: str,
    ) -> ProviderResult:
        if model.model_type != "video":
            raise ProviderError(
                "synchronous provider task does not support status query"
            )
        url = self._status_url(provider, provider_task_id)
        method = provider.status_query_method
        body = {"task_id": provider_task_id} if method == "POST" else None
        raw = _json_request(url=url, method=method, api_key=provider.api_key, body=body)
        data = raw.get("data", raw)
        if not isinstance(data, dict):
            raise ProviderError("provider response is invalid")
        status = _ark_status(data.get("status"))
        content = data.get("content")
        content = content if isinstance(content, dict) else {}
        outputs = ()
        video_url = content.get("video_url")
        if isinstance(video_url, str) and video_url:
            outputs = (
                ProviderOutput(
                    output_type="video",
                    url=video_url,
                    duration_seconds=_number(data.get("duration")),
                ),
            )
        error = data.get("error")
        error = error if isinstance(error, dict) else {}
        return ProviderResult(
            status=status,
            provider_task_id=provider_task_id,
            outputs=outputs,
            output_duration_seconds=_number(data.get("duration")),
            raw=raw,
            error_code=error.get("code")
            if isinstance(error.get("code"), str)
            else None,
            error_message=error.get("message")
            if isinstance(error.get("message"), str)
            else None,
        )

    @staticmethod
    def _llm_result(raw: dict[str, object]) -> ProviderResult:
        choices = raw.get("choices")
        choices = choices if isinstance(choices, list) else []
        text: str | None = None
        if choices and isinstance(choices[0], dict):
            message = choices[0].get("message")
            message = message if isinstance(message, dict) else {}
            value = message.get("content")
            if isinstance(value, str):
                text = value
        if text is None:
            raise ProviderError("provider response lacks LLM content")
        input_token, output_token, _ = _usage(raw)
        return ProviderResult(
            status="succeeded",
            provider_task_id=None,
            outputs=(ProviderOutput(output_type="text", text=text),),
            input_token=input_token,
            output_token=output_token,
            raw=raw,
        )

    @staticmethod
    def _image_result(raw: dict[str, object]) -> ProviderResult:
        data = raw.get("data")
        data = data if isinstance(data, list) else []
        outputs: list[ProviderOutput] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            url = item.get("url")
            if isinstance(url, str) and url:
                outputs.append(
                    ProviderOutput(
                        output_type="image",
                        url=url,
                        content_type=item.get("output_format")
                        if isinstance(item.get("output_format"), str)
                        else None,
                    )
                )
        _, output_token, generated_images = _usage(raw)
        if generated_images is None:
            generated_images = len(outputs)
        if generated_images < len(outputs):
            raise ProviderError("provider generated image count is inconsistent")
        if not outputs:
            raise ProviderError("provider returned no image outputs")
        return ProviderResult(
            status="succeeded",
            provider_task_id=None,
            outputs=tuple(outputs),
            output_token=output_token,
            generated_images=generated_images,
            raw=raw,
        )


class _ExternalMediaProviderAdapter:
    """Shared strict transport for documented media-provider APIs."""

    code = ""

    def _submit_url(self, provider: ModelPlayModeProvider) -> str:
        return _safe_https_url(provider.submit_url)

    def _status_url(
        self, provider: ModelPlayModeProvider, provider_task_id: str
    ) -> str:
        return _status_url(provider, provider_task_id)

    def _submit_image(
        self,
        *,
        provider: ModelPlayModeProvider,
        task_id: str,
        prompt: str | None,
        assets: dict[str, list[dict[str, object]]],
        resolution: str | None,
    ) -> ProviderResult:
        raw = _json_request(
            url=self._submit_url(provider),
            method="POST",
            api_key=provider.api_key,
            body=_image_body(provider, prompt, assets, resolution),
            task_id=task_id,
        )
        return _image_result(raw)

    def _require_media_model(self, model: Model) -> None:
        if model.model_type not in {"image", "video"}:
            raise ProviderError("unsupported model type")


class AnyFastProviderAdapter(_ExternalMediaProviderAdapter):
    """AnyFast 文生/参考生图片及 Seedance 视频协议。"""

    code = "anyfast"

    def submit(
        self,
        *,
        model: Model,
        play_mode: ModelPlayMode,
        provider: ModelPlayModeProvider,
        task_id: str,
        prompt: str | None,
        assets: dict[str, list[dict[str, object]]],
        resolution: str | None,
        ratio: str | None,
        duration_seconds: int | None,
        audio_enabled: bool,
        options: dict[str, object] | None = None,
        messages: list[dict[str, object]] | None = None,
    ) -> ProviderResult:
        self._require_media_model(model)
        if model.model_type == "image":
            return self._submit_image(
                provider=provider,
                task_id=task_id,
                prompt=prompt,
                assets=assets,
                resolution=resolution,
            )

        body: dict[str, object] = {
            "model": provider.provider_model_id,
            "content": _video_content(prompt, assets),
            "generate_audio": audio_enabled,
        }
        if resolution:
            body["resolution"] = resolution
        if ratio:
            body["ratio"] = ratio
        if duration_seconds:
            body["duration"] = duration_seconds
        raw = _json_request(
            url=self._submit_url(provider),
            method="POST",
            api_key=provider.api_key,
            body=body,
            task_id=task_id,
        )
        data = _object(raw.get("data")) or raw
        remote_id = data.get("id") or data.get("task_id")
        if not isinstance(remote_id, str) or not remote_id:
            raise ProviderError("provider response lacks task id")
        return ProviderResult(
            status=_ark_status(data.get("status", "queued")),
            provider_task_id=remote_id,
            raw=raw,
        )

    def get_status(
        self,
        *,
        model: Model,
        play_mode: ModelPlayMode,
        provider: ModelPlayModeProvider,
        provider_task_id: str,
    ) -> ProviderResult:
        if model.model_type != "video":
            raise ProviderError(
                "synchronous provider task does not support status query"
            )
        method = provider.status_query_method
        raw = _json_request(
            url=self._status_url(provider, provider_task_id),
            method=method,
            api_key=provider.api_key,
            body={"task_id": provider_task_id} if method == "POST" else None,
        )
        envelope = _object(raw.get("data")) or raw
        details = _object(envelope.get("data"))
        status = _ark_status(envelope.get("status") or details.get("status"))
        content = _object(details.get("content"))
        video_url = envelope.get("result_url") or content.get("video_url")
        duration = _number(details.get("duration") or envelope.get("duration"))
        outputs = (
            (
                ProviderOutput(
                    output_type="video", url=video_url, duration_seconds=duration
                ),
            )
            if isinstance(video_url, str) and video_url
            else ()
        )
        input_token, output_token, _ = _usage(details or envelope)
        return ProviderResult(
            status=status,
            provider_task_id=provider_task_id,
            outputs=outputs,
            input_token=input_token,
            output_token=output_token,
            output_duration_seconds=duration,
            raw=raw,
            error_code=envelope.get("error_code")
            if isinstance(envelope.get("error_code"), str)
            else None,
            error_message=envelope.get("fail_reason")
            if isinstance(envelope.get("fail_reason"), str)
            else None,
        )


class DuoyuanxProviderAdapter(_ExternalMediaProviderAdapter):
    """多元 x 的 OpenAI 兼容对话、Seedream/Seedance 生成协议。"""

    code = "duoyuanx"
    host = "duoyuanx.com"

    def _submit_url(self, provider: ModelPlayModeProvider) -> str:
        # 多元 x 是代码内注册的固定供应商。按精确域名校验后直接交给 TLS
        # 验证，避免本机透明代理使用 198.18.0.0/15 映射地址时被通用 DNS
        # SSRF 检查误判为内网目标。
        return _safe_https_url(provider.submit_url, expected_host=self.host)

    def _status_url(
        self, provider: ModelPlayModeProvider, provider_task_id: str
    ) -> str:
        return _status_url(provider, provider_task_id, host=self.host)

    @staticmethod
    def _resolution(value: str) -> str:
        """Normalize legacy UI/DB labels to the documented provider enum."""

        normalized = value.strip().lower()
        # Existing model capability rows used ``4K``; the provider API accepts
        # the lowercase enum ``4k`` alongside 480p/720p/1080p.
        return normalized

    def stream_chat(
        self,
        *,
        model: Model,
        provider: ModelPlayModeProvider,
        task_id: str,
        prompt: str | None,
        messages: list[dict[str, object]] | None = None,
    ) -> Iterator[LlmStreamDelta]:
        """Stream a 多元 X OpenAI Chat Completions response without buffering."""

        if model.model_type != "llm":
            raise ProviderError("streaming is only supported for LLM models")
        body: dict[str, object] = {
            "model": provider.provider_model_id,
            "messages": messages or [{"role": "user", "content": prompt or ""}],
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        for raw in _sse_json_request(
            url=self._submit_url(provider),
            api_key=provider.api_key,
            body=body,
            task_id=task_id,
        ):
            choices = raw.get("choices")
            choice = (
                choices[0]
                if isinstance(choices, list)
                and choices
                and isinstance(choices[0], dict)
                else {}
            )
            delta = choice.get("delta") if isinstance(choice, dict) else {}
            text = delta.get("content") if isinstance(delta, dict) else ""
            input_token, output_token, _ = _usage(raw)
            if not isinstance(text, str):
                text = ""
            yield LlmStreamDelta(
                text=text, input_token=input_token, output_token=output_token, raw=raw
            )

    def submit(
        self,
        *,
        model: Model,
        play_mode: ModelPlayMode,
        provider: ModelPlayModeProvider,
        task_id: str,
        prompt: str | None,
        assets: dict[str, list[dict[str, object]]],
        resolution: str | None,
        ratio: str | None,
        duration_seconds: int | None,
        audio_enabled: bool,
        options: dict[str, object] | None = None,
        messages: list[dict[str, object]] | None = None,
    ) -> ProviderResult:
        # 多元 x 的通用对话端点兼容 OpenAI Chat Completions。助手任务必须
        # 明确关闭 SSE：业务服务需要在同一个 ModelTask 中拿到完整 JSON 回复，
        # 以便结算 token 并把结果写入会话或后续工作流。
        if model.model_type == "llm":
            body: dict[str, object] = {
                "model": provider.provider_model_id,
                "messages": messages or [{"role": "user", "content": prompt or ""}],
                "stream": False,
            }
            raw = _json_request(
                url=self._submit_url(provider),
                method="POST",
                api_key=provider.api_key,
                body=body,
                task_id=task_id,
            )
            return VolcArkProviderAdapter._llm_result(raw)

        self._require_media_model(model)
        if model.model_type == "image":
            return self._submit_image(
                provider=provider,
                task_id=task_id,
                prompt=prompt,
                assets=assets,
                resolution=resolution,
            )

        metadata: dict[str, object] = {
            "generate_audio": audio_enabled,
            "watermark": False,
        }
        if duration_seconds:
            metadata["duration"] = duration_seconds
        if resolution:
            metadata["resolution"] = self._resolution(resolution)
        if ratio:
            metadata["ratio"] = ratio
        body: dict[str, object] = {
            "model": provider.provider_model_id,
            "content": _video_content(prompt, assets),
            "metadata": metadata,
        }
        # The documented Seedance 2.0 protocol uses ``content[type=text]``.
        # The currently configured legacy Seedance 1.5 endpoint also requires
        # a top-level prompt.  Sending both keeps multimodal content intact and
        # makes the adapter compatible with both generations of this API.
        if prompt:
            body["prompt"] = prompt
        raw = _json_request(
            url=self._submit_url(provider),
            method="POST",
            api_key=provider.api_key,
            body=body,
            task_id=task_id,
        )
        data = _object(raw.get("data")) or raw
        remote_id = data.get("task_id") or data.get("id")
        if not isinstance(remote_id, str) or not remote_id:
            raise ProviderError("provider response lacks task id")
        return ProviderResult(
            status=_ark_status(data.get("status", "queued")),
            provider_task_id=remote_id,
            raw=raw,
        )

    def get_status(
        self,
        *,
        model: Model,
        play_mode: ModelPlayMode,
        provider: ModelPlayModeProvider,
        provider_task_id: str,
    ) -> ProviderResult:
        if model.model_type != "video":
            raise ProviderError(
                "synchronous provider task does not support status query"
            )
        method = provider.status_query_method
        raw = _json_request(
            url=self._status_url(provider, provider_task_id),
            method=method,
            api_key=provider.api_key,
            body={"task_id": provider_task_id} if method == "POST" else None,
        )
        envelope = _object(raw.get("data")) or raw
        details = _object(envelope.get("data"))
        status = _ark_status(envelope.get("status") or details.get("status"))
        content = _object(details.get("content"))
        video_url = content.get("video_url") or envelope.get("result_url")
        duration = _number(details.get("duration") or envelope.get("duration"))
        outputs = (
            (
                ProviderOutput(
                    output_type="video", url=video_url, duration_seconds=duration
                ),
            )
            if isinstance(video_url, str) and video_url
            else ()
        )
        input_token, output_token, _ = _usage(details or envelope)
        return ProviderResult(
            status=status,
            provider_task_id=provider_task_id,
            outputs=outputs,
            input_token=input_token,
            output_token=output_token,
            output_duration_seconds=duration,
            raw=raw,
            error_code=envelope.get("error_code")
            if isinstance(envelope.get("error_code"), str)
            else None,
            error_message=envelope.get("fail_reason")
            if isinstance(envelope.get("fail_reason"), str)
            else None,
        )


class ApimartProviderAdapter(_ExternalMediaProviderAdapter):
    """APIMart unified video API with explicit, configuration-selected request profiles.

    ``provider_code`` selects this adapter.  A Provider row then declares a
    stable ``request_profile`` so that changing APIMart's host never changes
    protocol selection and model names are never guessed from prefixes.
    """

    code = "apimart"
    _profiles = frozenset(
        {"seedance_2x", "seedance_15", "minimax_h3", "wan_30", "kling_v3"}
    )
    _option_keys = {
        "seedance_2x": frozenset({"seed", "return_last_frame"}),
        "seedance_15": frozenset({"seed", "camerafixed"}),
        "minimax_h3": frozenset(),
        "wan_30": frozenset({"generation_type", "file_url", "link_url"}),
        "kling_v3": frozenset(
            {
                "mode",
                "negative_prompt",
                "watermark",
                "multi_shot",
                "shot_type",
                "multi_prompt",
                "element_list",
            }
        ),
    }

    @classmethod
    def _profile(cls, provider: ModelPlayModeProvider) -> str:
        profile = provider.request_profile
        if profile not in cls._profiles:
            raise ProviderError("APIMart provider request profile is invalid")
        return profile

    @staticmethod
    def _urls(assets: dict[str, list[dict[str, object]]], kind: str) -> list[str]:
        return [
            item["url"]
            for item in assets.get(kind, [])
            if isinstance(item.get("url"), str) and item["url"]
        ]

    @staticmethod
    def _image_roles(
        assets: dict[str, list[dict[str, object]]],
    ) -> tuple[list[dict[str, str]], list[str]]:
        roles: list[dict[str, str]] = []
        references: list[str] = []
        for item in assets.get("image", []):
            url = item.get("url")
            if not isinstance(url, str) or not url:
                continue
            role = item.get("role")
            if role in {"first_frame", "last_frame"}:
                roles.append({"url": url, "role": role})
            else:
                references.append(url)
        return roles, references

    @staticmethod
    def _option_url(value: object) -> str:
        if not isinstance(value, str):
            raise ProviderError("APIMart provider option URL is invalid")
        parsed = urlsplit(value)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
        ):
            raise ProviderError("APIMart provider option URL is invalid")
        return value

    @classmethod
    def _options(
        cls, profile: str, options: dict[str, object] | None
    ) -> dict[str, object]:
        values = options or {}
        if not isinstance(values, dict) or set(values) - cls._option_keys[profile]:
            raise ProviderError(
                "APIMart provider options are invalid for request profile"
            )
        # JSON values are accepted at the API boundary, but the adapter keeps
        # every profile's outbound fields explicit rather than forwarding a bag
        # of arbitrary provider parameters.
        return values

    @staticmethod
    def _common_body(
        *,
        provider: ModelPlayModeProvider,
        prompt: str | None,
        resolution: str | None,
        duration_seconds: int | None,
    ) -> dict[str, object]:
        body: dict[str, object] = {"model": provider.provider_model_id}
        if prompt:
            body["prompt"] = prompt
        if resolution:
            body["resolution"] = resolution.lower()
        if duration_seconds is not None:
            body["duration"] = duration_seconds
        return body

    @classmethod
    def _assert_no_frame_reference_mix(
        cls, *, roles: list[dict[str, str]], videos: list[str], audios: list[str]
    ) -> None:
        if roles and (videos or audios):
            raise ProviderError(
                "APIMart frame images cannot be combined with video or audio references"
            )

    def _seedance_2x_body(
        self,
        *,
        provider: ModelPlayModeProvider,
        prompt: str | None,
        assets: dict[str, list[dict[str, object]]],
        resolution: str | None,
        ratio: str | None,
        duration_seconds: int | None,
        audio_enabled: bool,
        options: dict[str, object],
    ) -> dict[str, object]:
        body = self._common_body(
            provider=provider,
            prompt=prompt,
            resolution=resolution,
            duration_seconds=duration_seconds,
        )
        if ratio:
            body["size"] = ratio
        body["generate_audio"] = audio_enabled
        roles, images = self._image_roles(assets)
        videos, audios = self._urls(assets, "video"), self._urls(assets, "audio")
        self._assert_no_frame_reference_mix(roles=roles, videos=videos, audios=audios)
        if roles:
            body["image_with_roles"] = roles
        elif images:
            body["image_urls"] = images
        if videos:
            body["video_urls"] = videos
        if audios:
            body["audio_urls"] = audios
        if (
            "seed" in options
            and isinstance(options["seed"], int)
            and not isinstance(options["seed"], bool)
        ):
            body["seed"] = options["seed"]
        elif "seed" in options:
            raise ProviderError("APIMart seed must be an integer")
        if "return_last_frame" in options and isinstance(
            options["return_last_frame"], bool
        ):
            body["return_last_frame"] = options["return_last_frame"]
        elif "return_last_frame" in options:
            raise ProviderError("APIMart return_last_frame must be a boolean")
        return body

    def _seedance_15_body(
        self,
        *,
        provider: ModelPlayModeProvider,
        prompt: str | None,
        assets: dict[str, list[dict[str, object]]],
        resolution: str | None,
        ratio: str | None,
        duration_seconds: int | None,
        audio_enabled: bool,
        options: dict[str, object],
    ) -> dict[str, object]:
        if self._urls(assets, "video") or self._urls(assets, "audio"):
            raise ProviderError(
                "Seedance 1.5 does not support video or audio references"
            )
        body = self._common_body(
            provider=provider,
            prompt=prompt,
            resolution=resolution,
            duration_seconds=duration_seconds,
        )
        if ratio:
            body["aspect_ratio"] = ratio
        body["audio"] = audio_enabled
        roles, images = self._image_roles(assets)
        if roles:
            body["image_with_roles"] = roles
        elif images:
            body["image_urls"] = images
        for key in ("seed", "camerafixed"):
            if key not in options:
                continue
            value = options[key]
            if key == "seed" and isinstance(value, int) and not isinstance(value, bool):
                body[key] = value
            elif key == "camerafixed" and isinstance(value, bool):
                body[key] = value
            else:
                raise ProviderError(f"APIMart {key} option is invalid")
        return body

    def _minimax_h3_body(
        self,
        *,
        provider: ModelPlayModeProvider,
        prompt: str | None,
        assets: dict[str, list[dict[str, object]]],
        resolution: str | None,
        ratio: str | None,
        duration_seconds: int | None,
    ) -> dict[str, object]:
        body = self._common_body(
            provider=provider,
            prompt=prompt,
            resolution=resolution,
            duration_seconds=duration_seconds,
        )
        if ratio:
            body["aspect_ratio"] = ratio
        roles, images = self._image_roles(assets)
        videos, audios = self._urls(assets, "video"), self._urls(assets, "audio")
        self._assert_no_frame_reference_mix(roles=roles, videos=videos, audios=audios)
        for item in roles:
            body[f"{item['role']}_image"] = item["url"]
        if images:
            body["image_urls"] = images
        if videos:
            body["video_urls"] = videos
        if audios:
            if not (images or videos):
                raise ProviderError(
                    "MiniMax-H3 audio references require an image or video reference"
                )
            body["audio_urls"] = audios
        return body

    def _wan_30_body(
        self,
        *,
        provider: ModelPlayModeProvider,
        prompt: str | None,
        assets: dict[str, list[dict[str, object]]],
        resolution: str | None,
        ratio: str | None,
        duration_seconds: int | None,
        options: dict[str, object],
    ) -> dict[str, object]:
        body = self._common_body(
            provider=provider,
            prompt=prompt,
            resolution=resolution,
            duration_seconds=duration_seconds,
        )
        if ratio:
            body["size"] = ratio
        roles, images = self._image_roles(assets)
        if roles:
            body["image_with_roles"] = roles
        elif images:
            body["image_urls"] = images
        for kind, field in (("video", "video_urls"), ("audio", "audio_urls")):
            urls = self._urls(assets, kind)
            if urls:
                body[field] = urls
        if "generation_type" in options:
            value = options["generation_type"]
            if not isinstance(value, str) or value not in {
                "first_frame",
                "first_last_frame",
                "reference",
            }:
                raise ProviderError("Wan 3.0 generation_type is invalid")
            body["generation_type"] = value
        for key in ("file_url", "link_url"):
            if key in options:
                body[key] = self._option_url(options[key])
        if "file_url" in body and "link_url" in body:
            raise ProviderError("Wan 3.0 file_url and link_url are mutually exclusive")
        if (
            not body.get("prompt")
            and not body.get("file_url")
            and not body.get("link_url")
            and not any(
                (
                    images,
                    roles,
                    self._urls(assets, "video"),
                    self._urls(assets, "audio"),
                )
            )
        ):
            raise ProviderError("Wan 3.0 requires prompt or reference input")
        return body

    def _kling_v3_body(
        self,
        *,
        provider: ModelPlayModeProvider,
        prompt: str | None,
        assets: dict[str, list[dict[str, object]]],
        ratio: str | None,
        duration_seconds: int | None,
        audio_enabled: bool,
        options: dict[str, object],
    ) -> dict[str, object]:
        if self._urls(assets, "video") or self._urls(assets, "audio"):
            raise ProviderError("Kling v3 does not support video or audio references")
        body = self._common_body(
            provider=provider,
            prompt=prompt,
            resolution=None,
            duration_seconds=duration_seconds,
        )
        if ratio:
            body["aspect_ratio"] = ratio
        image_urls = self._urls(assets, "image")
        if len(image_urls) > 2:
            raise ProviderError("Kling v3 supports at most two image references")
        if image_urls:
            body["image_urls"] = image_urls
        body["audio"] = audio_enabled
        for key in (
            "mode",
            "negative_prompt",
            "watermark",
            "multi_shot",
            "shot_type",
            "multi_prompt",
            "element_list",
        ):
            if key not in options:
                continue
            value = options[key]
            if key in {"mode", "negative_prompt", "shot_type"} and not isinstance(
                value, str
            ):
                raise ProviderError(f"Kling v3 {key} option is invalid")
            if key in {"watermark", "multi_shot"} and not isinstance(value, bool):
                raise ProviderError(f"Kling v3 {key} option is invalid")
            if key in {"multi_prompt", "element_list"} and not isinstance(value, list):
                raise ProviderError(f"Kling v3 {key} option is invalid")
            body[key] = value
        if body.get("multi_shot") and not isinstance(body.get("shot_type"), str):
            raise ProviderError(
                "Kling v3 shot_type is required when multi_shot is enabled"
            )
        return body

    def submit(
        self,
        *,
        model: Model,
        play_mode: ModelPlayMode,
        provider: ModelPlayModeProvider,
        task_id: str,
        prompt: str | None,
        assets: dict[str, list[dict[str, object]]],
        resolution: str | None,
        ratio: str | None,
        duration_seconds: int | None,
        audio_enabled: bool,
        options: dict[str, object] | None = None,
        messages: list[dict[str, object]] | None = None,
    ) -> ProviderResult:
        if model.model_type != "video":
            raise ProviderError("APIMart adapter supports video models only")
        profile = self._profile(provider)
        values = self._options(profile, options)
        builders = {
            "seedance_2x": lambda: self._seedance_2x_body(
                provider=provider,
                prompt=prompt,
                assets=assets,
                resolution=resolution,
                ratio=ratio,
                duration_seconds=duration_seconds,
                audio_enabled=audio_enabled,
                options=values,
            ),
            "seedance_15": lambda: self._seedance_15_body(
                provider=provider,
                prompt=prompt,
                assets=assets,
                resolution=resolution,
                ratio=ratio,
                duration_seconds=duration_seconds,
                audio_enabled=audio_enabled,
                options=values,
            ),
            "minimax_h3": lambda: self._minimax_h3_body(
                provider=provider,
                prompt=prompt,
                assets=assets,
                resolution=resolution,
                ratio=ratio,
                duration_seconds=duration_seconds,
            ),
            "wan_30": lambda: self._wan_30_body(
                provider=provider,
                prompt=prompt,
                assets=assets,
                resolution=resolution,
                ratio=ratio,
                duration_seconds=duration_seconds,
                options=values,
            ),
            "kling_v3": lambda: self._kling_v3_body(
                provider=provider,
                prompt=prompt,
                assets=assets,
                ratio=ratio,
                duration_seconds=duration_seconds,
                audio_enabled=audio_enabled,
                options=values,
            ),
        }
        raw = _json_request(
            url=self._submit_url(provider),
            method="POST",
            api_key=provider.api_key,
            body=builders[profile](),
            task_id=task_id,
        )
        entries = raw.get("data")
        entry = (
            entries[0]
            if isinstance(entries, list) and entries and isinstance(entries[0], dict)
            else None
        )
        if entry is None:
            raise ProviderError("APIMart provider response lacks task data")
        remote_id = entry.get("task_id")
        if not isinstance(remote_id, str) or not remote_id:
            raise ProviderError("APIMart provider response lacks task id")
        return ProviderResult(
            status=_ark_status(entry.get("status", "submitted")),
            provider_task_id=remote_id,
            raw=raw,
        )

    def get_status(
        self,
        *,
        model: Model,
        play_mode: ModelPlayMode,
        provider: ModelPlayModeProvider,
        provider_task_id: str,
    ) -> ProviderResult:
        if model.model_type != "video":
            raise ProviderError("APIMart adapter supports video models only")
        raw = _json_request(
            url=self._status_url(provider, provider_task_id),
            method=provider.status_query_method,
            api_key=provider.api_key,
            body={"task_id": provider_task_id}
            if provider.status_query_method == "POST"
            else None,
        )
        data = _object(raw.get("data"))
        if not data:
            raise ProviderError("APIMart provider status response is invalid")
        status = _ark_status(data.get("status"))
        result = _object(data.get("result"))
        videos = result.get("videos")
        first = (
            videos[0]
            if isinstance(videos, list) and videos and isinstance(videos[0], dict)
            else {}
        )
        url_value = first.get("url") if isinstance(first, dict) else None
        video_url = (
            url_value[0]
            if isinstance(url_value, list)
            and url_value
            and isinstance(url_value[0], str)
            else url_value
        )
        outputs = (
            (ProviderOutput(output_type="video", url=video_url),)
            if isinstance(video_url, str) and video_url
            else ()
        )
        error = _object(data.get("error"))
        error_code = error.get("code")
        return ProviderResult(
            status=status,
            provider_task_id=provider_task_id,
            outputs=outputs,
            raw=raw,
            error_code=str(error_code) if error_code is not None else None,
            error_message=error.get("message")
            if isinstance(error.get("message"), str)
            else None,
        )


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        return None
    return float(value)


class ProviderRegistry:
    """仅注册已实际实现的 Provider；未知代码不会静默降级。"""

    def __init__(self) -> None:
        self._providers: dict[str, ModelProvider] = {
            "volcengine": VolcArkProviderAdapter(),
            "anyfast": AnyFastProviderAdapter(),
            "duoyuanx": DuoyuanxProviderAdapter(),
            "apimart": ApimartProviderAdapter(),
        }

    def get(self, provider_code: str) -> ModelProvider:
        adapter = self._providers.get(provider_code)
        if adapter is None:
            raise ProviderError("provider adapter is not implemented")
        return adapter
