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
from core_api.api.errors import ApiError
from core_api.api.routes.task_creation import (
    create_atomic_task,
    replay_atomic_task,
    require_idempotency_key,
)
from core_api.api.routes.tasks import TaskDispatcher, get_task_dispatcher
from core_api.capabilities.service import CapabilityService
from core_api.config import Settings
from core_api.infrastructure.oss_client import CdnUrlPolicy, InputSecurityError


def _safe_execution_mapping(value: object) -> object:
    """递归裁剪任何疑似凭据键，执行快照只允许非秘密配置。"""

    if isinstance(value, dict):
        return {
            str(key): _safe_execution_mapping(item)
            for key, item in value.items()
            if not any(
                token in str(key).lower()
                for token in ("secret", "password", "token", "api_key", "credential")
            )
        }
    if isinstance(value, list):
        return [_safe_execution_mapping(item) for item in value]
    return value


def build_model_execution_snapshot(model, catalog_version: str) -> dict[str, object]:
    """冻结 Worker 所需执行参数；仅保存 secret_ref，不保存 secret。"""

    provider_settings = {
        key: value
        for key, value in (model.provider.settings or {}).items()
        if key in {"base_url", "api_base", "prompt_category"}
    }
    supported_limit_keys = {"max_input_chars", "max_output_items", "max_tokens"}
    provider_limits = {
        key: value
        for key, value in (model.provider.limits or {}).items()
        if key in supported_limit_keys and type(value) is int and value > 0
    }
    model_limits = {
        key: value
        for key, value in (model.limits or {}).items()
        if key in supported_limit_keys and type(value) is int and value > 0
    }
    return {
        "model_id": model.id,
        "catalog_version": catalog_version,
        "provider_code": model.provider.code,
        "provider_model_code": model.provider_model_code,
        "secret_ref": model.provider.secret_ref,
        "provider_settings": provider_settings,
        # 这些键和值已经经过显式 allowlist/type 校验；max_tokens 不是凭据。
        "provider_limits": provider_limits,
        "model_limits": model_limits,
        "capability_types": sorted(model.capability_types),
        "languages": sorted(model.languages),
    }


class ArtifactInput(BaseModel):
    """引用一个已登记 Core Artifact 的稳定公开输入。"""

    model_config = ConfigDict(extra="forbid")

    artifact_id: str = Field(min_length=1, max_length=80)
    url: str = Field(min_length=1, max_length=2048)


class ShortDramaSourceInput(BaseModel):
    """按用户顺序声明一个视频及可选显式字幕。"""

    model_config = ConfigDict(extra="forbid")

    source_asset_id: str = Field(min_length=1, max_length=80)
    video_url: str = Field(min_length=1, max_length=2048)
    subtitle_url: str | None = Field(default=None, min_length=1, max_length=2048)
    subtitle_artifact: ArtifactInput | None = None
    duration_seconds: float | None = Field(default=None, gt=0, le=600)

    @model_validator(mode="after")
    def only_one_subtitle_reference(self) -> ShortDramaSourceInput:
        """禁止同时提交 URL 和 Artifact，避免字幕来源产生歧义。"""

        if self.subtitle_url is not None and self.subtitle_artifact is not None:
            raise ValueError("字幕 URL 与 Artifact 只能提供一种")
        return self


class ShortDramaConfigSnapshot(BaseModel):
    """第一版已确认且不会携带供应商私密字段的用户配置快照。"""

    model_config = ConfigDict(extra="forbid")

    drama_genre: str = Field(default="", max_length=120)
    narration_style: str = Field(default="", max_length=120)
    original_sound_ratio: int = Field(default=30, ge=0, le=100)
    temperature: float = Field(default=0.7, ge=0, le=2)
    max_tokens: int = Field(default=4096, ge=1, le=131072)


def validate_max_tokens(config: ShortDramaConfigSnapshot, model_snapshot: dict[str, object]) -> None:
    """创建任务时拒绝超过冻结模型上限的 token 配额。"""
    limits = model_snapshot.get("model_limits", {})
    provider_limits = model_snapshot.get("provider_limits", {})
    candidates = [
        value
        for value in (
            limits.get("max_tokens") if isinstance(limits, dict) else None,
            provider_limits.get("max_tokens")
            if isinstance(provider_limits, dict)
            else None,
        )
        if type(value) is int and value > 0
    ]
    maximum = min(candidates) if candidates else None
    if type(maximum) is int and config.max_tokens > maximum:
        raise ApiError("MAX_TOKENS_EXCEEDED", "max_tokens 超过模型上限", 422)


