"""Provider Adapter registry.

数据库只配置连接点、模型 ID 与价格；供应商的请求字段、POST 查询参数和
状态映射均由本模块中的代码完成。当前生产 Adapter 覆盖火山方舟、AnyFast 与多元 x。
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from ipaddress import ip_address
from socket import getaddrinfo
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import quote as urlquote, urlsplit
from urllib.request import Request, urlopen

from narrato_api.products.model_generation import Model, ModelPlayMode, ModelPlayModeProvider


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
        if (value := payload.get(key)) is not None and isinstance(value, (str, int, float, bool))
    }
    return json.dumps(safe, ensure_ascii=False, separators=(",", ":")) if safe else "<unrecognized-json-error>"


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


def _json_request(*, url: str, method: str, api_key: str, body: object | None, task_id: str | None = None) -> dict[str, object]:
    if not api_key:
        raise ProviderError("provider API key is not configured")
    headers = {"Accept": "application/json", "Authorization": f"Bearer {api_key}"}
    data: bytes | None = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
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
        logger.warning("model_provider_transport_error type=%s task_id=%s", type(exc).__name__, task_id)
        raise ProviderError("provider request failed") from exc
    if not isinstance(loaded, dict):
        raise ProviderError("provider response is invalid")
    return loaded


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


def _video_content(prompt: str | None, assets: dict[str, list[dict[str, object]]]) -> list[dict[str, object]]:
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


def _image_body(provider: ModelPlayModeProvider, prompt: str | None, assets: dict[str, list[dict[str, object]]], resolution: str | None) -> dict[str, object]:
    body: dict[str, object] = {"model": provider.provider_model_id, "prompt": prompt or ""}
    image_urls = [str(item["url"]) for item in assets.get("image", []) if isinstance(item.get("url"), str)]
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
            outputs.append(ProviderOutput(output_type="image", url=url, content_type=output_format if isinstance(output_format, str) else None))
    _, output_token, generated_images = _usage(raw)
    if generated_images is None:
        generated_images = len(outputs)
    if generated_images < len(outputs):
        raise ProviderError("provider generated image count is inconsistent")
    if not outputs:
        raise ProviderError("provider returned no image outputs")
    return ProviderResult(status="succeeded", provider_task_id=None, outputs=tuple(outputs), output_token=output_token, generated_images=generated_images, raw=raw)


def _status_url(provider: ModelPlayModeProvider, provider_task_id: str, *, host: str) -> str:
    if not provider.status_query_url:
        raise ProviderError("provider status URL is not configured")
    url = provider.status_query_url.replace("{task_id}", urlquote(provider_task_id, safe=""))
    return _safe_https_url(url, expected_host=host)


class VolcArkProviderAdapter:
    """火山方舟的 LLM、Seedream 与 Seedance 真实协议适配。"""

    code = "volcengine"
    host = "ark.cn-beijing.volces.com"

    def _submit_url(self, provider: ModelPlayModeProvider) -> str:
        return _safe_https_url(provider.submit_url, expected_host=self.host)

    def _status_url(self, provider: ModelPlayModeProvider, provider_task_id: str) -> str:
        if not provider.status_query_url:
            raise ProviderError("provider status URL is not configured")
        url = provider.status_query_url.replace("{task_id}", urlquote(provider_task_id, safe=""))
        return _safe_https_url(url, expected_host=self.host)

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
        messages: list[dict[str, object]] | None = None,
    ) -> ProviderResult:
        url = self._submit_url(provider)
        if model.model_type == "llm":
            body = {
                "model": provider.provider_model_id,
                "messages": messages or [{"role": "user", "content": prompt or ""}],
            }
            raw = _json_request(url=url, method="POST", api_key=provider.api_key, body=body, task_id=task_id)
            return self._llm_result(raw)
        if model.model_type == "image":
            body: dict[str, object] = {"model": provider.provider_model_id, "prompt": prompt or ""}
            image_urls = [str(item["url"]) for item in assets.get("image", []) if isinstance(item.get("url"), str)]
            if image_urls:
                body["image"] = image_urls[0] if len(image_urls) == 1 else image_urls
            if resolution:
                body["size"] = resolution
            raw = _json_request(url=url, method="POST", api_key=provider.api_key, body=body, task_id=task_id)
            return self._image_result(raw)
        if model.model_type == "video":
            # Prompt aliases and the content array both use the frozen
            # ModelTaskAsset order; every media item retains its provider role.
            body = {"model": provider.provider_model_id, "content": _video_content(prompt, assets), "generate_audio": audio_enabled}
            if resolution:
                body["resolution"] = resolution
            if ratio:
                body["ratio"] = ratio
            if duration_seconds:
                body["duration"] = duration_seconds
            raw = _json_request(url=url, method="POST", api_key=provider.api_key, body=body, task_id=task_id)
            data = raw.get("data", raw)
            if not isinstance(data, dict):
                raise ProviderError("provider response is invalid")
            provider_task_id = data.get("id") or data.get("task_id")
            if not isinstance(provider_task_id, str) or not provider_task_id:
                raise ProviderError("provider response lacks task id")
            return ProviderResult(status=_ark_status(data.get("status", "queued")), provider_task_id=provider_task_id, raw=raw)
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
            raise ProviderError("synchronous provider task does not support status query")
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
            outputs = (ProviderOutput(output_type="video", url=video_url, duration_seconds=_number(data.get("duration"))),)
        error = data.get("error")
        error = error if isinstance(error, dict) else {}
        return ProviderResult(
            status=status,
            provider_task_id=provider_task_id,
            outputs=outputs,
            output_duration_seconds=_number(data.get("duration")),
            raw=raw,
            error_code=error.get("code") if isinstance(error.get("code"), str) else None,
            error_message=error.get("message") if isinstance(error.get("message"), str) else None,
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
        return ProviderResult(status="succeeded", provider_task_id=None, outputs=(ProviderOutput(output_type="text", text=text),), input_token=input_token, output_token=output_token, raw=raw)

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
                outputs.append(ProviderOutput(output_type="image", url=url, content_type=item.get("output_format") if isinstance(item.get("output_format"), str) else None))
        _, output_token, generated_images = _usage(raw)
        if generated_images is None:
            generated_images = len(outputs)
        if generated_images < len(outputs):
            raise ProviderError("provider generated image count is inconsistent")
        if not outputs:
            raise ProviderError("provider returned no image outputs")
        return ProviderResult(status="succeeded", provider_task_id=None, outputs=tuple(outputs), output_token=output_token, generated_images=generated_images, raw=raw)


class _ExternalMediaProviderAdapter:
    """Shared strict transport for documented media-provider APIs."""

    code = ""
    host = ""

    def _submit_url(self, provider: ModelPlayModeProvider) -> str:
        return _safe_https_url(provider.submit_url, expected_host=self.host)

    def _status_url(self, provider: ModelPlayModeProvider, provider_task_id: str) -> str:
        return _status_url(provider, provider_task_id, host=self.host)

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
    host = "www.anyfast.ai"

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
            raise ProviderError("synchronous provider task does not support status query")
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
            (ProviderOutput(output_type="video", url=video_url, duration_seconds=duration),)
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
            error_code=envelope.get("error_code") if isinstance(envelope.get("error_code"), str) else None,
            error_message=envelope.get("fail_reason") if isinstance(envelope.get("fail_reason"), str) else None,
        )


class DuoyuanxProviderAdapter(_ExternalMediaProviderAdapter):
    """多元 x 的 Seedream/Seedance 文生和参考生协议。"""

    code = "duoyuanx"
    host = "duoyuanx.com"

    @staticmethod
    def _resolution(value: str) -> str:
        """Normalize legacy UI/DB labels to the documented provider enum."""

        normalized = value.strip().lower()
        # Existing model capability rows used ``4K``; the provider API accepts
        # the lowercase enum ``4k`` alongside 480p/720p/1080p.
        return normalized

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

        metadata: dict[str, object] = {"generate_audio": audio_enabled, "watermark": False}
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
        return ProviderResult(status=_ark_status(data.get("status", "queued")), provider_task_id=remote_id, raw=raw)

    def get_status(
        self,
        *,
        model: Model,
        play_mode: ModelPlayMode,
        provider: ModelPlayModeProvider,
        provider_task_id: str,
    ) -> ProviderResult:
        if model.model_type != "video":
            raise ProviderError("synchronous provider task does not support status query")
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
            (ProviderOutput(output_type="video", url=video_url, duration_seconds=duration),)
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
            error_code=envelope.get("error_code") if isinstance(envelope.get("error_code"), str) else None,
            error_message=envelope.get("fail_reason") if isinstance(envelope.get("fail_reason"), str) else None,
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
        }

    def get(self, provider_code: str) -> ModelProvider:
        adapter = self._providers.get(provider_code)
        if adapter is None:
            raise ProviderError("provider adapter is not implemented")
        return adapter
