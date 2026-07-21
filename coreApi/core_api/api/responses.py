from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    """Core API 成功与失败共用的响应信封。"""

    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    data: T | None = None
    request_id: str


def envelope(
    *, request_id: str, code: str, message: str, data: T | None = None
) -> dict[str, object]:
    """构建可直接序列化的统一响应信封。"""

    return ApiResponse[T](
        code=code,
        message=message,
        data=data,
        request_id=request_id,
    ).model_dump()
