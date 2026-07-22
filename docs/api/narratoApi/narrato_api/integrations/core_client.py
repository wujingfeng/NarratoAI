from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from typing import Any, cast
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class CoreClientError(RuntimeError):
    """Core 媒体探测请求未能安全完成。"""


def _duration_seconds(payload: object) -> float | None:
    """仅接受 Core 已验证媒体探测返回的正有限时长。"""

    if not isinstance(payload, dict):
        return None
    duration = payload.get("duration_seconds")
    if (
        isinstance(duration, bool)
        or not isinstance(duration, (int, float))
        or not math.isfinite(duration)
        or duration <= 0
    ):
        return None
    return float(duration)


@dataclass(frozen=True, slots=True)
class MediaProbeResult:
    """Core 返回的媒体校验结论；None 表示异步结果尚未返回。"""

    valid: bool | None
    core_task_id: str | None = None
    duration_seconds: float | None = None


@dataclass(frozen=True, slots=True)
class CoreJianyingResource:
    """发送给 Core 的已登记剪映资源。"""

    kind: str
    zip_path: str
    url: str
    size: int
    checksum: str
    content_type: str
    width: int | None = None
    height: int | None = None
    duration: float | None = None


@dataclass(frozen=True, slots=True)
class CoreJianyingManifestFile:
    """Core 返回的一项内联或 CDN Manifest 文件。"""

    zip_path: str
    content: str | None
    content_base64: str | None
    url: str | None
    size: int | None
    checksum: str | None
    content_type: str | None

    @classmethod
    def from_payload(cls, payload: object) -> CoreJianyingManifestFile:
        if not isinstance(payload, dict):
            raise CoreClientError("Core Jianying manifest response is invalid")
        values = {key: payload.get(key) for key in cls.__dataclass_fields__}
        if not isinstance(values["zip_path"], str) or not values["zip_path"]:
            raise CoreClientError("Core Jianying manifest response is invalid")
        if any(
            value is not None and not isinstance(value, expected)
            for value, expected in (
                (values["content"], str),
                (values["content_base64"], str),
                (values["url"], str),
                (values["size"], int),
                (values["checksum"], str),
                (values["content_type"], str),
            )
        ):
            raise CoreClientError("Core Jianying manifest response is invalid")
        return cls(
            content=cast(str | None, values["content"]),
            content_base64=cast(str | None, values["content_base64"]),
            zip_path=values["zip_path"],
            url=cast(str | None, values["url"]),
            size=cast(int | None, values["size"]),
            checksum=cast(str | None, values["checksum"]),
            content_type=cast(str | None, values["content_type"]),
        )


@dataclass(frozen=True, slots=True)
class CoreJianyingManifest:
    """Core 无状态生成的剪映基础文件和资源映射。"""

    template_version: str
    package_name: str
    files: tuple[CoreJianyingManifestFile, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "template_version": self.template_version,
            "package_name": self.package_name,
            "files": [asdict(item) for item in self.files],
        }


class HttpCoreClient:
    """只调用 Core 的媒体探测原子接口。"""

    def __init__(self, *, base_url: str, request_token: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.request_token = request_token

    def probe_media(
        self,
        *,
        source_url: str,
        media_type: str,
        declared_extension: str,
        caller_task_id: str,
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
            data = payload.get("data", payload)
            task_id = data.get("core_task_id") if isinstance(data, dict) else None
            if not isinstance(task_id, str) or not task_id:
                raise CoreClientError("Core media probe response is invalid")
            return MediaProbeResult(valid=None, core_task_id=task_id)
        data = payload.get("data", payload)
        valid = data.get("valid") if isinstance(data, dict) else None
        if not isinstance(valid, bool):
            raise CoreClientError("Core media probe response is invalid")
        return MediaProbeResult(valid=valid, duration_seconds=_duration_seconds(data))

    def get_probe_result(self, core_task_id: str) -> MediaProbeResult:
        """查询已提交 Core 原子任务的终态，不创建工作流。"""
        request = Request(
            f"{self.base_url}/api/v1/tasks/{core_task_id}",
            headers={"Authorization": f"Bearer {self.request_token}"},
        )
        try:
            with urlopen(request, timeout=10) as response:
                payload = json.loads(response.read() or b"{}")
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as error:
            raise CoreClientError("Core media probe query failed") from error
        data = payload.get("data", payload)
        state = data.get("status") if isinstance(data, dict) else None
        if state == "succeeded":
            result = data.get("result") if isinstance(data, dict) else None
            return MediaProbeResult(
                valid=True,
                core_task_id=core_task_id,
                duration_seconds=_duration_seconds(result),
            )
        if state == "failed":
            return MediaProbeResult(valid=False, core_task_id=core_task_id)
        return MediaProbeResult(valid=None, core_task_id=core_task_id)

    def build_jianying_manifest(
        self,
        *,
        snapshot_id: str,
        timeline: list[dict[str, Any]],
        resources: list[CoreJianyingResource],
    ) -> CoreJianyingManifest:
        """调用 Core 同步构建无状态剪映 Manifest，不创建 ZIP 或文件。"""

        if not self.request_token:
            raise CoreClientError("Core request token is not configured")
        body = json.dumps(
            {
                "snapshot_id": snapshot_id,
                "timeline": timeline,
                "resources": [asdict(resource) for resource in resources],
            }
        ).encode()
        request = Request(
            f"{self.base_url}/api/v1/jianying/manifests/build",
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.request_token}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urlopen(request, timeout=10) as response:
                payload = json.loads(response.read() or b"{}")
                status = response.status
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as error:
            raise CoreClientError("Core Jianying manifest request failed") from error
        data = payload.get("data", payload) if isinstance(payload, dict) else None
        if status != 200 or not isinstance(data, dict):
            raise CoreClientError("Core Jianying manifest response is invalid")
        template_version, package_name, files = (
            data.get("template_version"),
            data.get("package_name"),
            data.get("files"),
        )
        if (
            not isinstance(template_version, str)
            or not template_version
            or not isinstance(package_name, str)
            or not package_name
            or not isinstance(files, list)
        ):
            raise CoreClientError("Core Jianying manifest response is invalid")
        return CoreJianyingManifest(
            template_version=template_version,
            package_name=package_name,
            files=tuple(CoreJianyingManifestFile.from_payload(item) for item in files),
        )
