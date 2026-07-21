from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from core_api.api.dependencies import (
    ReadinessChecker,
    get_readiness_checker,
    get_request_id,
)
from core_api.api.responses import ApiResponse

router = APIRouter()


@router.get("/live", response_model=ApiResponse[dict[str, str]])
async def live(
    request_id: Annotated[str, Depends(get_request_id)],
) -> ApiResponse[dict[str, str]]:
    """确认 Core Web 进程仍可响应请求。"""

    return ApiResponse(
        code="OK",
        message="服务存活",
        data={"status": "live"},
        request_id=request_id,
    )


@router.get("/ready", response_model=ApiResponse[dict[str, str]])
async def ready(
    request_id: Annotated[str, Depends(get_request_id)],
    checker: Annotated[ReadinessChecker, Depends(get_readiness_checker)],
) -> ApiResponse[dict[str, str]]:
    """检查数据库、Redis 和必要配置是否可用。"""

    await checker()
    return ApiResponse(
        code="OK",
        message="服务就绪",
        data={"status": "ready"},
        request_id=request_id,
    )
