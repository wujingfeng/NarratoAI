from __future__ import annotations

import json
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class CoreClientError(RuntimeError):
    """Core 媒体探测请求未能安全完成。"""


@dataclass(frozen=True, slots=True)
class MediaProbeResult:
    """Core 返回的媒体校验结论；None 表示异步结果尚未返回。"""

    valid: bool | None


class HttpCoreClient:
    """只调用 Core 的媒体探测原子接口。"""

    def __init__(self, *, base_url: str, request_token: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.request_token = request_token

    def probe_media(
        self, *, source_url: str, media_type: str, declared_extension: str, caller_task_id: str
    ) -> MediaProbeResult:
        """提交媒体探测，并兼容同步 Fake 与 Core 的 202 异步响应。"""

        if not self.request_token:
            raise CoreClientError("Core request token is not configured")
        body = json.dumps(
            {
                "source_url": source_url,
                "media_type": media_type,
                "declared_extension": declared_extension,
                "caller_task_id": caller_task_id,
            }
        ).encode()
        request = Request(
            f"{self.base_url}/api/v1/media-probe/tasks",
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.request_token}",
                "Content-Type": "application/json",
                "X-Idempotency-Key": caller_task_id,
            },
        )
        try:
            with urlopen(request, timeout=10) as response:
                payload = json.loads(response.read() or b"{}")
                status = response.status
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as error:
            raise CoreClientError("Core media probe request failed") from error
        if status == 202:
            return MediaProbeResult(valid=None)
        data = payload.get("data", payload)
        valid = data.get("valid") if isinstance(data, dict) else None
        if not isinstance(valid, bool):
            raise CoreClientError("Core media probe response is invalid")
        return MediaProbeResult(valid=valid)
