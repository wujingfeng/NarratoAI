from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class ApiError(Exception):
    """携带稳定错误码和 HTTP 状态的公开异常。"""

    code: str
    message: str
    status_code: int
    data: object | None = None


class ServiceUnavailableError(ApiError):
    """表示 Core 依赖服务暂时未就绪。"""

    def __init__(self, message: str = "依赖服务未就绪") -> None:
        super().__init__("SERVICE_UNAVAILABLE", message, 503)


class UnauthorizedError(ApiError):
    """表示服务间 Bearer Token 无效。"""

    def __init__(self, message: str = "服务凭据无效") -> None:
        super().__init__("UNAUTHORIZED", message, 401)


class CapabilityUnavailableError(ApiError):
    """表示稳定能力 ID 当前不存在或不可调用。"""

    def __init__(self, message: str = "能力当前不可用") -> None:
        super().__init__("CAPABILITY_UNAVAILABLE", message, 409)
