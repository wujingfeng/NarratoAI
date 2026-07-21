from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict

T = TypeVar("T")


class StrictModel(BaseModel):
    """拒绝未知字段的业务 DTO 基类。"""

    model_config = ConfigDict(extra="forbid")


class ApiResponse(StrictModel, Generic[T]):
    """所有业务接口共用的类型化响应信封。"""

    code: str
    message: str
    data: T | None = None
    request_id: str


class HealthData(StrictModel):
    """健康检查返回的明确数据结构。"""

    status: str


def envelope(
    *, request_id: str, code: str, message: str, data: object | None = None
) -> dict[str, object]:
    """构建可直接序列化且字段固定的统一信封。"""

    return {
        "code": code,
        "message": message,
        "data": data,
        "request_id": request_id,
    }
