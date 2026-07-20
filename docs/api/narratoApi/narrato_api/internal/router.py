from __future__ import annotations

import hmac
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import Field
from sqlalchemy.orm import sessionmaker

from narrato_api.api.dependencies import get_request_id, get_settings
from narrato_api.api.errors import ApiError
from narrato_api.api.responses import ApiResponse, StrictModel
from narrato_api.config import Settings
from narrato_api.workflows.reconciler import WorkflowReconciler

router = APIRouter()
_bearer = HTTPBearer(auto_error=False)


class CoreCallbackEvent(StrictModel):
    """Core 终态回调的最小版本化事件载荷。"""

    event_id: str = Field(min_length=1, max_length=128)
    core_task_id: str = Field(min_length=1, max_length=128)
    attempt_no: int = Field(ge=0)
    state_version: int = Field(ge=0)
    status: Literal["succeeded", "failed"]
    result: dict[str, object] = Field(default_factory=dict)
    error: dict[str, object] | None = None


class CoreCallbackReceipt(StrictModel):
    """回调接收确认只返回事件标识和幂等处理结果。"""

    event_id: str
    accepted: bool


def require_core_callback_token(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(_bearer)
    ],
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    """校验 Core 专用回调 Bearer，绝不复用请求方向 Token。"""

    if (
        credentials is None
        or credentials.scheme.lower() != "bearer"
        or not settings.core_callback_token
        or not hmac.compare_digest(
            credentials.credentials, settings.core_callback_token
        )
    ):
        raise ApiError("UNAUTHORIZED", "Authentication is required", 401)


def get_workflow_reconciler(request: Request) -> WorkflowReconciler:
    """构造共享数据库事实源上的回调收口器，测试可替换。"""

    return WorkflowReconciler(
        sessionmaker(bind=request.app.state.database_engine, expire_on_commit=False)
    )


@router.post(
    "/internal/core/callbacks",
    response_model=ApiResponse[CoreCallbackReceipt],
    dependencies=[Depends(require_core_callback_token)],
)
def receive_core_callback(
    body: CoreCallbackEvent,
    idempotency_key: Annotated[str | None, Header(alias="X-Idempotency-Key")] = None,
    reconciler: Annotated[WorkflowReconciler, Depends(get_workflow_reconciler)] = None,
    request_id: Annotated[str, Depends(get_request_id)] = "",
) -> ApiResponse[CoreCallbackReceipt]:
    """接收 Core 终态事件，要求 Header 和正文使用同一个事件 ID。"""

    if idempotency_key != body.event_id:
        raise ApiError(
            "CALLBACK_EVENT_ID_MISMATCH",
            "Callback event identifier does not match idempotency key",
            409,
        )
    accepted = reconciler.reconcile_callback(
        core_task_id=body.core_task_id,
        event_id=body.event_id,
        state_version=body.state_version,
        state=body.status,
        result={"result": body.result, "error": body.error, "attempt_no": body.attempt_no},
    )
    return ApiResponse(
        code="CORE_CALLBACK_ACCEPTED",
        message="Core callback accepted",
        request_id=request_id,
        data=CoreCallbackReceipt(event_id=body.event_id, accepted=accepted),
    )