class VideoAnalysisTaskRequest(BaseModel):
    """剧情分析异步任务的稳定公共输入。"""

    model_config = ConfigDict(extra="forbid")

    model_id: str = Field(min_length=1, max_length=80)
    sources: list[ShortDramaSourceInput] = Field(min_length=1, max_length=5)
    language: str = Field(default="zh-CN", min_length=1, max_length=32)
    config_snapshot: ShortDramaConfigSnapshot = Field(
        default_factory=ShortDramaConfigSnapshot
    )
    caller_task_id: str | None = Field(default=None, max_length=80)

    @model_validator(mode="after")
    def validate_explicit_sources(self) -> VideoAnalysisTaskRequest:
        """分析必须显式提供每个来源字幕且 source_asset_id 唯一。"""

        source_ids = [item.source_asset_id for item in self.sources]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("source_asset_id 不能重复")
        if any(
            item.subtitle_url is None and item.subtitle_artifact is None
            for item in self.sources
        ):
            # 本 Task 不隐式触发 ASR，业务 DAG 必须先提供 Task7 字幕产物。
            raise ValueError("每个分析来源都必须显式提供字幕")
        return self


router = APIRouter(dependencies=[Depends(require_service_token)])


def validate_source_url(
    settings: Settings, value: str, *, core_artifact: bool = False
) -> str:
    """按输入类型验证业务对象或 Core Artifact 的公开 CDN URL。"""

    prefix = "/narrato/coreApi/" if core_artifact else "/narrato/api/"
    try:
        return CdnUrlPolicy(set(settings.cdn_allowed_hosts), prefix=prefix).validate(
            value
        )
    except (InputSecurityError, ValueError) as exc:
        raise ApiError(
            "SOURCE_URL_REJECTED", "来源 URL 不符合 CDN 安全策略", 422
        ) from exc


def snapshot_sources(
    settings: Settings, sources: list[ShortDramaSourceInput]
) -> list[dict[str, object]]:
    """保持输入顺序并将全部 URL 规范化为不可变任务快照。"""

    result: list[dict[str, object]] = []
    for source in sources:
        item = source.model_dump(mode="json", exclude_none=True)
        item["video_url"] = validate_source_url(settings, source.video_url)
        if source.subtitle_url is not None:
            item["subtitle_url"] = validate_source_url(settings, source.subtitle_url)
        elif source.subtitle_artifact is not None:
            item["subtitle_artifact"] = {
                "artifact_id": source.subtitle_artifact.artifact_id,
                "url": validate_source_url(
                    settings, source.subtitle_artifact.url, core_artifact=True
                ),
            }
        result.append(item)
    return result


@router.post("/tasks", status_code=status.HTTP_202_ACCEPTED)
def create_video_analysis_task(
    payload: VideoAnalysisTaskRequest,
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
    session: Annotated[Session, Depends(get_database_session)],
    dispatcher: Annotated[TaskDispatcher, Depends(get_task_dispatcher)],
    settings: Annotated[Settings, Depends(get_settings)],
    request_id: Annotated[str, Depends(get_request_id)],
) -> dict[str, object]:
    """校验稳定模型能力并幂等创建异步剧情分析任务。"""

    sources = snapshot_sources(settings, payload.sources)
    idempotency_payload = {
        "model_id": payload.model_id,
        "sources": sources,
        "language": payload.language,
        "config_snapshot": payload.config_snapshot.model_dump(mode="json"),
        "caller_task_id": payload.caller_task_id,
    }
    replay = replay_atomic_task(
        session=session,
        dispatcher=dispatcher,
        request_id=request_id,
        route="/api/v1/video-analysis/tasks",
        idempotency_key=idempotency_key,
        idempotency_payload=idempotency_payload,
    )
    if replay is not None:
        return replay
    capabilities = CapabilityService(session, settings.provider_secrets)
    model = capabilities.require_model(
        payload.model_id, "video_analysis", language=payload.language
    )
    catalog_version = capabilities.catalog().version
    model_snapshot = build_model_execution_snapshot(model, catalog_version)
    validate_max_tokens(payload.config_snapshot, model_snapshot)
    snapshot = {
        "model_id": payload.model_id,
        "model_snapshot": model_snapshot,
        "sources": sources,
        "source_order": [item.source_asset_id for item in payload.sources],
        "language": payload.language,
        "config_snapshot": payload.config_snapshot.model_dump(mode="json"),
    }
    return create_atomic_task(
        session=session,
        dispatcher=dispatcher,
        request_id=request_id,
        route="/api/v1/video-analysis/tasks",
        task_type="video_analysis",
        idempotency_key=idempotency_key,
        input_snapshot=snapshot,
        caller_task_id=payload.caller_task_id,
        idempotency_payload=idempotency_payload,
    )
