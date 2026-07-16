from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class ApiError(Exception):
    """携带稳定错误码和安全公开消息的业务异常。"""

    code: str
    message: str
    status_code: int
    data: object | None = None


class ServiceUnavailableError(ApiError):
    """表示业务服务依赖暂时不可用。"""

    def __init__(self) -> None:
        """初始化不泄露依赖细节的 503 异常。"""

        super().__init__(
            "SERVICE_UNAVAILABLE", "Service dependencies are unavailable", 503
        )
