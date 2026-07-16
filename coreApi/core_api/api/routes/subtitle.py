from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.orm import Session

from core_api.api.dependencies import (
    get_database_session,
    get_request_id,
    require_service_token,
)
from core_api.api.routes.task_creation import (
    create_atomic_task,
    replay_atomic_task,
    require_idempotency_key,
)
from core_api.api.routes.tasks import TaskDispatcher, get_task_dispatcher


class SubtitleCueInput(BaseModel):
    """一个 UTF-8 SRT cue 的不可变输入。"""

    model_config = ConfigDict(extra="forbid")
    start: float = Field(ge=0, le=86_400)
    end: float = Field(gt=0, le=86_400)
    text: str = Field(min_length=1, max_length=10_000)


class SubtitleTaskRequest(BaseModel):
    """字幕生成任务公共输入。"""

    model_config = ConfigDict(extra="forbid")
    snapshot_id: str = Field(min_length=1, max_length=80)
    timeline: list[SubtitleCueInput] = Field(min_length=1, max_length=5_000)
    caller_task_id: str | None = Field(default=None, max_length=80)

    @model_validator(mode="after")
    def ordered(self) -> SubtitleTaskRequest:
        """拒绝重叠、倒序或非正时长的字幕 cue。"""

        previous = 0.0
        for item in self.timeline:
            if item.end <= item.start or item.start < previous:
                raise ValueError("字幕时间线无效")
            previous = item.end
        return self


router = APIRouter(dependencies=[Depends(require_service_token)])


@router.post("/tasks", status_code=status.HTTP_202_ACCEPTED)
def create_subtitle_task(
    payload: SubtitleTaskRequest,
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
    session: Annotated[Session, Depends(get_database_session)],
    dispatcher: Annotated[TaskDispatcher, Depends(get_task_dispatcher)],
    request_id: Annotated[str, Depends(get_request_id)],
) -> dict[str, object]:
    """幂等创建只消费不可变 revision 的字幕任务。"""
    body = payload.model_dump(mode="json")
    replay = replay_atomic_task(
        session=session,
        dispatcher=dispatcher,
        request_id=request_id,
        route="/api/v1/subtitle/tasks",
        idempotency_key=idempotency_key,
        idempotency_payload=body,
    )
    if replay is not None:
        return replay
    snapshot = {
        "snapshot_id": payload.snapshot_id,
        "timeline": [item.model_dump(mode="json") for item in payload.timeline],
    }
    return create_atomic_task(
        session=session,
        dispatcher=dispatcher,
        request_id=request_id,
        route="/api/v1/subtitle/tasks",
        task_type="subtitle",
        idempotency_key=idempotency_key,
        input_snapshot=snapshot,
        caller_task_id=payload.caller_task_id,
        idempotency_payload=body,
    )
