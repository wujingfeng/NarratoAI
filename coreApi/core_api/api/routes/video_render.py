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
from core_api.api.routes.tts import build_voice_snapshot
from core_api.api.routes.video_analysis import validate_source_url
from core_api.capabilities.service import CapabilityService
from core_api.config import Settings


class RenderSourceInput(BaseModel):
    """显式排序的渲染媒体来源。"""

    model_config = ConfigDict(extra="forbid")
    source_asset_id: str = Field(min_length=1, max_length=80)
    video_url: str = Field(min_length=1, max_length=2048)


class RenderTimelineInput(BaseModel):
    """引用来源时间范围的渲染片段。"""

    model_config = ConfigDict(extra="forbid")
    source_asset_id: str = Field(min_length=1, max_length=80)
    start: float = Field(ge=0, le=86_400)
    end: float = Field(gt=0, le=86_400)
    narration: str = Field(min_length=1, max_length=10_000)
    subtitle: str | None = Field(default=None, max_length=10_000)
    original_sound: bool = False
    event_id: str | None = Field(default=None, max_length=160)
    visual_anchor: float | None = Field(default=None, ge=0, le=86_400)
    narration_anchor_text: str | None = Field(default=None, max_length=1_000)
    match_confidence: float | None = Field(default=None, ge=0, le=1)
    visual_lead: float = Field(default=0.15, ge=-2, le=2)
    narration_start_offset: float | None = Field(default=None, ge=0, le=86_400)


class VideoRenderTaskRequest(BaseModel):
    """只消费不可变 editor revision 的最终渲染请求。"""

    model_config = ConfigDict(extra="forbid")
    snapshot_id: str = Field(min_length=1, max_length=80)
    voice_id: str = Field(min_length=1, max_length=80)
    language: str = Field(default="zh-CN", min_length=1, max_length=32)
    sources: list[RenderSourceInput] = Field(min_length=1, max_length=20)
    timeline: list[RenderTimelineInput] = Field(min_length=1, max_length=2_000)
    render_config: dict[str, object] = Field(default_factory=dict)
    caller_task_id: str | None = Field(default=None, max_length=80)

    @model_validator(mode="after")
    def explicit_order(self) -> VideoRenderTaskRequest:
        """确认来源唯一且时间线首次出现顺序与 sources 一致。"""

        ids = [item.source_asset_id for item in self.sources]
        if len(ids) != len(set(ids)) or any(
            item.source_asset_id not in ids for item in self.timeline
        ):
            raise ValueError("渲染来源无效")
        first = list(dict.fromkeys(item.source_asset_id for item in self.timeline))
        if first != [item for item in ids if item in first]:
            raise ValueError("渲染来源顺序无效")
        return self


router = APIRouter(dependencies=[Depends(require_service_token)])


@router.post("/tasks", status_code=status.HTTP_202_ACCEPTED)
def create_video_render_task(
    payload: VideoRenderTaskRequest,
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
    session: Annotated[Session, Depends(get_database_session)],
    dispatcher: Annotated[TaskDispatcher, Depends(get_task_dispatcher)],
    settings: Annotated[Settings, Depends(get_settings)],
    request_id: Annotated[str, Depends(get_request_id)],
) -> dict[str, object]:
    """冻结 revision、source order 和 voice 能力后幂等创建渲染任务。"""
    sources = [
        {
            "source_asset_id": item.source_asset_id,
            "video_url": validate_source_url(settings, item.video_url),
        }
        for item in payload.sources
    ]
    public = {**payload.model_dump(mode="json"), "sources": sources}
    replay = replay_atomic_task(
        session=session,
        dispatcher=dispatcher,
        request_id=request_id,
        route="/api/v1/video-render/tasks",
        idempotency_key=idempotency_key,
        idempotency_payload=public,
    )
    if replay is not None:
        return replay
    capabilities = CapabilityService(session, settings.resolved_provider_secrets)
    voice = capabilities.require_voice(
        payload.voice_id,
        language=payload.language,
        output_format="wav",
        sample_rate=16000,
    )
    snapshot = {
        "snapshot_id": payload.snapshot_id,
        "voice_id": payload.voice_id,
        "voice_snapshot": build_voice_snapshot(voice, capabilities.catalog().version),
        "sources": sources,
        "source_order": [item.source_asset_id for item in payload.sources],
        "timeline": [item.model_dump(mode="json") for item in payload.timeline],
        "render_config": payload.render_config,
    }
    return create_atomic_task(
        session=session,
        dispatcher=dispatcher,
        request_id=request_id,
        route="/api/v1/video-render/tasks",
        task_type="video_render",
        idempotency_key=idempotency_key,
        input_snapshot=snapshot,
        caller_task_id=payload.caller_task_id,
        idempotency_payload=public,
    )
