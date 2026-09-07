from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.orm import Session

from core_api.api.dependencies import (
    get_database_session,
    get_request_id,
    get_settings,
    require_service_token,
)
from core_api.api.routes.task_creation import (
    create_atomic_task,
    replay_atomic_task,
    require_idempotency_key,
)
from core_api.api.routes.tasks import TaskDispatcher, get_task_dispatcher
from core_api.api.routes.video_analysis import (
    build_model_execution_snapshot,
    validate_source_url,
)
from core_api.capabilities.service import CapabilityService
from core_api.config import Settings


class AudioUnderstandingSourceInput(BaseModel):
    """直接交给方舟的公网视频来源；模型只理解其中的内嵌音轨。"""

    model_config = ConfigDict(extra="forbid")

    source_asset_id: str = Field(min_length=1, max_length=80)
    video_url: str = Field(min_length=1, max_length=2048)
    video_name: str | None = Field(default=None, min_length=1, max_length=255)
    duration_seconds: float = Field(gt=0, le=600)


class AudioUnderstandingTaskRequest(BaseModel):
    """短剧音频理解任务；与通用 ASR API 完全分离。"""

    model_config = ConfigDict(extra="forbid")

    model_id: str = Field(min_length=1, max_length=80)
    sources: list[AudioUnderstandingSourceInput] = Field(min_length=1, max_length=5)
    language: str = Field(default="zh-CN", min_length=1, max_length=32)
    fps: int = Field(default=1, ge=1, le=1)
    min_frame_tokens: int = Field(default=64, ge=64, le=64)
    min_frame_tokens_mode: str = Field(
        default="provider_default", pattern="^provider_default$"
    )
    caller_task_id: str | None = Field(default=None, max_length=80)

    @model_validator(mode="after")
    def unique_sources(self) -> AudioUnderstandingTaskRequest:
        source_ids = [item.source_asset_id for item in self.sources]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("source_asset_id 不能重复")
        return self


router = APIRouter(dependencies=[Depends(require_service_token)])


@router.post("/tasks", status_code=status.HTTP_202_ACCEPTED)
def create_audio_understanding_task(
    payload: AudioUnderstandingTaskRequest,
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
    session: Annotated[Session, Depends(get_database_session)],
    dispatcher: Annotated[TaskDispatcher, Depends(get_task_dispatcher)],
    settings: Annotated[Settings, Depends(get_settings)],
    request_id: Annotated[str, Depends(get_request_id)],
) -> dict[str, object]:
    """冻结方舟模型和公开 URL 后创建一次音频理解任务。"""

    sources = [
        {
            **item.model_dump(mode="json", exclude_none=True),
            "video_url": validate_source_url(settings, item.video_url),
        }
        for item in payload.sources
    ]
    public = {
        "model_id": payload.model_id,
        "sources": sources,
        "language": payload.language,
        "fps": payload.fps,
        "min_frame_tokens": payload.min_frame_tokens,
        "min_frame_tokens_mode": payload.min_frame_tokens_mode,
        "caller_task_id": payload.caller_task_id,
    }
    replay = replay_atomic_task(
        session=session,
        dispatcher=dispatcher,
        request_id=request_id,
        route="/api/v1/audio-understanding/tasks",
        idempotency_key=idempotency_key,
        idempotency_payload=public,
    )
    if replay is not None:
        return replay
    capabilities = CapabilityService(session, settings.resolved_provider_secrets)
    model = capabilities.require_model(
        payload.model_id, "audio_understanding", language=payload.language
    )
    model_snapshot = build_model_execution_snapshot(
        model, capabilities.catalog().version
    )
    snapshot = {
        "model_id": payload.model_id,
        "model_snapshot": model_snapshot,
        "sources": sources,
        "source_order": [item.source_asset_id for item in payload.sources],
        "language": payload.language,
        "config_snapshot": {
            "fps": 1,
            "min_frame_tokens": 64,
            "min_frame_tokens_mode": "provider_default",
        },
    }
    return create_atomic_task(
        session=session,
        dispatcher=dispatcher,
        request_id=request_id,
        route="/api/v1/audio-understanding/tasks",
        task_type="audio_understanding",
        idempotency_key=idempotency_key,
        input_snapshot=snapshot,
        caller_task_id=payload.caller_task_id,
        idempotency_payload=public,
    )
