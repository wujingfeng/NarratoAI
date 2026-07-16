from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from core_api.api.dependencies import (
    get_database_session,
    get_request_id,
    get_settings,
    require_service_token,
)
from core_api.api.errors import ApiError
from core_api.api.routes.task_creation import create_atomic_task, require_idempotency_key
from core_api.api.routes.tasks import TaskDispatcher, get_task_dispatcher
from core_api.config import Settings
from core_api.infrastructure.oss_client import CdnUrlPolicy, InputSecurityError


class AsrTaskRequest(BaseModel):
    """ASR 原子任务的稳定公共输入。"""

    model_config = ConfigDict(extra="forbid")

    source_url: str = Field(min_length=1, max_length=2048)
    declared_extension: str = Field(min_length=1, max_length=8)
    caller_task_id: str | None = Field(default=None, max_length=80)


router = APIRouter(dependencies=[Depends(require_service_token)])


@router.post("/tasks", status_code=status.HTTP_202_ACCEPTED)
def create_asr_task(
    payload: AsrTaskRequest,
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
    session: Annotated[Session, Depends(get_database_session)],
    dispatcher: Annotated[TaskDispatcher, Depends(get_task_dispatcher)],
    settings: Annotated[Settings, Depends(get_settings)],
    request_id: Annotated[str, Depends(get_request_id)],
) -> dict[str, object]:
    """幂等创建异步 ASR 任务。"""

    try:
        source_url = CdnUrlPolicy(set(settings.cdn_allowed_hosts)).validate(
            payload.source_url
        )
    except (InputSecurityError, ValueError) as exc:
        raise ApiError("SOURCE_URL_REJECTED", "媒体 URL 不符合 CDN 安全策略", 422) from exc
    snapshot = payload.model_dump(exclude={"caller_task_id"})
    snapshot["source_url"] = source_url
    return create_atomic_task(
        session=session,
        dispatcher=dispatcher,
        request_id=request_id,
        route="/api/v1/asr/tasks",
        task_type="asr",
        idempotency_key=idempotency_key,
        input_snapshot=snapshot,
        caller_task_id=payload.caller_task_id,
    )
