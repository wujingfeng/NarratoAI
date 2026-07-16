from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from narrato_api.api.dependencies import (
    ReadinessChecker,
    get_readiness_checker,
    get_request_id,
)
from narrato_api.api.errors import ServiceUnavailableError
from narrato_api.api.responses import ApiResponse, HealthData

router = APIRouter()


@router.get("/live", response_model=ApiResponse[HealthData])
async def live(
    request_id: Annotated[str, Depends(get_request_id)],
) -> ApiResponse[HealthData]:
    """确认业务 Web 进程存活且不访问外部依赖。"""

    return ApiResponse(
        code="OK",
        message="Service is live",
        data=HealthData(status="live"),
        request_id=request_id,
    )


@router.get("/ready", response_model=ApiResponse[HealthData])
async def ready(
    request_id: Annotated[str, Depends(get_request_id)],
    checker: Annotated[ReadinessChecker, Depends(get_readiness_checker)],
    details: Annotated[bool, Query()] = False,
) -> ApiResponse[HealthData]:
    """有界检查独立业务数据库和 Redis 是否可用。"""

    del details
    try:
        await checker()
    except ServiceUnavailableError:
        raise
    except Exception as error:
        raise ServiceUnavailableError() from error
    return ApiResponse(
        code="OK",
        message="Service is ready",
        data=HealthData(status="ready"),
        request_id=request_id,
    )
