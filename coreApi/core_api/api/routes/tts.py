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
from core_api.capabilities.service import CapabilityService
from core_api.config import Settings


class TtsSegmentInput(BaseModel):
    """一段显式有序的配音文本。"""

    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=10_000)
    start: float = Field(ge=0, le=86_400)
    end: float = Field(gt=0, le=86_400)


class TtsTaskRequest(BaseModel):
    """稳定音色 TTS 任务公共输入。"""

    model_config = ConfigDict(extra="forbid")
    voice_id: str = Field(min_length=1, max_length=80)
    language: str = Field(default="zh-CN", min_length=1, max_length=32)
    output_format: str = Field(default="wav", pattern="^wav$")
    sample_rate: int = Field(default=16000, ge=8000, le=48000)
    segments: list[TtsSegmentInput] = Field(min_length=1, max_length=2_000)
    caller_task_id: str | None = Field(default=None, max_length=80)

    @model_validator(mode="after")
    def ordered(self) -> TtsTaskRequest:
        """拒绝重叠、倒序或非正时长的配音片段。"""

        previous = 0.0
        for item in self.segments:
            if item.end <= item.start or item.start < previous:
                raise ValueError("TTS 时间线无效")
            previous = item.end
        return self


router = APIRouter(dependencies=[Depends(require_service_token)])


def build_voice_snapshot(
    voice,
    catalog_version: str,
    *,
    output_format: str = "wav",
    sample_rate: int = 16_000,
) -> dict[str, object]:
    """冻结音色、供应商和执行配置引用，不保存真实密钥。"""
    settings = {
        key: value
        for key, value in (voice.provider.settings or {}).items()
        if key in {"base_url", "api_base", "tts_endpoint"}
    }
    return {
        "voice_id": voice.id,
        "catalog_version": catalog_version,
        "provider_code": voice.provider.code,
        "provider_voice_code": voice.provider_voice_code,
        "secret_ref": voice.provider.secret_ref,
        "provider_settings": settings,
        "supported_formats": sorted(voice.supported_formats),
        "supported_sample_rates": sorted(voice.supported_sample_rates),
        "languages": sorted(voice.languages),
        "output_format": output_format,
        "sample_rate": sample_rate,
    }


@router.post("/tasks", status_code=status.HTTP_202_ACCEPTED)
def create_tts_task(
    payload: TtsTaskRequest,
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
    session: Annotated[Session, Depends(get_database_session)],
    dispatcher: Annotated[TaskDispatcher, Depends(get_task_dispatcher)],
    settings: Annotated[Settings, Depends(get_settings)],
    request_id: Annotated[str, Depends(get_request_id)],
) -> dict[str, object]:
    """校验稳定 voice_id 后幂等创建 TTS 任务。"""
    public = payload.model_dump(mode="json")
    replay = replay_atomic_task(
        session=session,
        dispatcher=dispatcher,
        request_id=request_id,
        route="/api/v1/tts/tasks",
        idempotency_key=idempotency_key,
        idempotency_payload=public,
    )
    if replay is not None:
        return replay
    service = CapabilityService(session, settings.provider_secrets)
    voice = service.require_voice(
        payload.voice_id,
        language=payload.language,
        output_format=payload.output_format,
        sample_rate=payload.sample_rate,
    )
    snapshot = {
        "voice_id": payload.voice_id,
        "voice_snapshot": build_voice_snapshot(
            voice,
            service.catalog().version,
            output_format=payload.output_format,
            sample_rate=payload.sample_rate,
        ),
        "segments": [item.model_dump(mode="json") for item in payload.segments],
    }
    return create_atomic_task(
        session=session,
        dispatcher=dispatcher,
        request_id=request_id,
        route="/api/v1/tts/tasks",
        task_type="tts",
        idempotency_key=idempotency_key,
        input_snapshot=snapshot,
        caller_task_id=payload.caller_task_id,
        idempotency_payload=public,
    )
