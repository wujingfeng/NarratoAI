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
    ArtifactInput,
    ShortDramaConfigSnapshot,
    ShortDramaSourceInput,
    snapshot_sources,
    validate_source_url,
    build_model_execution_snapshot,
    validate_max_tokens,
)
from core_api.capabilities.service import CapabilityService
from core_api.config import Settings


class ScriptGenerationTaskRequest(BaseModel):
    """文案生成与初始编辑时间线任务的稳定公共输入。"""

    model_config = ConfigDict(extra="forbid")

    model_id: str = Field(min_length=1, max_length=80)
    analysis_artifact: ArtifactInput
    sources: list[ShortDramaSourceInput] = Field(min_length=1, max_length=5)
    language: str = Field(default="zh-CN", min_length=1, max_length=32)
    config_snapshot: ShortDramaConfigSnapshot = Field(
        default_factory=ShortDramaConfigSnapshot
    )
    caller_task_id: str | None = Field(default=None, max_length=80)

    @model_validator(mode="after")
    def unique_source_ids(self) -> ScriptGenerationTaskRequest:
        """文案阶段仍以请求 source 数组作为唯一排序事实。"""

        source_ids = [item.source_asset_id for item in self.sources]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("source_asset_id 不能重复")
        return self


router = APIRouter(dependencies=[Depends(require_service_token)])


@router.post("/tasks", status_code=status.HTTP_202_ACCEPTED)
def create_script_generation_task(
    payload: ScriptGenerationTaskRequest,
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
    session: Annotated[Session, Depends(get_database_session)],
    dispatcher: Annotated[TaskDispatcher, Depends(get_task_dispatcher)],
    settings: Annotated[Settings, Depends(get_settings)],
    request_id: Annotated[str, Depends(get_request_id)],
) -> dict[str, object]:
    """校验模型与前序分析 Artifact 后幂等创建异步文案任务。"""

    sources = snapshot_sources(settings, payload.sources)
    analysis_artifact = {
        "artifact_id": payload.analysis_artifact.artifact_id,
        "url": validate_source_url(
            settings, payload.analysis_artifact.url, core_artifact=True
        ),
    }
    idempotency_payload = {
        "model_id": payload.model_id,
        "analysis_artifact": analysis_artifact,
        "sources": sources,
        "language": payload.language,
        "config_snapshot": payload.config_snapshot.model_dump(mode="json"),
        "caller_task_id": payload.caller_task_id,
    }
    replay = replay_atomic_task(
        session=session,
        dispatcher=dispatcher,
        request_id=request_id,
        route="/api/v1/script-generation/tasks",
        idempotency_key=idempotency_key,
        idempotency_payload=idempotency_payload,
    )
    if replay is not None:
        return replay
    capabilities = CapabilityService(session, settings.provider_secrets)
    model = capabilities.require_model(
        payload.model_id, "script_generation", language=payload.language
    )
    catalog_version = capabilities.catalog().version
    model_snapshot = build_model_execution_snapshot(model, catalog_version)
    validate_max_tokens(payload.config_snapshot, model_snapshot)
    snapshot = {
        "model_id": payload.model_id,
        "model_snapshot": model_snapshot,
        "analysis_artifact": analysis_artifact,
        "sources": sources,
        "source_order": [item.source_asset_id for item in payload.sources],
        "language": payload.language,
        "config_snapshot": payload.config_snapshot.model_dump(mode="json"),
    }
    return create_atomic_task(
        session=session,
        dispatcher=dispatcher,
        request_id=request_id,
        route="/api/v1/script-generation/tasks",
        task_type="script_generation",
        idempotency_key=idempotency_key,
        input_snapshot=snapshot,
        caller_task_id=payload.caller_task_id,
        idempotency_payload=idempotency_payload,
    )
