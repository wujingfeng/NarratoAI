from __future__ import annotations

import httpx
import time
import asyncio
import json

from core_api.tasks.callbacks import CallbackDeliveryResult, HttpCallbackClient


def test_http_callback_client_uses_private_bearer_idempotency_and_retries_rejections():
    """回调带事件幂等键，且只有 2xx 表示对端已接收。"""

    seen: list[httpx.Request] = []
    statuses = iter([503, 429, 408, 422, 204])

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(next(statuses))

    client = HttpCallbackClient(
        "https://narrato.example.test/api/v1/internal/core/callbacks",
        "callback-secret",
        transport=httpx.MockTransport(handler),
    )
    event = {
        "event_id": "evt_1",
        "core_task_id": "ctask_1",
        "attempt_no": 2,
        "state_version": 3,
        "status": "running",
    }

    assert [client.deliver(event) for _ in range(5)] == [
        CallbackDeliveryResult.RETRY,
        CallbackDeliveryResult.RETRY,
        CallbackDeliveryResult.RETRY,
        CallbackDeliveryResult.RETRY,
        CallbackDeliveryResult.SUCCESS,
    ]
    assert all(
        request.headers["Authorization"] == "Bearer callback-secret" for request in seen
    )
    assert all(request.headers["X-Idempotency-Key"] == "evt_1" for request in seen)
    assert all(request.method == "POST" for request in seen)
    assert all(json.loads(request.content) == event for request in seen)


def test_http_callback_client_rejects_unsafe_or_invalid_url():
    """回调目标必须是标准 443 DNS HTTPS endpoint。"""

    for url in (
        "http://example.test/callback",
        "https://u:p@example.test/callback",
        "https://example.test:bad/callback",
        "https://example.test:444/callback",
        "https://example.test/callback?secret=x",
        "https://127.0.0.1/callback",
        "https://10.0.0.1/callback",
        "https://localhost/callback",
        "https://bad_host.test/callback",
        "https://api.example.com/callback",
    ):
        try:
            HttpCallbackClient(url, "token")
        except ValueError as exc:
            assert str(exc) == "CALLBACK_URL_INVALID"
        else:
            raise AssertionError(url)


def test_all_non_2xx_callback_statuses_remain_retryable():
    statuses = [301, 307, 400, 401, 403, 404, 409, 422, 500, 503]
    for status in statuses:
        client = HttpCallbackClient(
            "https://narrato.example.test/callback",
            "token",
            transport=httpx.MockTransport(
                lambda _request, current=status: httpx.Response(current)
            ),
        )
        assert (
            client.deliver({"event_id": f"evt_{status}"})
            == CallbackDeliveryResult.RETRY
        )


def test_http_callback_client_maps_network_timeout_to_retry():
    """连接/读取超时只返回可重试分类且不暴露异常正文。"""

    def timeout(_request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("provider body with secret")

    client = HttpCallbackClient(
        "https://narrato.example.test/callback",
        "private-token",
        transport=httpx.MockTransport(timeout),
    )
    assert client.deliver({"event_id": "evt_timeout"}) == CallbackDeliveryResult.RETRY


def test_http_callback_client_enforces_total_timeout():
    """总时限必须主动取消慢请求，而非等待结束后才分类。"""

    async def slow(_request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(0.2)
        return httpx.Response(204)

    client = HttpCallbackClient(
        "https://narrato.example.test/callback",
        "private-token",
        total_timeout=0.02,
        transport=httpx.MockTransport(slow),
    )
    started = time.monotonic()
    assert client.deliver({"event_id": "evt_slow"}) == CallbackDeliveryResult.RETRY
    assert time.monotonic() - started < 0.15


def test_http_callback_client_rejects_late_success_when_transport_swallows_cancel():
    """传输层吞掉取消并迟到返回 2xx 时也不得把超时请求标记成功。"""

    class CancellationResistantTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            try:
                await asyncio.sleep(0.14)
            except asyncio.CancelledError:
                await asyncio.sleep(0.12)
            return httpx.Response(204, request=request)

    client = HttpCallbackClient(
        "https://narrato.example.test/callback",
        "private-token",
        total_timeout=0.02,
        transport=CancellationResistantTransport(),
    )
    started = time.monotonic()

    assert (
        client.deliver({"event_id": "evt_late_success"}) == CallbackDeliveryResult.RETRY
    )
    assert time.monotonic() - started >= 0.12
