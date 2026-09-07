"""数据库驱动的图片/视频生成 API，以及兼容的 AI 视频路由。

模型能力、供应商和价格均由标准化表下发。业务服务直接调用 Provider；Core
仅用于已转存视频的媒体信息获取，不参与第三方模型请求中转。
"""
from __future__ import annotations

import re
import secrets
import time
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, ROUND_CEILING
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, Query, Request, status
from pydantic import Field, field_validator
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from narrato_api.api.dependencies import get_request_id
from narrato_api.api.errors import ApiError
from narrato_api.api.responses import ApiResponse, StrictModel
from narrato_api.assets.models import Asset
from narrato_api.auth.router import bearer_token, get_auth_service
from narrato_api.auth.service import AuthService
from narrato_api.billing.service import _apply_credit, _locked_account
from narrato_api.projects.models import Project
from narrato_api.products.model_generation import (
    Model,
    ModelPlayMode,
    ModelPlayModeProvider,
    ModelPlayModeProviderPrice,
    ModelPlayModeRule,
    ModelTask,
    ModelTaskAsset,
    ModelTaskCharge,
    ModelTaskOutput,
    utc_now,
)
from narrato_api.products.providers import ProviderError, ProviderRegistry, ProviderResult

PRODUCT = "ai_video"
AI_VIDEO_MODEL_TYPES = ("image", "video")
ACTIVE_STATES = ("submitting", "queued", "processing", "finalizing")
_CHINESE = re.compile(r"[\u3400-\u9fff\uf900-\ufaff]")
_ENGLISH_WORD = re.compile(r"[A-Za-z]+(?:['-][A-Za-z]+)*")
_ASSET_MARKER = re.compile(r"\{\{asset:([A-Za-z0-9_-]+)\}\}")

# Backward-compatible Python symbols used by existing service imports. Their DB
# tables are now generic models/model_tasks after migration 0031.
AiVideoModel = Model
AiVideoTask = ModelTask


def _id(prefix: str) -> str:
    return f"{prefix}_{time.time_ns():x}{secrets.token_hex(6)}"


class InputRuleData(StrictModel):
    type: Literal["text", "image", "video", "audio"]
    supported: bool
    required: bool
    max_count: int | None = None
    max_file_size_bytes: int | None = None
    max_duration_seconds: int | None = None
    max_text_units: int | None = None
    supports_mention: bool = False


class OutputOptionData(StrictModel):
    type: Literal["resolution", "ratio", "duration"]
    values: list[str] = Field(default_factory=list)


class PlayModeData(StrictModel):
    id: str
    code: str
    display_name: str
    description: str | None = None
    default_credits: int
    supports_generate_audio: bool
    inputs: list[InputRuleData]
    output_options: list[OutputOptionData]


class ModelSummaryData(StrictModel):
    """模型列表所需的轻量展示信息，不携带玩法及规则明细。"""

    id: str
    display_name: str
    provider_code: str
    output_type: Literal["image", "video"]
    description: str | None = None
    cover_url: str | None = None
    category: str
    is_default: bool


class ModelGenParamData(ModelSummaryData):
    """用户选中模型后，按需加载的玩法、能力和计费展示信息。"""

    play_modes: list[PlayModeData]
    default_play_mode_id: str | None = None
    capabilities: dict[str, object] = Field(default_factory=dict)
    price: dict[str, object] = Field(default_factory=dict)


class ModelsData(StrictModel):
    items: list[ModelSummaryData]
    default_model_id: str | None = None


class DraftData(StrictModel):
    project_id: str


class QuoteRequest(StrictModel):
    model_id: str = Field(min_length=1, max_length=64)
    play_mode_id: str | None = Field(default=None, max_length=64)
    resolution: str | None = Field(default=None, max_length=32)
    duration_seconds: int | None = Field(default=None, ge=-1, le=3600)


class QuoteData(StrictModel):
    model_id: str
    play_mode_id: str
    credits: int
    billing_units: list[str]


class ReferenceMappingData(StrictModel):
    """一次提交中某个参考素材的语义说明；只用于编译最终 Prompt。"""

    asset_id: str = Field(min_length=1, max_length=64)
    description: str = Field(min_length=1, max_length=1000)

    @field_validator("description")
    @classmethod
    def normalized_description(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("reference mapping description must not be blank")
        return normalized


class TaskCreateRequest(StrictModel):
    project_id: str = Field(min_length=1, max_length=64)
    model_id: str = Field(min_length=1, max_length=64)
    play_mode_id: str | None = Field(default=None, max_length=64)
    prompt: str | None = Field(default=None, max_length=16000)
    image_asset_ids: list[str] = Field(default_factory=list, max_length=50)
    video_asset_ids: list[str] = Field(default_factory=list, max_length=50)
    audio_asset_ids: list[str] = Field(default_factory=list, max_length=50)
    resolution: str | None = Field(default=None, max_length=32)
    ratio: str | None = Field(default=None, max_length=16)
    duration_seconds: int | None = Field(default=None, ge=-1, le=3600)
    audio_enabled: bool = False
    # Provider 专有字段只能由对应 request_profile 的白名单消费；该值会随任务冻结。
    provider_options: dict[str, object] = Field(default_factory=dict)
    # 兼容旧客户端的素材引用标记；服务端会从素材和 Prompt 自动补齐映射说明。
    multi_subject_references: list[str] = Field(default_factory=list, max_length=50)
    # 保留给 API 集成方覆盖系统推断；Web 工作台不展示该输入项。
    reference_mappings: list[ReferenceMappingData] = Field(default_factory=list, max_length=50)

    @field_validator("image_asset_ids", "video_asset_ids", "audio_asset_ids", "multi_subject_references")
    @classmethod
    def distinct_ids(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("asset IDs must not contain duplicates")
        return value

    @field_validator("reference_mappings")
    @classmethod
    def distinct_mapping_assets(cls, value: list[ReferenceMappingData]) -> list[ReferenceMappingData]:
        if len(value) != len({item.asset_id for item in value}):
            raise ValueError("reference mappings must not contain duplicate asset IDs")
        return value


class LlmCompletionRequest(StrictModel):
    model_id: str = Field(min_length=1, max_length=64)
    play_mode_id: str | None = Field(default=None, max_length=64)
    project_id: str | None = Field(default=None, max_length=64)
    prompt: str | None = Field(default=None, max_length=16000)
    image_asset_ids: list[str] = Field(default_factory=list, max_length=50)
    video_asset_ids: list[str] = Field(default_factory=list, max_length=50)
    audio_asset_ids: list[str] = Field(default_factory=list, max_length=50)
    multi_subject_references: list[str] = Field(default_factory=list, max_length=50)

    @field_validator("image_asset_ids", "video_asset_ids", "audio_asset_ids", "multi_subject_references")
    @classmethod
    def distinct_ids(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("asset IDs must not contain duplicates")
        return value


class OutputData(StrictModel):
    type: Literal["text", "image", "video"]
    cdn_url: str | None = None
    text: str | None = None
    duration_seconds: float | None = None


class TaskData(StrictModel):
    id: str
    project_id: str | None = None
    model_id: str
    model_name: str
    play_mode_id: str
    type: Literal["llm", "image", "video"]
    status: str
    provider_task_id: str | None = None
    credits: int
    final_credits: int | None = None
    input_token: int | None = None
    output_token: int | None = None
    outputs: list[OutputData] = Field(default_factory=list)
    input: dict[str, object] = Field(default_factory=dict)
    output: dict[str, object] | None = None
    error_code: str | None = None
    error_message: str | None = None
    created_at: str
    updated_at: str


class TasksData(StrictModel):
    items: list[TaskData]
    view: Literal["list", "gallery"]
    total: int
    page: int
    page_size: int
    has_next: bool


@dataclass(frozen=True, slots=True)
class ValidatedInput:
    prompt: str | None
    assets: dict[str, list[Asset]]
    mentioned_ids: set[str]
    resolution: str | None
    ratio: str | None
    duration_seconds: int | None
    audio_enabled: bool


router = APIRouter()


def get_provider_registry(request: Request) -> ProviderRegistry:
    return getattr(request.app.state, "model_provider_registry", ProviderRegistry())


def _text_units(value: str) -> int:
    return len(_CHINESE.findall(value)) + len(_ENGLISH_WORD.findall(value))


def _rules(session: Session, play_mode_id: str) -> list[ModelPlayModeRule]:
    return list(session.scalars(select(ModelPlayModeRule).where(ModelPlayModeRule.play_mode_id == play_mode_id).order_by(ModelPlayModeRule.sort_order.desc(), ModelPlayModeRule.id)))


def _mode_data(session: Session, mode: ModelPlayMode) -> PlayModeData:
    inputs: list[InputRuleData] = []
    outputs: list[OutputOptionData] = []
    for rule in _rules(session, mode.id):
        if rule.rule_kind == "input_constraint" and rule.input_type:
            inputs.append(InputRuleData(type=rule.input_type, supported=rule.is_supported, required=rule.is_required, max_count=rule.max_count, max_file_size_bytes=rule.max_file_size_bytes, max_duration_seconds=rule.max_duration_seconds, max_text_units=rule.max_text_units, supports_mention=rule.supports_mention))
        elif rule.rule_kind == "output_option" and rule.output_option_type:
            values = rule.resolution if rule.output_option_type == "resolution" else rule.ratio if rule.output_option_type == "ratio" else rule.duration_seconds
            outputs.append(OutputOptionData(type=rule.output_option_type, values=[_output_option_key(value) for value in values or []]))
    return PlayModeData(id=mode.id, code=mode.code, display_name=mode.display_name, description=mode.description, default_credits=mode.default_credits, supports_generate_audio=mode.supports_generate_audio, inputs=inputs, output_options=outputs)


def _model_summary(session: Session, model: Model) -> ModelSummaryData:
    """返回模型卡片的基础字段；玩法规则由详情接口按需返回。"""
    modes = list(session.scalars(select(ModelPlayMode).where(ModelPlayMode.model_id == model.id, ModelPlayMode.is_enabled.is_(True)).order_by(ModelPlayMode.sort_order.desc(), ModelPlayMode.id)))
    default_mode = next((mode.id for mode in modes if mode.is_default), modes[0].id if modes else None)
    provider = None
    if default_mode:
        mode = next(mode for mode in modes if mode.id == default_mode)
        provider = session.get(ModelPlayModeProvider, mode.active_provider_id) if mode.active_provider_id else None
    return ModelSummaryData(id=model.id, display_name=model.display_name, provider_code=provider.provider_code if provider else "", output_type=model.model_type, description=model.description, cover_url=model.cover_url, category=model.category, is_default=model.is_default)


def _model_gen_params(session: Session, model: Model) -> ModelGenParamData:
    """返回选中模型的完整生成参数；不会出现在模型列表响应中。"""
    summary = _model_summary(session, model)
    modes = list(session.scalars(select(ModelPlayMode).where(ModelPlayMode.model_id == model.id, ModelPlayMode.is_enabled.is_(True)).order_by(ModelPlayMode.sort_order.desc(), ModelPlayMode.id)))
    default_mode = next((mode.id for mode in modes if mode.is_default), modes[0].id if modes else None)
    public_modes = [_mode_data(session, mode) for mode in modes]
    selected = next((item for item in public_modes if item.id == default_mode), None)
    return ModelGenParamData(**summary.model_dump(), play_modes=public_modes, default_play_mode_id=default_mode, capabilities=_compat_capabilities(selected), price={"credits": selected.default_credits if selected else 0})


# 供现有内部调用和测试兼容；HTTP 列表接口使用 _model_summary。
_public_model = _model_gen_params


def _compat_capabilities(mode: PlayModeData | None) -> dict[str, object]:
    """AI-video 现有页面的过渡合同；数据仍完全来自规则表。"""
    if mode is None:
        return {}
    input_by_type = {item.type: item for item in mode.inputs}
    values: dict[str, object] = {
        f"{kind}_upload": {"enabled": bool(rule and rule.supported), "max_count": (rule.max_count or 0) if rule else 0}
        for kind, rule in (("image", input_by_type.get("image")), ("video", input_by_type.get("video")), ("audio", input_by_type.get("audio")))
    }
    values["multi_subject_reference"] = any(item.supports_mention for item in mode.inputs)
    values["audio_switch"] = mode.supports_generate_audio
    values["resolutions"] = [value for item in mode.output_options if item.type == "resolution" for value in item.values]
    values["ratios"] = [value for item in mode.output_options if item.type == "ratio" for value in item.values]
    duration = [value for item in mode.output_options if item.type == "duration" for value in item.values]
    if duration:
        values["duration"] = {"options": duration, "adaptive": "adaptive" in duration}
    return values


def _selected_mode(session: Session, model: Model, requested_id: str | None) -> ModelPlayMode:
    statement = select(ModelPlayMode).where(ModelPlayMode.model_id == model.id, ModelPlayMode.is_enabled.is_(True))
    if requested_id:
        statement = statement.where(ModelPlayMode.id == requested_id)
    else:
        statement = statement.order_by(ModelPlayMode.is_default.desc(), ModelPlayMode.sort_order.desc(), ModelPlayMode.id)
    mode = session.scalar(statement)
    if mode is None:
        raise ApiError("MODEL_PLAY_MODE_NOT_FOUND", "Model play mode is not available", 404)
    return mode


def _active_provider(session: Session, mode: ModelPlayMode) -> ModelPlayModeProvider:
    provider = session.get(ModelPlayModeProvider, mode.active_provider_id) if mode.active_provider_id else None
    if provider is None or provider.play_mode_id != mode.id or not provider.is_enabled:
        raise ApiError("MODEL_PROVIDER_NOT_AVAILABLE", "Model provider is not available", 503)
    return provider


def _input_rule_map(rules: list[ModelPlayModeRule]) -> dict[str, ModelPlayModeRule]:
    return {rule.input_type: rule for rule in rules if rule.rule_kind == "input_constraint" and rule.input_type}


def _output_option_key(value: object) -> str:
    """Canonicalize case-insensitive model option values at the API boundary."""

    return str(value).strip().lower()


def _select_output_option(rules: list[ModelPlayModeRule], kind: str, requested: str | int | None) -> str | int | None:
    options = [rule for rule in rules if rule.rule_kind == "output_option" and rule.output_option_type == kind and rule.is_supported]
    if not options:
        return requested
    supported: list[str] = []
    for rule in options:
        values = rule.resolution if kind == "resolution" else rule.ratio if kind == "ratio" else rule.duration_seconds
        supported.extend(_output_option_key(value) for value in values or [])
    if not supported:
        return requested
    if requested is None:
        selected = supported[0]
    elif _output_option_key(requested) in supported:
        selected = _output_option_key(requested)
    else:
        raise ApiError("MODEL_OUTPUT_OPTION_UNSUPPORTED", f"{kind} is not supported by this play mode", 422)
    if kind == "duration":
        return None if selected == "adaptive" else int(selected)
    return selected


def _validate_input(
    *,
    session: Session,
    user_id: str,
    project_id: str | None,
    model: Model,
    mode: ModelPlayMode,
    prompt: str | None,
    image_asset_ids: list[str],
    video_asset_ids: list[str],
    audio_asset_ids: list[str],
    resolution: str | None,
    ratio: str | None,
    duration_seconds: int | None,
    audio_enabled: bool,
    mentioned_ids: list[str],
) -> ValidatedInput:
    rules = _rules(session, mode.id)
    by_type = _input_rule_map(rules)
    requested = {"text": [prompt] if prompt else [], "image": image_asset_ids, "video": video_asset_ids, "audio": audio_asset_ids}
    all_ids = image_asset_ids + video_asset_ids + audio_asset_ids
    assets: dict[str, Asset] = {}
    if all_ids:
        if not project_id:
            raise ApiError("MODEL_ASSET_PROJECT_REQUIRED", "Assets require a project", 422)
        rows = list(session.scalars(select(Asset).where(Asset.user_id == user_id, Asset.project_id == project_id, Asset.id.in_(all_ids))))
        assets = {row.id: row for row in rows}
        if len(assets) != len(all_ids):
            raise ApiError("MODEL_ASSET_INVALID", "Asset does not belong to this project", 422)
    asset_groups: dict[str, list[Asset]] = {"image": [], "video": [], "audio": []}
    for input_type, values in requested.items():
        rule = by_type.get(input_type)
        if values and (rule is None or not rule.is_supported):
            raise ApiError("MODEL_INPUT_UNSUPPORTED", f"{input_type} input is not supported", 422)
        if rule and rule.is_required and not values:
            raise ApiError("MODEL_INPUT_REQUIRED", f"{input_type} input is required", 422)
        if input_type == "text":
            if prompt and rule and rule.max_text_units is not None and _text_units(prompt) > rule.max_text_units:
                raise ApiError("MODEL_PROMPT_TOO_LONG", "Prompt exceeds this play mode limit", 422)
            continue
        if rule and rule.max_count is not None and len(values) > rule.max_count:
            raise ApiError("MODEL_INPUT_LIMIT_EXCEEDED", f"Too many {input_type} inputs", 422)
        for asset_id in values:
            asset = assets.get(asset_id)
            if asset is None or asset.asset_type != input_type or asset.status != "ready":
                raise ApiError("MODEL_ASSET_INVALID", f"{input_type} asset is not ready", 422)
            if rule and rule.max_file_size_bytes is not None and asset.size_bytes > rule.max_file_size_bytes:
                raise ApiError("MODEL_ASSET_TOO_LARGE", f"{input_type} asset exceeds size limit", 422)
            if rule and rule.max_duration_seconds is not None and (asset.duration_seconds is None or asset.duration_seconds > rule.max_duration_seconds):
                raise ApiError("MODEL_ASSET_DURATION_INVALID", f"{input_type} asset exceeds duration limit", 422)
            asset_groups[input_type].append(asset)
    mentioned = set(mentioned_ids)
    if mentioned:
        if not mentioned <= set(all_ids):
            raise ApiError("MODEL_MENTION_INVALID", "Mentioned assets must be uploaded for this task", 422)
        if not any(rule.supports_mention for rule in by_type.values()):
            raise ApiError("MODEL_MENTION_UNSUPPORTED", "This play mode does not support @ references", 422)
    if audio_enabled and (model.model_type != "video" or not mode.supports_generate_audio):
        raise ApiError("MODEL_AUDIO_GENERATION_UNSUPPORTED", "Audio generation is not supported", 422)
    chosen_resolution = _select_output_option(rules, "resolution", resolution)
    chosen_ratio = _select_output_option(rules, "ratio", ratio)
    chosen_duration = _select_output_option(rules, "duration", duration_seconds)
    return ValidatedInput(prompt=prompt, assets=asset_groups, mentioned_ids=mentioned, resolution=chosen_resolution if isinstance(chosen_resolution, str) else None, ratio=chosen_ratio if isinstance(chosen_ratio, str) else None, duration_seconds=chosen_duration if isinstance(chosen_duration, int) else None, audio_enabled=audio_enabled)


def _locked_prices(session: Session, provider: ModelPlayModeProvider, resolution: str | None) -> list[ModelPlayModeProviderPrice]:
    resolution_key = _output_option_key(resolution) if resolution else None
    rows = list(
        session.scalars(
            select(ModelPlayModeProviderPrice).where(
                ModelPlayModeProviderPrice.provider_id == provider.id,
                ModelPlayModeProviderPrice.is_enabled.is_(True),
                (func.lower(func.trim(ModelPlayModeProviderPrice.resolution)) == resolution_key)
                | (ModelPlayModeProviderPrice.resolution.is_(None)),
            )
        )
    )
    chosen: dict[str, ModelPlayModeProviderPrice] = {}
    for row in rows:
        old = chosen.get(row.billing_unit)
        if old is None or (old.resolution is None and row.resolution is not None):
            chosen[row.billing_unit] = row
    if not chosen:
        raise ApiError("MODEL_PRICE_NOT_FOUND", "No active price matches this provider and resolution", 409)
    return list(chosen.values())


def _create_charge_rows(session: Session, task: ModelTask, prices: list[ModelPlayModeProviderPrice]) -> None:
    for price in prices:
        session.add(ModelTaskCharge(
            id=_id("mtc"), task_id=task.id, billing_unit=price.billing_unit,
            resolution=task.resolution, quantity=Decimal("0"), credits=0,
            per_million_input_credits=price.per_million_input_credits,
            per_million_output_credits=price.per_million_output_credits,
            per_usage_credits=price.per_usage_credits,
            per_second_credits=price.per_second_credits,
        ))


def _round_credits(value: Decimal) -> int:
    """积分不可拆分，所有按量规则按各自计费维度向上取整。"""

    return int(value.to_integral_value(rounding=ROUND_CEILING))


def _estimated_credits(prices: list[ModelPlayModeProviderPrice], duration_seconds: int | None) -> int:
    """在提交前计算可确定的积分；Token 实际量仍在供应商回执后结算。"""

    total = 0
    for price in prices:
        if price.billing_unit == "usage":
            total += price.per_usage_credits or 0
        elif price.billing_unit == "second" and duration_seconds is not None and duration_seconds > 0:
            total += _round_credits(Decimal(duration_seconds) * Decimal(price.per_second_credits or 0))
    return total


def _precharge(session: Session, task: ModelTask) -> None:
    account = _locked_account(session, task.user_id)
    if account.balance < 0:
        raise ApiError("CREDITS_DEBT_OUTSTANDING", "Outstanding credit debt must be settled before submitting another task", 409)
    if task.default_credits_charged:
        _apply_credit(session, user_id=task.user_id, entry_type="charge", amount=-task.default_credits_charged, idempotency_key=f"model-task:precharge:{task.id}:{task.attempt_count}", reference_id=task.id, reason="model_task_default_precharge", allow_negative=True)


def _refund(session: Session, task: ModelTask, *, reason: str) -> None:
    if task.default_credits_charged:
        _apply_credit(session, user_id=task.user_id, entry_type="refund", amount=task.default_credits_charged, idempotency_key=f"model-task:refund:{task.id}:{task.attempt_count}", reference_id=task.id, reason=reason)
    task.settlement_status = "refunded"


def _task_assets_payload(session: Session, task: ModelTask) -> dict[str, list[dict[str, object]]]:
    rows = list(session.execute(select(ModelTaskAsset, Asset).join(Asset, Asset.id == ModelTaskAsset.asset_id).where(ModelTaskAsset.task_id == task.id).order_by(ModelTaskAsset.sort_order)).all())
    output: dict[str, list[dict[str, object]]] = {"image": [], "video": [], "audio": []}
    for link, asset in rows:
        role = link.provider_role or (f"reference_{link.input_type}" if link.input_type in output else None)
        output[link.input_type].append({
            "asset_id": asset.id,
            "url": asset.cdn_url,
            "filename": asset.filename,
            "mentioned": link.is_mentioned,
            "role": role,
        })
    return output


def _task_outputs(session: Session, task_id: str) -> list[OutputData]:
    rows = list(session.scalars(select(ModelTaskOutput).where(ModelTaskOutput.task_id == task_id).order_by(ModelTaskOutput.sort_order)))
    return [OutputData(type=row.output_type, cdn_url=row.cdn_url, text=row.text_content, duration_seconds=row.duration_seconds) for row in rows]


def _task_data(session: Session, task: ModelTask) -> TaskData:
    outputs = _task_outputs(session, task.id)
    output = next(({"url": item.cdn_url, "text": item.text} for item in outputs if item.cdn_url or item.text), None)
    model = session.get(Model, task.model_id)
    return TaskData(id=task.id, project_id=task.project_id, model_id=task.model_id, model_name=model.display_name if model else task.model_id, play_mode_id=task.play_mode_id, type=task.task_type, status=task.status, provider_task_id=task.provider_task_id, credits=task.default_credits_charged, final_credits=task.final_credits, input_token=task.input_token, output_token=task.output_token, outputs=outputs, input={"prompt": task.prompt or "", "provider_options": task.provider_options}, output=output, error_code=task.error_code, error_message=task.error_message, created_at=task.created_at.isoformat(), updated_at=task.updated_at.isoformat())


def _owned_project(session: Session, user_id: str, project_id: str, *, lock: bool = False) -> Project:
    statement = select(Project).where(Project.id == project_id, Project.user_id == user_id, Project.product == PRODUCT)
    if lock:
        statement = statement.with_for_update()
    project = session.scalar(statement)
    if project is None:
        raise ApiError("AI_VIDEO_DRAFT_NOT_FOUND", "AI video draft not found", 404)
    return project


def _provider_payload(task: ModelTask, assets: dict[str, list[dict[str, object]]]) -> dict[str, object]:
    return {"model_task_id": task.id, "model_id": task.model_id, "play_mode_id": task.play_mode_id, "provider_id": task.provider_id, "provider_options": task.provider_options, "asset_ids": {kind: [item["asset_id"] for item in items] for kind, items in assets.items()}}


def _submit_task(registry: ProviderRegistry, session: Session, task: ModelTask, *, messages: list[dict[str, object]] | None = None) -> ProviderResult:
    model = session.get(Model, task.model_id)
    mode = session.get(ModelPlayMode, task.play_mode_id)
    provider = session.get(ModelPlayModeProvider, task.provider_id)
    if model is None or mode is None or provider is None:
        raise ProviderError("model provider configuration is unavailable")
    assets = _task_assets_payload(session, task)
    # LLM 任务在 Worker 接管或恢复时同样必须携带已冻结的多模态素材。
    # 不能退化成只有 prompt 的第二次请求，否则模型会误判图片未上传。
    if messages is None and model.model_type == "llm":
        frozen_context = (
            task.provider_request.get("chat_context_messages")
            if isinstance(task.provider_request, dict)
            else None
        )
        if isinstance(frozen_context, list) and frozen_context and all(
            isinstance(message, dict) for message in frozen_context
        ):
            messages = frozen_context
        else:
            content: list[dict[str, object]] = []
            if task.prompt:
                content.append({"type": "text", "text": task.prompt})
            for kind, tag in (
                ("image", "image_url"),
                ("video", "video_url"),
                ("audio", "audio_url"),
            ):
                for asset in assets[kind]:
                    content.append({"type": tag, tag: {"url": asset["url"]}})
            messages = [{"role": "user", "content": content or ""}]
    return registry.get(provider.provider_code).submit(model=model, play_mode=mode, provider=provider, task_id=task.id, prompt=task.prompt, assets=assets, resolution=task.resolution, ratio=task.ratio, duration_seconds=task.requested_duration_seconds, audio_enabled=task.audio_enabled, options=task.provider_options, messages=messages)


def _stage_provider_result(session: Session, task: ModelTask, result: ProviderResult) -> None:
    task.provider_response = result.raw
    task.error_code = result.error_code
    task.error_message = result.error_message
    task.input_token = result.input_token
    task.output_token = result.output_token
    task.actual_output_image_count = result.generated_images
    task.actual_output_duration_seconds = result.output_duration_seconds
    if result.provider_task_id:
        task.provider_task_id = result.provider_task_id
    if result.status in {"queued", "processing"}:
        task.status = result.status
        task.next_poll_at = utc_now()
        return
    if result.status == "failed":
        _fail_task(session, task, code=result.error_code or "MODEL_PROVIDER_FAILED", message=result.error_message or "Model provider reported failure")
        return
    if result.status != "succeeded":
        raise ProviderError("provider result status is invalid")
    for index, output in enumerate(result.outputs):
        if session.scalar(select(ModelTaskOutput).where(ModelTaskOutput.task_id == task.id, ModelTaskOutput.sort_order == index)) is None:
            session.add(ModelTaskOutput(id=_id("mto"), task_id=task.id, output_type=output.output_type, provider_url=output.url, text_content=output.text, content_type=output.content_type, duration_seconds=output.duration_seconds, sort_order=index))
    task.status = "finalizing"
    task.next_poll_at = utc_now()


def _fail_task(session: Session, task: ModelTask, *, code: str, message: str, refund: bool = True) -> None:
    task.status = "failed"
    task.error_code = code
    task.error_message = message
    task.next_poll_at = None
    task.poll_lease_token = None
    task.poll_lease_until = None
    if refund and task.settlement_status not in {"refunded", "settled"}:
        _refund(session, task, reason="model_task_failed_refund")
    project = session.get(Project, task.project_id) if task.project_id else None
    if project is not None and task.task_type in AI_VIDEO_MODEL_TYPES:
        project.status = "failed"


def _settle(session: Session, task: ModelTask) -> None:
    charges = list(session.scalars(select(ModelTaskCharge).where(ModelTaskCharge.task_id == task.id)))
    total = 0
    for charge in charges:
        if charge.billing_unit == "usage":
            quantity = Decimal(task.actual_output_image_count or 1) if task.task_type == "image" else Decimal("1")
            credits = int(quantity) * (charge.per_usage_credits or 0)
        elif charge.billing_unit == "second":
            if task.actual_output_duration_seconds is None:
                raise ApiError("MODEL_USAGE_MISSING", "Actual output duration is unavailable", 503)
            quantity = Decimal(str(task.actual_output_duration_seconds))
            credits = _round_credits(quantity * Decimal(charge.per_second_credits or 0))
        elif charge.billing_unit == "token":
            if task.input_token is None and task.output_token is None:
                raise ApiError("MODEL_USAGE_MISSING", "Actual token usage is unavailable", 503)
            input_quantity = Decimal(task.input_token or 0) / Decimal("1000000")
            output_quantity = Decimal(task.output_token or 0) / Decimal("1000000")
            quantity = input_quantity + output_quantity
            credits = (
                _round_credits(input_quantity * Decimal(charge.per_million_input_credits or 0))
                + _round_credits(output_quantity * Decimal(charge.per_million_output_credits or 0))
            )
        else:
            raise ApiError("MODEL_PRICE_INVALID", "Task price configuration is invalid", 503)
        charge.quantity = quantity
        charge.credits = credits
        total += credits
    difference = total - task.default_credits_charged
    if difference > 0:
        _apply_credit(session, user_id=task.user_id, entry_type="charge", amount=-difference, idempotency_key=f"model-task:settlement-charge:{task.id}:{task.attempt_count}", reference_id=task.id, reason="model_task_settlement_charge", allow_negative=True)
    elif difference < 0:
        _apply_credit(session, user_id=task.user_id, entry_type="refund", amount=-difference, idempotency_key=f"model-task:settlement-refund:{task.id}:{task.attempt_count}", reference_id=task.id, reason="model_task_settlement_refund")
    task.final_credits = total
    task.settlement_status = "settled"


def _mark_completed(session: Session, task: ModelTask, *, partial: bool = False) -> None:
    try:
        _settle(session, task)
    except ApiError as exc:
        _fail_task(session, task, code=exc.code, message=exc.message, refund=True)
        task.settlement_status = "billing_failed"
        return
    task.status = "succeeded_with_partial_output" if partial else "succeeded"
    # 曾经的轮询重试错误仅表示中间态；成功落库后不能继续暴露为任务错误。
    task.error_code = None
    task.error_message = None
    task.next_poll_at = None
    task.poll_lease_token = None
    task.poll_lease_until = None
    project = session.get(Project, task.project_id) if task.project_id else None
    if project is not None and task.task_type in AI_VIDEO_MODEL_TYPES:
        project.status = "completed"


@router.get("/products/ai-video/models", response_model=ApiResponse[ModelsData])
def list_models(request: Request, token: Annotated[str, Depends(bearer_token)], auth: Annotated[AuthService, Depends(get_auth_service)], request_id: Annotated[str, Depends(get_request_id)]):
    auth.resolve_user(token)
    with Session(request.app.state.database_engine) as session:
        rows = list(session.scalars(select(Model).where(Model.is_enabled.is_(True), Model.model_type.in_(AI_VIDEO_MODEL_TYPES)).order_by(Model.sort_order.desc(), Model.display_name)))
        items = [_model_summary(session, row) for row in rows]
    default = next((row.id for row in rows if row.is_default), rows[0].id if rows else None)
    return ApiResponse(code="AI_VIDEO_MODELS_RETRIEVED", message="AI video models retrieved", request_id=request_id, data=ModelsData(items=items, default_model_id=default))


@router.get("/products/ai-video/models/{model_id}/gen-params", response_model=ApiResponse[ModelGenParamData])
def model_gen_params(model_id: str, request: Request, token: Annotated[str, Depends(bearer_token)], auth: Annotated[AuthService, Depends(get_auth_service)], request_id: Annotated[str, Depends(get_request_id)]):
    """按模型 ID 获取玩法规则、输入能力、输出参数和展示计费信息。"""
    auth.resolve_user(token)
    with Session(request.app.state.database_engine) as session:
        model = session.scalar(select(Model).where(Model.id == model_id, Model.is_enabled.is_(True), Model.model_type.in_(AI_VIDEO_MODEL_TYPES)))
        if model is None:
            raise ApiError("AI_VIDEO_MODEL_NOT_FOUND", "AI video model not found", 404)
        data = _model_gen_params(session, model)
    return ApiResponse(code="AI_VIDEO_MODEL_GEN_PARAMS_RETRIEVED", message="AI video model generation parameters retrieved", request_id=request_id, data=data)


@router.post("/products/ai-video/drafts", status_code=status.HTTP_201_CREATED, response_model=ApiResponse[DraftData])
def create_draft(request: Request, token: Annotated[str, Depends(bearer_token)], auth: Annotated[AuthService, Depends(get_auth_service)], request_id: Annotated[str, Depends(get_request_id)]):
    user = auth.resolve_user(token)
    project_id = _id("prj")
    with Session(request.app.state.database_engine) as session:
        with session.begin():
            session.add(Project(id=project_id, user_id=user.id, product=PRODUCT, status="draft", current_stage="created"))
    return ApiResponse(code="AI_VIDEO_DRAFT_CREATED", message="AI video draft created", request_id=request_id, data=DraftData(project_id=project_id))


@router.post("/products/ai-video/quote", response_model=ApiResponse[QuoteData])
def quote(body: QuoteRequest, request: Request, token: Annotated[str, Depends(bearer_token)], auth: Annotated[AuthService, Depends(get_auth_service)], request_id: Annotated[str, Depends(get_request_id)]):
    auth.resolve_user(token)
    with Session(request.app.state.database_engine) as session:
        model = session.scalar(select(Model).where(Model.id == body.model_id, Model.is_enabled.is_(True), Model.model_type.in_(AI_VIDEO_MODEL_TYPES)))
        if model is None:
            raise ApiError("AI_VIDEO_MODEL_NOT_FOUND", "AI video model not found", 404)
        mode = _selected_mode(session, model, body.play_mode_id)
        provider = _active_provider(session, mode)
        prices = _locked_prices(session, provider, body.resolution)
        data = QuoteData(
            model_id=model.id,
            play_mode_id=mode.id,
            credits=max(mode.default_credits, _estimated_credits(prices, body.duration_seconds)),
            billing_units=[row.billing_unit for row in prices],
        )
    return ApiResponse(code="AI_VIDEO_QUOTE_RETRIEVED", message="AI video quote retrieved", request_id=request_id, data=data)


def _reference_alias(input_type: str, order: int) -> tuple[str, str]:
    english = {"image": "image", "video": "video", "audio": "audio"}[input_type]
    chinese = {"image": "图", "video": "视频", "audio": "音频"}[input_type]
    return f"@{english}{order + 1}", f"{chinese}{order + 1}"


def _inferred_reference_description(*, input_type: str, source_prompt: str, marker: str) -> str:
    """Use the local prompt context first, then a safe Seedance reference default.

    The mapping editor is intentionally not exposed to users.  The compiled
    prompt still has to state what each ordered material represents, as
    required by Seedance 2.5's multi-material prompt guidance.
    """

    position = source_prompt.find(marker)
    context = source_prompt[max(0, position - 80):position + len(marker) + 80] if position >= 0 else source_prompt
    if input_type == "image":
        if any(word in context for word in ("风格", "光影", "滤镜", "色彩")):
            return "作为画面风格、光影与色彩参考。"
        if any(word in context for word in ("场景", "背景", "地点", "环境")):
            return "作为场景、环境与构图参考。"
        return "作为主体外观、角色一致性或场景风格参考，以创作指令为准。"
    if input_type == "video":
        if any(word in context for word in ("运镜", "镜头", "机位", "跟拍", "环绕")):
            return "作为镜头运动、机位与运镜节奏参考。"
        if any(word in context for word in ("动作", "表情", "姿势", "运动")):
            return "作为主体动作、表情与动态节奏参考。"
        return "作为动作、镜头运动、动态信息或剧情节奏参考，以创作指令为准。"
    if any(word in context for word in ("音乐", "BGM", "bgm", "旋律", "配乐")):
        return "作为音乐、旋律与声音氛围参考。"
    if any(word in context for word in ("台词", "说话", "口音", "配音", "音色")):
        return "作为人物音色、台词或说话风格参考。"
    return "作为人物音色、台词、音乐或环境声音参考，以创作指令为准。"


def _compile_reference_prompt(
    *,
    prompt: str | None,
    assets: dict[str, list[Asset]],
    rules: dict[str, ModelPlayModeRule],
    mappings: list[ReferenceMappingData],
    legacy_mentioned_ids: list[str],
) -> tuple[str | None, set[str]]:
    """Compile Seedance's ordered material mapping into the immutable task prompt.

    No subject/usage JSON is persisted.  The user supplied mapping is baked into
    ``model_tasks.prompt`` and the stable task asset order is persisted separately.
    ``{{asset:<id>}}`` markers are an editor transport format, never sent upstream.
    """

    aliases: dict[str, tuple[str, str, str]] = {}
    for input_type in ("image", "video", "audio"):
        for order, asset in enumerate(assets[input_type]):
            alias, display = _reference_alias(input_type, order)
            aliases[asset.id] = (alias, display, input_type)

    mapping_by_id = {item.asset_id: item.description for item in mappings}
    if set(mapping_by_id) - set(aliases):
        raise ApiError("MODEL_REFERENCE_MAPPING_INVALID", "Reference mapping asset is not submitted", 422)

    # New clients intentionally submit no manual mapping data.  Generate an
    # ordered material section from the media type and local prompt context.
    for asset_id, (_alias, _display, input_type) in aliases.items():
        rule = rules.get(input_type)
        if rule is not None and rule.supports_mention:
            mapping_by_id.setdefault(
                asset_id,
                _inferred_reference_description(
                    input_type=input_type,
                    source_prompt=prompt or "",
                    marker=f"{{{{asset:{asset_id}}}}}",
                ),
            )

    mentioned = set(legacy_mentioned_ids)
    source = prompt or ""
    marker_ids = set(_ASSET_MARKER.findall(source))
    if not marker_ids <= set(aliases):
        raise ApiError("MODEL_MENTION_INVALID", "Prompt mentions an asset that is not submitted", 422)
    mentioned.update(marker_ids)
    mentioned.update(mapping_by_id)

    for asset_id in mentioned:
        input_type = aliases.get(asset_id, ("", "", ""))[2]
        rule = rules.get(input_type)
        if rule is None or not rule.supports_mention:
            raise ApiError("MODEL_MENTION_UNSUPPORTED", f"{input_type or 'asset'} references are not supported by this play mode", 422)

    def replace_marker(match: re.Match[str]) -> str:
        return aliases[match.group(1)][0]

    creative_prompt = _ASSET_MARKER.sub(replace_marker, source).strip()
    if not mapping_by_id:
        return creative_prompt or None, mentioned

    lines = ["【参考素材映射】"]
    for input_type in ("image", "video", "audio"):
        for asset in assets[input_type]:
            if asset.id not in mapping_by_id:
                continue
            alias, display, _ = aliases[asset.id]
            lines.append(f"{alias}（{display}）：{mapping_by_id[asset.id]}")
    if creative_prompt:
        lines.extend(("", "【创作指令】", creative_prompt))
    return "\n".join(lines), mentioned


def _create_model_task(
    *,
    session: Session,
    user_id: str,
    project_id: str | None,
    body: TaskCreateRequest | LlmCompletionRequest,
    task_type: str,
) -> ModelTask:
    if project_id:
        project = _owned_project(session, user_id, project_id, lock=True)
        reusable_statuses = {"draft", "ready", "failed"}
        # 聊天图片复用 ai_video 项目作为素材容器。旧版本曾在 LLM 完成后错误地
        # 将该项目标记为 completed，重试时也必须允许继续复用原始图片。
        if task_type == "llm":
            reusable_statuses.add("completed")
        if project.status not in reusable_statuses:
            raise ApiError("AI_VIDEO_DRAFT_LOCKED", "AI video draft cannot accept a new task", 409)
    model_statement = select(Model).where(Model.id == body.model_id, Model.is_enabled.is_(True))
    if task_type == "ai_video":
        model_statement = model_statement.where(Model.model_type.in_(AI_VIDEO_MODEL_TYPES))
    else:
        model_statement = model_statement.where(Model.model_type == task_type)
    model = session.scalar(model_statement)
    if model is None:
        raise ApiError("MODEL_NOT_FOUND", "Model is not available", 404)
    mode = _selected_mode(session, model, body.play_mode_id)
    provider = _active_provider(session, mode)
    validated = _validate_input(session=session, user_id=user_id, project_id=project_id, model=model, mode=mode, prompt=body.prompt, image_asset_ids=body.image_asset_ids, video_asset_ids=body.video_asset_ids, audio_asset_ids=body.audio_asset_ids, resolution=getattr(body, "resolution", None), ratio=getattr(body, "ratio", None), duration_seconds=getattr(body, "duration_seconds", None), audio_enabled=getattr(body, "audio_enabled", False), mentioned_ids=getattr(body, "multi_subject_references", []))
    compiled_prompt, mentioned_ids = _compile_reference_prompt(
        prompt=validated.prompt,
        assets=validated.assets,
        rules=_input_rule_map(_rules(session, mode.id)),
        mappings=getattr(body, "reference_mappings", []),
        legacy_mentioned_ids=getattr(body, "multi_subject_references", []),
    )
    validated = ValidatedInput(prompt=compiled_prompt, assets=validated.assets, mentioned_ids=mentioned_ids, resolution=validated.resolution, ratio=validated.ratio, duration_seconds=validated.duration_seconds, audio_enabled=validated.audio_enabled)
    prices = _locked_prices(session, provider, validated.resolution)
    precharge_credits = max(mode.default_credits, _estimated_credits(prices, validated.duration_seconds))
    task = ModelTask(id=_id("mt"), project_id=project_id, user_id=user_id, model_id=model.id, play_mode_id=mode.id, provider_id=provider.id, task_type=model.model_type, status="submitting", idempotency_key="", prompt=validated.prompt, resolution=validated.resolution, ratio=validated.ratio, requested_duration_seconds=validated.duration_seconds, audio_enabled=validated.audio_enabled, provider_options=getattr(body, "provider_options", {}), default_credits_charged=precharge_credits, settlement_status="pending")
    session.add(task)
    for kind, assets in validated.assets.items():
        for order, asset in enumerate(assets):
            session.add(ModelTaskAsset(
                id=_id("mta"), task_id=task.id, asset_id=asset.id,
                input_type=kind, provider_role=f"reference_{kind}",
                is_mentioned=asset.id in validated.mentioned_ids, sort_order=order,
            ))
    _create_charge_rows(session, task, prices)
    _precharge(session, task)
    if project_id and model.model_type in AI_VIDEO_MODEL_TYPES:
        project.status = "queued"
        project.current_stage = "generate"
    return task


@router.post("/products/ai-video/tasks", status_code=status.HTTP_202_ACCEPTED, response_model=ApiResponse[TaskData])
def create_task(body: TaskCreateRequest, request: Request, token: Annotated[str, Depends(bearer_token)], auth: Annotated[AuthService, Depends(get_auth_service)], request_id: Annotated[str, Depends(get_request_id)], idempotency_key: Annotated[str | None, Header(alias="X-Idempotency-Key")] = None, registry: Annotated[ProviderRegistry, Depends(get_provider_registry)] = None):
    user = auth.resolve_user(token)
    key = idempotency_key or f"request:{request_id}"
    if len(key) > 256:
        raise ApiError("IDEMPOTENCY_KEY_INVALID", "Idempotency key is invalid", 422)
    with Session(request.app.state.database_engine) as session:
        with session.begin():
            existing = session.scalar(select(ModelTask).where(ModelTask.user_id == user.id, ModelTask.idempotency_key == key).with_for_update())
            if existing is not None:
                return ApiResponse(code="AI_VIDEO_TASK_RETRIEVED", message="AI video task retrieved", request_id=request_id, data=_task_data(session, existing))
            task = _create_model_task(session=session, user_id=user.id, project_id=body.project_id, body=body, task_type="ai_video")
            # The selected model determines whether this is image or video; reload avoids accepting a mismatched helper type.
            model = session.get(Model, task.model_id)
            assert model is not None
            if model.model_type not in AI_VIDEO_MODEL_TYPES:
                raise ApiError("AI_VIDEO_MODEL_NOT_FOUND", "AI video model not found", 404)
            task.task_type = model.model_type
            task.idempotency_key = key
            task_id = task.id
        try:
            with Session(request.app.state.database_engine) as submit_session:
                submitted = submit_session.get(ModelTask, task_id)
                assert submitted is not None
                result = _submit_task(registry, submit_session, submitted)
            with Session(request.app.state.database_engine) as persist_session:
                with persist_session.begin():
                    persisted = persist_session.get(ModelTask, task_id)
                    assert persisted is not None
                    persisted.provider_request = _provider_payload(persisted, _task_assets_payload(persist_session, persisted))
                    persisted.submitted_at = utc_now()
                    _stage_provider_result(persist_session, persisted, result)
                    data = _task_data(persist_session, persisted)
        except ProviderError as exc:
            with Session(request.app.state.database_engine) as fail_session:
                with fail_session.begin():
                    persisted = fail_session.get(ModelTask, task_id)
                    if persisted is not None:
                        _fail_task(fail_session, persisted, code="MODEL_PROVIDER_UNAVAILABLE", message="Model provider submission failed")
            raise ApiError("MODEL_PROVIDER_UNAVAILABLE", "Model provider submission failed", 503) from exc
    return ApiResponse(code="AI_VIDEO_TASK_SUBMITTED", message="AI video task submitted", request_id=request_id, data=data)


@router.post("/products/llm/chat/completions", status_code=status.HTTP_202_ACCEPTED, response_model=ApiResponse[TaskData])
def create_llm_completion(body: LlmCompletionRequest, request: Request, token: Annotated[str, Depends(bearer_token)], auth: Annotated[AuthService, Depends(get_auth_service)], request_id: Annotated[str, Depends(get_request_id)], idempotency_key: Annotated[str | None, Header(alias="X-Idempotency-Key")] = None, registry: Annotated[ProviderRegistry, Depends(get_provider_registry)] = None):
    user = auth.resolve_user(token)
    key = idempotency_key or f"request:{request_id}"
    with Session(request.app.state.database_engine) as session:
        with session.begin():
            if session.scalar(select(ModelTask).where(ModelTask.user_id == user.id, ModelTask.idempotency_key == key)):
                existing = session.scalar(select(ModelTask).where(ModelTask.user_id == user.id, ModelTask.idempotency_key == key))
                assert existing is not None
                return ApiResponse(code="LLM_TASK_RETRIEVED", message="LLM task retrieved", request_id=request_id, data=_task_data(session, existing))
            task = _create_model_task(session=session, user_id=user.id, project_id=body.project_id, body=body, task_type="llm")
            task.idempotency_key = key
            task_id = task.id
        try:
            with Session(request.app.state.database_engine) as submit_session:
                submitted = submit_session.get(ModelTask, task_id)
                assert submitted is not None
                assets = _task_assets_payload(submit_session, submitted)
                content: list[dict[str, object]] = []
                if submitted.prompt:
                    content.append({"type": "text", "text": submitted.prompt})
                for kind, tag in (("image", "image_url"), ("video", "video_url"), ("audio", "audio_url")):
                    for asset in assets[kind]:
                        content.append({"type": tag, tag: {"url": asset["url"]}})
                messages = [{"role": "user", "content": content or ""}]
                result = _submit_task(registry, submit_session, submitted, messages=messages)
            with Session(request.app.state.database_engine) as persist_session:
                with persist_session.begin():
                    persisted = persist_session.get(ModelTask, task_id)
                    assert persisted is not None
                    persisted.provider_request = _provider_payload(persisted, _task_assets_payload(persist_session, persisted))
                    persisted.submitted_at = utc_now()
                    _stage_provider_result(persist_session, persisted, result)
                    data = _task_data(persist_session, persisted)
        except ProviderError as exc:
            with Session(request.app.state.database_engine) as fail_session:
                with fail_session.begin():
                    persisted = fail_session.get(ModelTask, task_id)
                    if persisted is not None:
                        _fail_task(fail_session, persisted, code="MODEL_PROVIDER_UNAVAILABLE", message="Model provider submission failed")
            raise ApiError("MODEL_PROVIDER_UNAVAILABLE", "Model provider submission failed", 503) from exc
    return ApiResponse(code="LLM_TASK_SUBMITTED", message="LLM task submitted", request_id=request_id, data=data)


@router.post("/products/ai-video/tasks/{task_id}/retry", response_model=ApiResponse[TaskData])
def retry_task(task_id: str, request: Request, token: Annotated[str, Depends(bearer_token)], auth: Annotated[AuthService, Depends(get_auth_service)], request_id: Annotated[str, Depends(get_request_id)], registry: Annotated[ProviderRegistry, Depends(get_provider_registry)] = None):
    """失败任务以当前生效价格作为一次新的提交重新发起。"""
    user = auth.resolve_user(token)
    with Session(request.app.state.database_engine) as session:
        with session.begin():
            task = session.scalar(select(ModelTask).where(ModelTask.id == task_id, ModelTask.user_id == user.id).with_for_update())
            if task is None:
                raise ApiError("AI_VIDEO_TASK_NOT_FOUND", "AI video task not found", 404)
            if task.status != "failed":
                raise ApiError("AI_VIDEO_TASK_NOT_RETRYABLE", "AI video task cannot be retried", 409)
            mode = session.get(ModelPlayMode, task.play_mode_id)
            if mode is None:
                raise ApiError("MODEL_PLAY_MODE_NOT_FOUND", "Model play mode is not available", 404)
            # Retrying is a new submission: lock the mode's currently effective
            # provider and its current price rows instead of reusing a disabled
            # historical provider from the failed attempt.
            provider = _active_provider(session, mode)
            task.provider_id = provider.id
            session.execute(delete(ModelTaskCharge).where(ModelTaskCharge.task_id == task.id))
            _create_charge_rows(session, task, _locked_prices(session, provider, task.resolution))
            session.execute(delete(ModelTaskOutput).where(ModelTaskOutput.task_id == task.id))
            task.attempt_count += 1
            task.status = "submitting"
            task.provider_task_id = None
            task.provider_request = None
            task.provider_response = None
            task.error_code = None
            task.error_message = None
            task.final_credits = None
            task.input_token = None
            task.output_token = None
            task.actual_output_duration_seconds = None
            task.actual_output_image_count = None
            task.settlement_status = "pending"
            _precharge(session, task)
        try:
            with Session(request.app.state.database_engine) as submit_session:
                current = submit_session.get(ModelTask, task_id)
                assert current is not None
                result = _submit_task(registry, submit_session, current)
            with Session(request.app.state.database_engine) as persist_session:
                with persist_session.begin():
                    current = persist_session.get(ModelTask, task_id)
                    assert current is not None
                    current.provider_request = _provider_payload(current, _task_assets_payload(persist_session, current))
                    current.submitted_at = utc_now()
                    _stage_provider_result(persist_session, current, result)
                    data = _task_data(persist_session, current)
        except ProviderError as exc:
            with Session(request.app.state.database_engine) as fail_session:
                with fail_session.begin():
                    current = fail_session.get(ModelTask, task_id)
                    if current is not None:
                        _fail_task(fail_session, current, code="MODEL_PROVIDER_UNAVAILABLE", message="Model provider submission failed")
            raise ApiError("MODEL_PROVIDER_UNAVAILABLE", "Model provider submission failed", 503) from exc
    return ApiResponse(code="AI_VIDEO_TASK_RETRIED", message="AI video task retried", request_id=request_id, data=data)


@router.get("/products/ai-video/tasks", response_model=ApiResponse[TasksData])
def list_tasks(request: Request, token: Annotated[str, Depends(bearer_token)], auth: Annotated[AuthService, Depends(get_auth_service)], request_id: Annotated[str, Depends(get_request_id)], created_from: datetime | None = Query(default=None), created_to: datetime | None = Query(default=None), type: Literal["image", "video"] | None = Query(default=None), view: Literal["list", "gallery"] = Query(default="list"), page: int = Query(default=1, ge=1), page_size: int = Query(default=30, ge=1, le=100)):
    user = auth.resolve_user(token)
    if created_from and created_to and created_from > created_to:
        raise ApiError("AI_VIDEO_TIME_RANGE_INVALID", "Created time range is invalid", 422)
    with Session(request.app.state.database_engine) as session:
        statement = select(ModelTask).where(ModelTask.user_id == user.id, ModelTask.task_type.in_(AI_VIDEO_MODEL_TYPES))
        if created_from:
            statement = statement.where(ModelTask.created_at >= created_from)
        if created_to:
            statement = statement.where(ModelTask.created_at < created_to)
        if type:
            statement = statement.where(ModelTask.task_type == type)
        total = session.scalar(select(func.count()).select_from(statement.subquery())) or 0
        rows = list(session.scalars(
            statement.order_by(ModelTask.created_at.desc(), ModelTask.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ))
        data = TasksData(
            items=[_task_data(session, row) for row in rows],
            view=view,
            total=total,
            page=page,
            page_size=page_size,
            has_next=page * page_size < total,
        )
    return ApiResponse(code="AI_VIDEO_TASKS_RETRIEVED", message="AI video tasks retrieved", request_id=request_id, data=data)
