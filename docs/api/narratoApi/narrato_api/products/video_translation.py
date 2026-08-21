"""独立视频翻译产品的持久化契约与 Business API。

它只共享 Project/Workflow/Asset/积分账本等通用基础设施，绝不读取短剧
解说设置或编辑器草稿。Core 通过标准 workflow outbox 消费节点快照。
"""

from __future__ import annotations

import hashlib
import math
import secrets
import time
from datetime import datetime, timezone
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, Request, status
from pydantic import Field, model_validator
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    UniqueConstraint,
    func,
    select,
)
from sqlalchemy.orm import Mapped, Session, mapped_column

from narrato_api.api.dependencies import get_request_id, get_settings
from narrato_api.api.errors import ApiError
from narrato_api.api.responses import ApiResponse, StrictModel
from narrato_api.artifacts.service import list_registered_artifacts
from narrato_api.assets.models import Asset
from narrato_api.auth.router import bearer_token, get_auth_service
from narrato_api.auth.service import AuthService
from narrato_api.billing.models import CreditLedger, ProductPrice
from narrato_api.billing.pricing import (
    VOICE_REPLACEMENT_SURCHARGE_CREDITS_PER_MINUTE as DEFAULT_VOICE_REPLACEMENT_SURCHARGE_CREDITS_PER_MINUTE,
    estimate_video_translation_cost,
)
from narrato_api.config import Settings
from narrato_api.billing.service import InsufficientCreditsError, _apply_credit
from narrato_api.database import Base
from narrato_api.integrations.core_client import (
    CoreClientError,
    CoreClientRejectedError,
    HttpCoreClient,
)
from narrato_api.projects.models import Project
from narrato_api.workflows.models import (
    Workflow,
    WorkflowNode,
    WorkflowNodeAttempt,
    WorkflowOutbox,
    WorkflowTemplateSnapshot,
)
from narrato_api.workflows.service import _new_id

PRODUCT = "video_translation"
PREVIEW_CREDITS = 12
VOICE_REPLACEMENT_SURCHARGE_CREDITS_PER_MINUTE = (
    DEFAULT_VOICE_REPLACEMENT_SURCHARGE_CREDITS_PER_MINUTE
)
TTS_TIMING_TOLERANCE_MS = 200
SUPPORTED_LANGUAGES = (
    "en",
    "ja",
    "ko",
    "de",
    "fr",
    "es",
    "pt",
    "ru",
    "vi",
    "th",
    "id",
    "ar",
)
RATIOS = ("original", "9:16", "16:9", "1:1", "4:3", "3:4")
ORIGINAL_SOUND_MODES = ("voice_replacement", "translated_voice_only")
NODES = (
    "subtitle_recognition",
    "subtitle_translation",
    "subtitle_rewrite",
    "tts",
    "video_render",
    "publish_artifacts",
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _id(prefix: str) -> str:
    return f"{prefix}_{time.time_ns():x}{secrets.token_hex(6)}"


def normalize_original_sound_mode(value: object) -> str:
    """把历史音频开关映射到唯一的成片音频双态合同。"""

    aliases = {
        "voice_replacement": "voice_replacement",
        "translated_voice_only": "translated_voice_only",
        # 旧 ``keep``/``preserve`` 的用户意图是保留环境声；新实现通过人声
        # 分离只保留非人声，而不是继续把完整原声与译音叠加。
        "keep": "voice_replacement",
        "preserve": "voice_replacement",
        "mute": "translated_voice_only",
    }
    # 未选择音频模式时默认只保留译文配音，基础价格与创建页的预估一致；
    # 显式的 keep/preserve 仍保持旧项目的“保留环境声”语义。
    return aliases.get(
        str(value or "translated_voice_only"), "translated_voice_only"
    )


class VideoTranslationSettings(Base):
    __tablename__ = "project_video_translation_settings"
    project_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("projects.id", ondelete="RESTRICT"), primary_key=True
    )
    settings: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class VideoTranslationSegment(Base):
    __tablename__ = "video_translation_segments"
    __table_args__ = (
        UniqueConstraint(
            "project_id", "segment_index", name="uq_translation_segment_index"
        ),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("projects.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    segment_index: Mapped[int] = mapped_column(Integer, nullable=False)
    start_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    end_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    source_text: Mapped[str] = mapped_column(String(4000), nullable=False)
    translated_text: Mapped[str] = mapped_column(String(4000), nullable=False)
    voice_id: Mapped[str] = mapped_column(String(128), nullable=False)
    voice_overridden: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    speed: Mapped[float] = mapped_column(nullable=False, default=1.0)
    volume: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    keep_original_sound: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    preview_audio_url: Mapped[str | None] = mapped_column(String(2048))
    preview_digest: Mapped[str | None] = mapped_column(String(64))
    # Core TTS 回写的实际结果，不能用字数或供应商预估冒充。编辑译文、音色或
    # 语速后这些字段会失效，直到下一次整段配音成功。
    tts_duration_ms: Mapped[int | None] = mapped_column(Integer)
    timing_fit_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending"
    )
    timing_overflow_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    fitted_speed: Mapped[float | None] = mapped_column()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class VideoTranslationPreviewCharge(Base):
    __tablename__ = "video_translation_preview_charges"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "segment_id",
            "idempotency_key",
            name="uq_translation_preview_charge",
        ),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False
    )
    segment_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("video_translation_segments.id", ondelete="RESTRICT"),
        nullable=False,
    )
    idempotency_key: Mapped[str] = mapped_column(String(256), nullable=False)
    core_task_id: Mapped[str | None] = mapped_column(String(128), unique=True)
    credits: Mapped[int] = mapped_column(
        Integer, nullable=False, default=PREVIEW_CREDITS
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class VideoTranslationCharge(Base):
    """视频翻译启动时冻结的报价及收费明细。

    账本只写一笔项目总扣费，便于既有项目列表统计和失败退款复用同一幂等
    边界；该表保留总源时长、价格版本和音频模式，保证重新读取价格或配置
    后不会改变已经发起任务的收费事实。
    """

    __tablename__ = "video_translation_charges"
    __table_args__ = (
        CheckConstraint(
            "total_source_seconds > 0",
            name="ck_translation_charge_source_seconds_positive",
        ),
        CheckConstraint(
            "billed_minutes > 0", name="ck_translation_charge_minutes_positive"
        ),
        CheckConstraint(
            "base_credits_per_minute > 0",
            name="ck_translation_charge_base_rate_positive",
        ),
        CheckConstraint(
            "voice_replacement_credits_per_minute >= 0",
            name="ck_translation_charge_surcharge_rate_nonnegative",
        ),
        CheckConstraint(
            "base_credits >= 0", name="ck_translation_charge_base_nonnegative"
        ),
        CheckConstraint(
            "voice_replacement_credits >= 0",
            name="ck_translation_charge_surcharge_nonnegative",
        ),
        CheckConstraint(
            "total_credits = base_credits + voice_replacement_credits",
            name="ck_translation_charge_total_matches_breakdown",
        ),
        CheckConstraint(
            "original_sound_mode IN ('voice_replacement', 'translated_voice_only')",
            name="ck_translation_charge_audio_mode",
        ),
    )

    project_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("projects.id", ondelete="RESTRICT"), primary_key=True
    )
    workflow_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("workflows.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
    )
    price_version: Mapped[int] = mapped_column(Integer, nullable=False)
    total_source_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    billed_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    base_credits_per_minute: Mapped[int] = mapped_column(Integer, nullable=False)
    original_sound_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    voice_replacement_credits_per_minute: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    base_credits: Mapped[int] = mapped_column(Integer, nullable=False)
    voice_replacement_credits: Mapped[int] = mapped_column(Integer, nullable=False)
    total_credits: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class Option(StrictModel):
    id: str
    name: str


class VoiceOption(Option):
    provider_code: str
    languages: list[str]
    gender: str | None = None


class TranslationConfig(StrictModel):
    target_languages: list[Option]
    video_ratios: list[Option]
    voices: list[VoiceOption]
    preview_credits: int = PREVIEW_CREDITS
    voice_replacement_surcharge_credits_per_minute: int = (
        VOICE_REPLACEMENT_SURCHARGE_CREDITS_PER_MINUTE
    )
    max_segment_words_or_chars: int = 100
    timing_tolerance_ms: int = TTS_TIMING_TOLERANCE_MS


class Region(StrictModel):
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    width: float = Field(gt=0, le=1)
    height: float = Field(gt=0, le=1)


class TranslationSettings(StrictModel):
    target_language: str | None = None
    video_ratio: str = "original"
    execution_mode: Literal["manual", "auto"] = "manual"
    voice_id: str | None = None
    original_sound_mode: Literal["voice_replacement", "translated_voice_only"] = (
        "translated_voice_only"
    )
    preserve_source_subtitles: bool = False
    source_subtitle_region: Region | None = None
    translated_subtitle_region: Region | None = None
    background_music_asset_id: str | None = None
    background_music_volume: int = Field(default=50, ge=0, le=100)

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_original_sound_mode(cls, value):
        """读取旧项目和滚动部署请求时立即收敛为新双态合同。"""

        if not isinstance(value, dict):
            return value
        normalized = dict(value)
        normalized["original_sound_mode"] = normalize_original_sound_mode(
            normalized.get("original_sound_mode")
        )
        return normalized


class SegmentInput(StrictModel):
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)
    source_text: str = Field(min_length=1, max_length=4000)
    translated_text: str = Field(min_length=1, max_length=4000)
    voice_id: str
    speed: float = Field(default=1, ge=0.5, le=2)
    volume: int = Field(default=100, ge=0, le=100)
    keep_original_sound: bool = False


class SegmentPatch(StrictModel):
    translated_text: str | None = Field(default=None, min_length=1, max_length=4000)
    voice_id: str | None = None
    speed: float | None = Field(default=None, ge=0.5, le=2)
    volume: int | None = Field(default=None, ge=0, le=100)
    keep_original_sound: bool | None = None


class SegmentData(SegmentInput):
    id: str
    segment_index: int
    preview_audio_url: str | None = None
    preview_valid: bool
    tts_duration_ms: int | None = None
    timing_fit_status: str = "pending"
    timing_overflow_ms: int = 0
    fitted_speed: float | None = None
    allowed_duration_ms: int
    timing_tolerance_ms: int = TTS_TIMING_TOLERANCE_MS


class GlobalVoiceRequest(StrictModel):
    voice_id: str
    overwrite_custom: bool = False


class PreviewData(StrictModel):
    segment_id: str
    core_task_id: str
    credits_charged: int
    preview_audio_url: str | None = None
    status: str


class StartData(StrictModel):
    workflow_id: str


class TranslationCostData(StrictModel):
    """当前报价或已启动任务的冻结收费快照。"""

    total_source_seconds: int
    billed_minutes: int
    price_version: int
    base_credits_per_minute: int
    base_credits: int
    original_sound_mode: Literal["voice_replacement", "translated_voice_only"]
    voice_replacement_credits_per_minute: int
    voice_replacement_credits: int
    credits: int


class TranslationCostRequest(StrictModel):
    """尚未启动时供设置页预览的服务端权威音频模式。"""

    original_sound_mode: (
        Literal["voice_replacement", "translated_voice_only"] | None
    ) = None


class RetryData(StrictModel):
    workflow_id: str
    resumed_from_node: str


class RetryRequest(StrictModel):
    """从指定的翻译工作流节点恢复，已完成产物不受影响。"""

    restart_from: (
        Literal[
            "subtitle_recognition",
            "subtitle_translation",
            "subtitle_rewrite",
            "tts",
            "video_render",
            "publish_artifacts",
        ]
        | None
    ) = None


router = APIRouter()


def _owned(
    session: Session, user_id: str, project_id: str, lock: bool = False
) -> Project:
    stmt = select(Project).where(
        Project.id == project_id, Project.user_id == user_id, Project.product == PRODUCT
    )
    if lock:
        stmt = stmt.with_for_update()
    item = session.scalar(stmt)
    if not item:
        raise ApiError("PROJECT_NOT_FOUND", "Video translation project not found", 404)
    return item


def _text_units(text: str, language: str) -> int:
    return (
        len("".join(text.split()))
        if language in {"ja", "ko"}
        else len([w for w in text.split() if w])
    )


def _validate_text(text: str, language: str) -> None:
    if _text_units(text, language) > 100:
        raise ApiError(
            "TRANSLATION_SEGMENT_TOO_LONG",
            "Translated text must not exceed 100 characters or words",
            422,
        )


def _digest(s: VideoTranslationSegment) -> str:
    return hashlib.sha256(
        f"{s.translated_text}|{s.voice_id}|{s.speed}|{s.volume}".encode()
    ).hexdigest()


def _invalidate_tts_timing(s: VideoTranslationSegment) -> None:
    """台词或声音参数变化后，旧音频时长不再能代表当前行。"""

    s.tts_duration_ms = None
    s.timing_fit_status = "pending"
    s.timing_overflow_ms = 0
    s.fitted_speed = None


def _preview_caller_task_id(
    project_id: str, segment_id: str, idempotency_key: str
) -> str:
    """Core caller_task_id 最长 80 字符，不能直接拼接三个 UUID。"""

    identity = f"{project_id}:{segment_id}:{idempotency_key}".encode("utf-8")
    return f"translation-preview:{hashlib.sha256(identity).hexdigest()[:40]}"


def _serialize(s: VideoTranslationSegment) -> SegmentData:
    return SegmentData(
        id=s.id,
        segment_index=s.segment_index,
        start_ms=s.start_ms,
        end_ms=s.end_ms,
        source_text=s.source_text,
        translated_text=s.translated_text,
        voice_id=s.voice_id,
        speed=s.speed,
        volume=s.volume,
        keep_original_sound=s.keep_original_sound,
        preview_audio_url=s.preview_audio_url,
        preview_valid=bool(s.preview_audio_url and s.preview_digest == _digest(s)),
        tts_duration_ms=s.tts_duration_ms,
        timing_fit_status=s.timing_fit_status or "pending",
        timing_overflow_ms=s.timing_overflow_ms or 0,
        fitted_speed=s.fitted_speed,
        allowed_duration_ms=s.end_ms - s.start_ms,
    )


def _settings(record: VideoTranslationSettings | None) -> TranslationSettings:
    return TranslationSettings(**(record.settings if record else {}))


def _translation_cost_data(
    session: Session,
    *,
    project: Project,
    setting: TranslationSettings,
) -> TranslationCostData:
    """读取新报价；任务启动后始终返回同一份冻结收费快照。"""

    frozen = session.get(VideoTranslationCharge, project.id)
    if frozen is not None:
        return TranslationCostData(
            total_source_seconds=frozen.total_source_seconds,
            billed_minutes=frozen.billed_minutes,
            price_version=frozen.price_version,
            base_credits_per_minute=frozen.base_credits_per_minute,
            base_credits=frozen.base_credits,
            original_sound_mode=frozen.original_sound_mode,
            voice_replacement_credits_per_minute=(
                frozen.voice_replacement_credits_per_minute
            ),
            voice_replacement_credits=frozen.voice_replacement_credits,
            credits=frozen.total_credits,
        )

    videos = list(
        session.scalars(
            select(Asset).where(
                Asset.project_id == project.id,
                Asset.asset_type == "video",
            )
        )
    )
    if not videos:
        raise ApiError(
            "PROJECT_ASSETS_NOT_READY", "Project video assets are not ready", 409
        )
    # Core 的视频翻译渲染以一个原视频作为连续时间轴；上传页也明确限制为 1 个。
    # 直接 API 调用同样必须在报价/扣费前拒绝多视频，避免先收费再由 Core 失败。
    if len(videos) != 1:
        raise ApiError(
            "PROJECT_VIDEO_COUNT_INVALID",
            "Video translation requires exactly one source video",
            409,
        )
    if any(video.status != "ready" for video in videos):
        raise ApiError(
            "PROJECT_ASSETS_NOT_READY", "Project video assets are not ready", 409
        )
    if any(video.duration_seconds is None for video in videos):
        raise ApiError(
            "PROJECT_DURATION_UNAVAILABLE",
            "Project source video duration is unavailable",
            409,
        )
    # Asset duration is a float. 先将实际时长向上取整到秒，再按分钟整体向上取整。
    total_source_seconds = math.ceil(
        sum(float(video.duration_seconds or 0) for video in videos)
    )
    if total_source_seconds <= 0:
        raise ApiError(
            "PROJECT_DURATION_UNAVAILABLE",
            "Project source video duration must be positive",
            409,
        )
    price = session.scalar(
        select(ProductPrice)
        .where(ProductPrice.product == PRODUCT)
        .order_by(ProductPrice.version.desc())
    )
    if price is None:
        raise ApiError(
            "PROJECT_PRICE_UNAVAILABLE", "Video translation price is unavailable", 503
        )
    mode = normalize_original_sound_mode(setting.original_sound_mode)
    base_credits, voice_replacement_credits, credits = estimate_video_translation_cost(
        total_source_seconds,
        credits_per_minute=price.credits_per_minute,
        original_sound_mode=mode,
        voice_replacement_surcharge_credits_per_minute=(
            VOICE_REPLACEMENT_SURCHARGE_CREDITS_PER_MINUTE
        ),
    )
    return TranslationCostData(
        total_source_seconds=total_source_seconds,
        billed_minutes=(total_source_seconds + 59) // 60,
        price_version=price.version,
        base_credits_per_minute=price.credits_per_minute,
        base_credits=base_credits,
        original_sound_mode=mode,
        voice_replacement_credits_per_minute=(
            VOICE_REPLACEMENT_SURCHARGE_CREDITS_PER_MINUTE
            if mode == "voice_replacement"
            else 0
        ),
        voice_replacement_credits=voice_replacement_credits,
        credits=credits,
    )


def _freeze_translation_charge(
    session: Session,
    *,
    project: Project,
    workflow: Workflow,
    quote: TranslationCostData,
) -> VideoTranslationCharge:
    """写入启动价目，再由同一事务追加唯一项目扣费流水。"""

    charge = VideoTranslationCharge(
        project_id=project.id,
        workflow_id=workflow.id,
        price_version=quote.price_version,
        total_source_seconds=quote.total_source_seconds,
        billed_minutes=quote.billed_minutes,
        base_credits_per_minute=quote.base_credits_per_minute,
        original_sound_mode=quote.original_sound_mode,
        voice_replacement_credits_per_minute=(
            quote.voice_replacement_credits_per_minute
        ),
        base_credits=quote.base_credits,
        voice_replacement_credits=quote.voice_replacement_credits,
        total_credits=quote.credits,
    )
    session.add(charge)
    session.flush()
    try:
        _apply_credit(
            session,
            user_id=project.user_id,
            entry_type="charge",
            amount=-quote.credits,
            idempotency_key=f"charge:{project.id}",
            reference_id=project.id,
            reason="video_translation_charge",
        )
    except InsufficientCreditsError as exc:
        raise ApiError("INSUFFICIENT_CREDITS", "Insufficient credits", 409) from exc
    return charge


def _ensure_rewrite_node(
    session: Session, workflow: Workflow, *, initially_completed: bool = False
) -> WorkflowNode:
    node = session.scalar(
        select(WorkflowNode).where(
            WorkflowNode.workflow_id == workflow.id,
            WorkflowNode.name == "subtitle_rewrite",
        )
    )
    if node is None:
        node = WorkflowNode(
            id=_new_id("wnd"),
            workflow_id=workflow.id,
            name="subtitle_rewrite",
            state="completed" if initially_completed else "queued",
            depends_on=["subtitle_translation"],
            retryable=True,
            manual_gate=not initially_completed,
            max_attempts=2,
        )
        session.add(node)
        session.flush()
    return node


@router.get(
    "/products/video-translation/config", response_model=ApiResponse[TranslationConfig]
)
def config(
    request_id: Annotated[str, Depends(get_request_id)], settings=Depends(get_settings)
):
    try:
        voices = HttpCoreClient(
            base_url=str(settings.core_base_url),
            request_token=settings.core_request_token,
        ).get_voice_capabilities()
    except CoreClientError as exc:
        raise ApiError(
            "CORE_CAPABILITIES_UNAVAILABLE",
            "Core voice capabilities are unavailable",
            503,
        ) from exc
    return ApiResponse(
        code="VIDEO_TRANSLATION_CONFIG_RETRIEVED",
        message="Video translation configuration retrieved",
        request_id=request_id,
        data=TranslationConfig(
            target_languages=[Option(id=x, name=x) for x in SUPPORTED_LANGUAGES],
            video_ratios=[Option(id=x, name=x) for x in RATIOS],
            voices=[
                VoiceOption(
                    id=x.voice_id,
                    name=x.name,
                    provider_code=x.provider_code,
                    languages=list(x.languages),
                    gender=x.gender,
                )
                for x in voices
            ],
            voice_replacement_surcharge_credits_per_minute=(
                VOICE_REPLACEMENT_SURCHARGE_CREDITS_PER_MINUTE
            ),
        ),
    )


@router.get(
    "/projects/{project_id}/video-translation/settings",
    response_model=ApiResponse[TranslationSettings],
)
def get_settings_route(
    project_id: str,
    request: Request,
    token: Annotated[str, Depends(bearer_token)],
    auth: Annotated[AuthService, Depends(get_auth_service)],
    request_id: Annotated[str, Depends(get_request_id)],
):
    user = auth.resolve_user(token)
    with Session(request.app.state.database_engine) as s:
        _owned(s, user.id, project_id)
        data = _settings(s.get(VideoTranslationSettings, project_id))
    return ApiResponse(
        code="VIDEO_TRANSLATION_SETTINGS_RETRIEVED",
        message="Settings retrieved",
        data=data,
        request_id=request_id,
    )


@router.post(
    "/projects/{project_id}/video-translation/cost-estimate",
    response_model=ApiResponse[TranslationCostData],
)
def translation_cost_estimate(
    project_id: str,
    request: Request,
    token: Annotated[str, Depends(bearer_token)],
    auth: Annotated[AuthService, Depends(get_auth_service)],
    request_id: Annotated[str, Depends(get_request_id)],
    body: TranslationCostRequest | None = None,
):
    """报价和启动统一走同一计费函数，启动后返回冻结值而非最新价。"""

    user = auth.resolve_user(token)
    with Session(request.app.state.database_engine) as session:
        project = _owned(session, user.id, project_id)
        setting = _settings(session.get(VideoTranslationSettings, project_id))
        if body is not None and body.original_sound_mode is not None:
            setting = setting.model_copy(
                update={"original_sound_mode": body.original_sound_mode}
            )
        data = _translation_cost_data(
            session,
            project=project,
            setting=setting,
        )
    return ApiResponse(
        code="VIDEO_TRANSLATION_COST_ESTIMATED",
        message="Video translation cost estimated",
        data=data,
        request_id=request_id,
    )


@router.put(
    "/projects/{project_id}/video-translation/settings",
    response_model=ApiResponse[TranslationSettings],
)
def put_settings(
    project_id: str,
    body: TranslationSettings,
    request: Request,
    token: Annotated[str, Depends(bearer_token)],
    auth: Annotated[AuthService, Depends(get_auth_service)],
    request_id: Annotated[str, Depends(get_request_id)],
):
    if body.target_language and body.target_language not in SUPPORTED_LANGUAGES:
        raise ApiError(
            "TARGET_LANGUAGE_UNSUPPORTED", "Target language is unsupported", 422
        )
    user = auth.resolve_user(token)
    with Session(request.app.state.database_engine) as s:
        with s.begin():
            p = _owned(s, user.id, project_id, True)
            if p.current_stage not in {"created", "settings"}:
                raise ApiError(
                    "PROJECT_SETTINGS_LOCKED",
                    "Settings are locked after translation starts",
                    409,
                )
            r = s.get(VideoTranslationSettings, project_id)
            if r:
                r.settings = body.model_dump()
            else:
                s.add(
                    VideoTranslationSettings(
                        project_id=project_id, settings=body.model_dump()
                    )
                )
            p.current_stage = "settings"
    return ApiResponse(
        code="VIDEO_TRANSLATION_SETTINGS_UPDATED",
        message="Settings updated",
        data=body,
        request_id=request_id,
    )


@router.put(
    "/projects/{project_id}/video-translation/segments",
    response_model=ApiResponse[list[SegmentData]],
)
def replace_segments(
    project_id: str,
    body: list[SegmentInput],
    request: Request,
    token: Annotated[str, Depends(bearer_token)],
    auth: Annotated[AuthService, Depends(get_auth_service)],
    request_id: Annotated[str, Depends(get_request_id)],
):
    user = auth.resolve_user(token)
    with Session(request.app.state.database_engine) as s:
        with s.begin():
            _owned(s, user.id, project_id, True)
            setting = _settings(s.get(VideoTranslationSettings, project_id))
            lang = setting.target_language or "en"
            for x in body:
                if x.end_ms <= x.start_ms:
                    raise ApiError(
                        "TRANSLATION_SEGMENT_TIME_INVALID",
                        "Segment end must be after start",
                        422,
                    )
                _validate_text(x.translated_text, lang)
            for old in s.scalars(
                select(VideoTranslationSegment).where(
                    VideoTranslationSegment.project_id == project_id
                )
            ).all():
                s.delete(old)
            rows = [
                VideoTranslationSegment(
                    id=_id("vts"),
                    project_id=project_id,
                    segment_index=i,
                    **x.model_dump(),
                )
                for i, x in enumerate(body)
            ]
            s.add_all(rows)
        data = [_serialize(x) for x in rows]
    return ApiResponse(
        code="VIDEO_TRANSLATION_SEGMENTS_REPLACED",
        message="Segments saved",
        data=data,
        request_id=request_id,
    )


@router.get(
    "/projects/{project_id}/video-translation/segments",
    response_model=ApiResponse[list[SegmentData]],
)
def list_segments(
    project_id: str,
    request: Request,
    token: Annotated[str, Depends(bearer_token)],
    auth: Annotated[AuthService, Depends(get_auth_service)],
    request_id: Annotated[str, Depends(get_request_id)],
):
    user = auth.resolve_user(token)
    with Session(request.app.state.database_engine) as s:
        _owned(s, user.id, project_id)
        rows = s.scalars(
            select(VideoTranslationSegment)
            .where(VideoTranslationSegment.project_id == project_id)
            .order_by(VideoTranslationSegment.segment_index)
        ).all()
        data = [_serialize(x) for x in rows]
    return ApiResponse(
        code="VIDEO_TRANSLATION_SEGMENTS_RETRIEVED",
        message="Segments retrieved",
        data=data,
        request_id=request_id,
    )


@router.patch(
    "/projects/{project_id}/video-translation/segments/{segment_id}",
    response_model=ApiResponse[SegmentData],
)
def patch_segment(
    project_id: str,
    segment_id: str,
    body: SegmentPatch,
    request: Request,
    token: Annotated[str, Depends(bearer_token)],
    auth: Annotated[AuthService, Depends(get_auth_service)],
    request_id: Annotated[str, Depends(get_request_id)],
):
    user = auth.resolve_user(token)
    with Session(request.app.state.database_engine) as s:
        with s.begin():
            _owned(s, user.id, project_id, True)
            row = s.scalar(
                select(VideoTranslationSegment)
                .where(
                    VideoTranslationSegment.id == segment_id,
                    VideoTranslationSegment.project_id == project_id,
                )
                .with_for_update()
            )
            if not row:
                raise ApiError(
                    "TRANSLATION_SEGMENT_NOT_FOUND", "Segment not found", 404
                )
            before = _digest(row)
            for k, v in body.model_dump(exclude_none=True).items():
                setattr(row, k, v)
            if body.voice_id is not None:
                row.voice_overridden = True
            lang = (
                _settings(s.get(VideoTranslationSettings, project_id)).target_language
                or "en"
            )
            _validate_text(row.translated_text, lang)
            if before != _digest(row):
                row.preview_audio_url = None
                row.preview_digest = None
                _invalidate_tts_timing(row)
            data = _serialize(row)
    return ApiResponse(
        code="VIDEO_TRANSLATION_SEGMENT_UPDATED",
        message="Segment updated",
        data=data,
        request_id=request_id,
    )


@router.post(
    "/projects/{project_id}/video-translation/segments/voice",
    response_model=ApiResponse[list[SegmentData]],
)
def apply_voice(
    project_id: str,
    body: GlobalVoiceRequest,
    request: Request,
    token: Annotated[str, Depends(bearer_token)],
    auth: Annotated[AuthService, Depends(get_auth_service)],
    request_id: Annotated[str, Depends(get_request_id)],
):
    user = auth.resolve_user(token)
    with Session(request.app.state.database_engine) as s:
        with s.begin():
            _owned(s, user.id, project_id, True)
            rows = s.scalars(
                select(VideoTranslationSegment)
                .where(VideoTranslationSegment.project_id == project_id)
                .with_for_update()
            ).all()
            for row in rows:
                if row.voice_overridden and not body.overwrite_custom:
                    continue
                if row.voice_id != body.voice_id:
                    row.voice_id = body.voice_id
                    row.preview_audio_url = None
                    row.preview_digest = None
                    _invalidate_tts_timing(row)
                if body.overwrite_custom:
                    row.voice_overridden = False
            data = [_serialize(x) for x in rows]
    return ApiResponse(
        code="VIDEO_TRANSLATION_GLOBAL_VOICE_APPLIED",
        message="Voice applied",
        data=data,
        request_id=request_id,
    )


@router.post(
    "/projects/{project_id}/video-translation/segments/{segment_id}/preview",
    response_model=ApiResponse[PreviewData],
    status_code=status.HTTP_202_ACCEPTED,
)
def preview(
    project_id: str,
    segment_id: str,
    request: Request,
    token: Annotated[str, Depends(bearer_token)],
    auth: Annotated[AuthService, Depends(get_auth_service)],
    settings: Annotated[Settings, Depends(get_settings)],
    request_id: Annotated[str, Depends(get_request_id)],
    idempotency_key: Annotated[str | None, Header(alias="X-Idempotency-Key")] = None,
):
    if not idempotency_key:
        raise ApiError("IDEMPOTENCY_KEY_REQUIRED", "X-Idempotency-Key is required", 422)
    user = auth.resolve_user(token)
    with Session(request.app.state.database_engine) as session:
        with session.begin():
            _owned(session, user.id, project_id, True)
            row = session.scalar(
                select(VideoTranslationSegment)
                .where(
                    VideoTranslationSegment.id == segment_id,
                    VideoTranslationSegment.project_id == project_id,
                )
                .with_for_update()
            )
            if not row:
                raise ApiError(
                    "TRANSLATION_SEGMENT_NOT_FOUND", "Segment not found", 404
                )
            # 当前文本、音色和参数已有可用试听时直接复用它。前端再次点击应播放
            # 既有音频，绝不能重新创建 Core TTS 任务或重复扣除 12 积分。
            if row.preview_audio_url and row.preview_digest == _digest(row):
                return ApiResponse(
                    code="VIDEO_TRANSLATION_PREVIEW_READY",
                    message="Preview already ready",
                    data=PreviewData(
                        segment_id=segment_id,
                        core_task_id="",
                        credits_charged=0,
                        preview_audio_url=row.preview_audio_url,
                        status="succeeded",
                    ),
                    request_id=request_id,
                )
            existing = session.scalar(
                select(VideoTranslationPreviewCharge).where(
                    VideoTranslationPreviewCharge.project_id == project_id,
                    VideoTranslationPreviewCharge.segment_id == segment_id,
                    VideoTranslationPreviewCharge.idempotency_key == idempotency_key,
                )
            )
            if existing:
                data = PreviewData(
                    segment_id=segment_id,
                    core_task_id=existing.core_task_id or "",
                    credits_charged=PREVIEW_CREDITS
                    if existing.status == "succeeded"
                    else 0,
                    preview_audio_url=row.preview_audio_url
                    if existing.status == "succeeded"
                    else None,
                    status=existing.status,
                )
            else:
                language = (
                    _settings(
                        session.get(VideoTranslationSettings, project_id)
                    ).target_language
                    or "en"
                )
                try:
                    core_task_id = HttpCoreClient(
                        base_url=str(settings.core_base_url),
                        request_token=settings.core_request_token,
                    ).submit_tts_preview(
                        voice_id=row.voice_id,
                        language=language,
                        text=row.translated_text,
                        speed=row.speed,
                        volume=row.volume,
                        caller_task_id=_preview_caller_task_id(
                            project_id, segment_id, idempotency_key
                        ),
                    )
                except CoreClientRejectedError as exc:
                    raise ApiError(
                        "CORE_TTS_REQUEST_REJECTED",
                        "Preview parameters were rejected by the TTS service",
                        422,
                    ) from exc
                except CoreClientError as exc:
                    raise ApiError(
                        "CORE_TTS_UNAVAILABLE",
                        "Preview synthesis could not be started",
                        503,
                    ) from exc
                existing = VideoTranslationPreviewCharge(
                    id=_id("vtp"),
                    project_id=project_id,
                    segment_id=segment_id,
                    idempotency_key=idempotency_key,
                    core_task_id=core_task_id,
                    status="pending",
                )
                session.add(existing)
                data = PreviewData(
                    segment_id=segment_id,
                    core_task_id=core_task_id,
                    credits_charged=0,
                    status="pending",
                )
    return ApiResponse(
        code="VIDEO_TRANSLATION_PREVIEW_QUEUED",
        message="Preview synthesis queued",
        data=data,
        request_id=request_id,
    )


@router.post(
    "/projects/{project_id}/video-translation/segments/{segment_id}/preview/{core_task_id}/reconcile",
    response_model=ApiResponse[PreviewData],
)
def reconcile_preview(
    project_id: str,
    segment_id: str,
    core_task_id: str,
    request: Request,
    token: Annotated[str, Depends(bearer_token)],
    auth: Annotated[AuthService, Depends(get_auth_service)],
    settings: Annotated[Settings, Depends(get_settings)],
    request_id: Annotated[str, Depends(get_request_id)],
):
    user = auth.resolve_user(token)
    with Session(request.app.state.database_engine) as session:
        with session.begin():
            _owned(session, user.id, project_id, True)
            charge = session.scalar(
                select(VideoTranslationPreviewCharge)
                .where(
                    VideoTranslationPreviewCharge.project_id == project_id,
                    VideoTranslationPreviewCharge.segment_id == segment_id,
                    VideoTranslationPreviewCharge.core_task_id == core_task_id,
                )
                .with_for_update()
            )
            row = session.scalar(
                select(VideoTranslationSegment)
                .where(
                    VideoTranslationSegment.id == segment_id,
                    VideoTranslationSegment.project_id == project_id,
                )
                .with_for_update()
            )
            if not charge or not row:
                raise ApiError(
                    "TRANSLATION_PREVIEW_NOT_FOUND", "Preview task not found", 404
                )
            if charge.status == "succeeded":
                return ApiResponse(
                    code="VIDEO_TRANSLATION_PREVIEW_READY",
                    message="Preview ready",
                    data=PreviewData(
                        segment_id=segment_id,
                        core_task_id=core_task_id,
                        credits_charged=PREVIEW_CREDITS,
                        preview_audio_url=row.preview_audio_url,
                        status="succeeded",
                    ),
                    request_id=request_id,
                )
            try:
                core = HttpCoreClient(
                    base_url=str(settings.core_base_url),
                    request_token=settings.core_request_token,
                ).get_task_result(core_task_id)
            except CoreClientError as exc:
                raise ApiError(
                    "CORE_TTS_UNAVAILABLE", "Preview status unavailable", 503
                ) from exc
            if core.status == "failed":
                charge.status = "failed"
                return ApiResponse(
                    code="VIDEO_TRANSLATION_PREVIEW_FAILED",
                    message="Preview failed; no credits charged",
                    data=PreviewData(
                        segment_id=segment_id,
                        core_task_id=core_task_id,
                        credits_charged=0,
                        status="failed",
                    ),
                    request_id=request_id,
                )
            if core.status != "succeeded":
                return ApiResponse(
                    code="VIDEO_TRANSLATION_PREVIEW_PENDING",
                    message="Preview is processing",
                    data=PreviewData(
                        segment_id=segment_id,
                        core_task_id=core_task_id,
                        credits_charged=0,
                        status="pending",
                    ),
                    request_id=request_id,
                )
            audio = next(
                (
                    x.get("url")
                    for x in core.artifacts
                    if x.get("kind") in {"voice", "audio", "tts"}
                    and isinstance(x.get("url"), str)
                ),
                None,
            )
            if not audio:
                charge.status = "failed"
                return ApiResponse(
                    code="VIDEO_TRANSLATION_PREVIEW_FAILED",
                    message="Preview artifact missing; no credits charged",
                    data=PreviewData(
                        segment_id=segment_id,
                        core_task_id=core_task_id,
                        credits_charged=0,
                        status="failed",
                    ),
                    request_id=request_id,
                )
            try:
                _apply_credit(
                    session,
                    user_id=user.id,
                    entry_type="charge",
                    amount=-PREVIEW_CREDITS,
                    idempotency_key=f"translation-preview:{project_id}:{segment_id}:{charge.id}",
                    reference_id=project_id,
                    reason="video_translation_preview",
                )
            except InsufficientCreditsError as exc:
                raise ApiError(
                    "INSUFFICIENT_CREDITS", "Insufficient credits", 409
                ) from exc
            charge.status = "succeeded"
            row.preview_audio_url = audio
            row.preview_digest = _digest(row)
            data = PreviewData(
                segment_id=segment_id,
                core_task_id=core_task_id,
                credits_charged=PREVIEW_CREDITS,
                preview_audio_url=audio,
                status="succeeded",
            )
    return ApiResponse(
        code="VIDEO_TRANSLATION_PREVIEW_READY",
        message="Preview ready and charged",
        data=data,
        request_id=request_id,
    )


class StageNode(StrictModel):
    name: str
    state: str


class StageData(StrictModel):
    project_id: str
    status: str
    current_stage: str
    execution_mode: str
    workflow_id: str | None = None
    nodes: list[StageNode] = []
    tts_completed_segments: int = 0
    tts_total_segments: int = 0
    rewrite_attempts: int = 0
    max_rewrite_attempts: int = 2


def _start_translation(session: Session, *, user_id: str, project_id: str) -> str:
    project = _owned(session, user_id, project_id, True)
    setting = _settings(session.get(VideoTranslationSettings, project_id))
    if not setting.target_language or not setting.voice_id:
        raise ApiError(
            "PROJECT_SETTINGS_INCOMPLETE", "Target language and voice are required", 422
        )
    if project.current_stage not in {"created", "settings"}:
        raise ApiError("PROJECT_ALREADY_STARTED", "Translation already started", 409)
    quote = _translation_cost_data(session, project=project, setting=setting)
    snap = session.scalar(
        select(WorkflowTemplateSnapshot)
        .where(WorkflowTemplateSnapshot.template_name == PRODUCT)
        .order_by(WorkflowTemplateSnapshot.created_at.desc())
    )
    if not snap:
        raise ApiError(
            "PROJECT_WORKFLOW_UNAVAILABLE",
            "Video translation workflow is unavailable",
            503,
        )
    workflow = Workflow(
        id=_new_id("wfl"),
        user_id=user_id,
        project_id=project.id,
        template_snapshot_id=snap.id,
        state="queued",
        state_version=1,
    )
    session.add(workflow)
    session.flush()
    _freeze_translation_charge(session, project=project, workflow=workflow, quote=quote)
    dependencies = {
        "subtitle_recognition": [],
        "subtitle_translation": ["subtitle_recognition"],
        # 常规流程无需压缩重译，所以该节点初始即完成；TTS 实测超限时才
        # 将它重置为 queued，且最多允许两个真实 Core attempt。
        "subtitle_rewrite": ["subtitle_translation"],
        "tts": ["subtitle_translation"],
        "video_render": ["tts"],
        "publish_artifacts": ["video_render"],
    }
    for name in NODES:
        # 手动模式必须先停在译文编辑。TTS 和渲染都只能由用户确认动作
        # 依次解除，不能让调度器在字幕翻译完成后抢先合成或渲染。
        manual = name in {"tts", "video_render"} and setting.execution_mode == "manual"
        session.add(
            WorkflowNode(
                id=_new_id("wnd"),
                workflow_id=workflow.id,
                name=name,
                state="completed" if name == "subtitle_rewrite" else "queued",
                depends_on=dependencies[name],
                retryable=name == "subtitle_rewrite" or not manual,
                manual_gate=manual,
                max_attempts=(
                    2 if name == "subtitle_rewrite" else 3 if not manual else 1
                ),
            )
        )
    project.status = "queued"
    project.current_stage = "analysis"
    session.add(
        WorkflowOutbox(
            id=_new_id("obx"),
            workflow_id=workflow.id,
            workflow_node_id=None,
            event_type="workflow.state_changed",
            idempotency_key=f"workflow-state:queued:{project.id}",
            payload={
                "state": "queued",
                "state_version": 1,
                "stage": "analysis",
                "product": PRODUCT,
                "translation_settings": setting.model_dump(),
                "tasks": ["subtitle_recognition", "subtitle_translation", "tts"],
            },
            status="pending",
        )
    )
    return workflow.id


@router.post(
    "/projects/{project_id}/video-translation/start",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=ApiResponse[StartData],
)
def start_translation(
    project_id: str,
    request: Request,
    token: Annotated[str, Depends(bearer_token)],
    auth: Annotated[AuthService, Depends(get_auth_service)],
    request_id: Annotated[str, Depends(get_request_id)],
):
    user = auth.resolve_user(token)
    with Session(request.app.state.database_engine) as s:
        with s.begin():
            workflow_id = _start_translation(s, user_id=user.id, project_id=project_id)
    return ApiResponse(
        code="VIDEO_TRANSLATION_STARTED",
        message="Video translation started",
        data=StartData(workflow_id=workflow_id),
        request_id=request_id,
    )


@router.get(
    "/projects/{project_id}/video-translation/stage",
    response_model=ApiResponse[StageData],
)
def translation_stage(
    project_id: str,
    request: Request,
    token: Annotated[str, Depends(bearer_token)],
    auth: Annotated[AuthService, Depends(get_auth_service)],
    request_id: Annotated[str, Depends(get_request_id)],
    settings: Annotated[Settings, Depends(get_settings)],
):
    user = auth.resolve_user(token)
    with Session(request.app.state.database_engine) as s:
        p = _owned(s, user.id, project_id)
        workflow = s.scalar(select(Workflow).where(Workflow.project_id == project_id))
        nodes = (
            []
            if not workflow
            else [
                StageNode(name=x.name, state=x.state)
                for x in s.scalars(
                    select(WorkflowNode)
                    .where(WorkflowNode.workflow_id == workflow.id)
                    .order_by(WorkflowNode.created_at)
                ).all()
            ]
        )
        mode = _settings(s.get(VideoTranslationSettings, project_id)).execution_mode
        tts_total = (
            s.scalar(
                select(func.count(VideoTranslationSegment.id)).where(
                    VideoTranslationSegment.project_id == project_id
                )
            )
            or 0
        )
        tts_completed = 0
        rewrite_attempts = 0
        rewrite_node = next(
            (node for node in nodes if node.name == "subtitle_rewrite"), None
        )
        if workflow and rewrite_node:
            rewrite_attempts = (
                s.scalar(
                    select(func.count())
                    .select_from(WorkflowNodeAttempt)
                    .join(WorkflowNode)
                    .where(
                        WorkflowNode.workflow_id == workflow.id,
                        WorkflowNode.name == "subtitle_rewrite",
                    )
                )
                or 0
            )
        tts_node = next((node for node in nodes if node.name == "tts"), None)
        if tts_node and tts_node.state in {"completed", "succeeded"}:
            tts_completed = tts_total
        elif workflow and tts_node:
            attempt = s.scalar(
                select(WorkflowNodeAttempt)
                .join(
                    WorkflowNode,
                    WorkflowNode.id == WorkflowNodeAttempt.workflow_node_id,
                )
                .where(
                    WorkflowNode.workflow_id == workflow.id,
                    WorkflowNode.name == "tts",
                    WorkflowNodeAttempt.core_task_id.is_not(None),
                )
                .order_by(WorkflowNodeAttempt.created_at.desc())
            )
            if attempt and attempt.core_task_id:
                try:
                    progress = (
                        HttpCoreClient(
                            base_url=str(settings.core_base_url),
                            request_token=settings.core_request_token,
                        )
                        .get_task_result(attempt.core_task_id)
                        .progress
                    )
                    # Core 的 10-90% 区间仅表示每条字幕已合成的数量。
                    tts_completed = min(
                        tts_total,
                        max(0, round(((progress - 10) / 80) * tts_total)),
                    )
                except CoreClientError:
                    pass
        data = StageData(
            project_id=project_id,
            status=p.status,
            current_stage=p.current_stage,
            execution_mode=mode,
            workflow_id=workflow.id if workflow else None,
            nodes=nodes,
            tts_completed_segments=tts_completed,
            tts_total_segments=tts_total,
            rewrite_attempts=rewrite_attempts,
        )
    return ApiResponse(
        code="VIDEO_TRANSLATION_STAGE_RETRIEVED",
        message="Stage retrieved",
        data=data,
        request_id=request_id,
    )


@router.post(
    "/projects/{project_id}/video-translation/retry",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=ApiResponse[RetryData],
)
def retry_translation(
    project_id: str,
    body: RetryRequest | None,
    request: Request,
    token: Annotated[str, Depends(bearer_token)],
    auth: Annotated[AuthService, Depends(get_auth_service)],
    request_id: Annotated[str, Depends(get_request_id)],
):
    """仅把失败节点重新入队；已完成节点和产物不动，保证断点恢复。"""
    user = auth.resolve_user(token)
    with Session(request.app.state.database_engine) as s:
        with s.begin():
            p = _owned(s, user.id, project_id, True)
            workflow = s.scalar(
                select(Workflow)
                .where(Workflow.project_id == project_id)
                .with_for_update()
            )
            if not workflow:
                raise ApiError(
                    "PROJECT_WORKFLOW_UNAVAILABLE", "Workflow is unavailable", 409
                )
            # 项目行与 workflow 行均已锁定。只有已完成失败收口（含退款）的
            # 终态工作流可以发起一次新执行；第一次请求会立刻改为 queued，
            # 后续重复点击即使指定 restart_from 也不能利用旧 failed attempt 二扣。
            if workflow.state != "failed":
                raise ApiError(
                    "PROJECT_NOT_RETRYABLE", "No retryable failed workflow", 409
                )
            restart_from = body.restart_from if body is not None else None
            failed = s.scalar(
                select(WorkflowNode)
                .where(
                    WorkflowNode.workflow_id == workflow.id,
                    WorkflowNode.state == "failed",
                )
                .order_by(WorkflowNode.created_at)
                .with_for_update()
            )
            if restart_from:
                failed = s.scalar(
                    select(WorkflowNode)
                    .where(
                        WorkflowNode.workflow_id == workflow.id,
                        WorkflowNode.name == restart_from,
                    )
                    .with_for_update()
                )
                if failed is None:
                    raise ApiError(
                        "PROJECT_WORKFLOW_INVALID",
                        "Translation node is unavailable",
                        409,
                    )
                latest_attempt_state = s.scalar(
                    select(WorkflowNodeAttempt.state)
                    .where(WorkflowNodeAttempt.workflow_node_id == failed.id)
                    .order_by(WorkflowNodeAttempt.attempt_number.desc())
                )
                # 历史恢复逻辑可能已经把失败节点标回 queued；只要最近一次
                # Core attempt 失败，用户仍可从该节点显式重试。
                if failed.state != "failed" and latest_attempt_state != "failed":
                    raise ApiError(
                        "PROJECT_NOT_RETRYABLE", "No retryable failed node", 409
                    )
                downstream_by_start = {
                    "subtitle_recognition": {
                        "subtitle_recognition",
                        "subtitle_translation",
                        "tts",
                        "video_render",
                        "publish_artifacts",
                    },
                    "subtitle_translation": {
                        "subtitle_translation",
                        "tts",
                        "video_render",
                        "publish_artifacts",
                    },
                    "subtitle_rewrite": {"subtitle_rewrite"},
                    "tts": {"tts", "video_render", "publish_artifacts"},
                    "video_render": {"video_render", "publish_artifacts"},
                    "publish_artifacts": {"publish_artifacts"},
                }
                downstream = downstream_by_start[restart_from]
                for node in s.scalars(
                    select(WorkflowNode)
                    .where(
                        WorkflowNode.workflow_id == workflow.id,
                        WorkflowNode.name.in_(downstream),
                    )
                    .with_for_update()
                ).all():
                    node.state = "queued"
                if restart_from in {"tts", "video_render"}:
                    tts_node = s.scalar(
                        select(WorkflowNode)
                        .where(
                            WorkflowNode.workflow_id == workflow.id,
                            WorkflowNode.name == "tts",
                        )
                        .with_for_update()
                    )
                    render_node = s.scalar(
                        select(WorkflowNode)
                        .where(
                            WorkflowNode.workflow_id == workflow.id,
                            WorkflowNode.name == "video_render",
                        )
                        .with_for_update()
                    )
                    if restart_from == "tts" and tts_node is not None:
                        tts_node.manual_gate = False
                    if restart_from == "video_render" and render_node is not None:
                        render_node.manual_gate = False
                if restart_from == "subtitle_translation":
                    # 仅重新翻译时才丢弃旧台词；TTS/渲染失败必须保留用户编辑结果。
                    for row in s.scalars(
                        select(VideoTranslationSegment).where(
                            VideoTranslationSegment.project_id == project_id
                        )
                    ).all():
                        s.delete(row)
            if not failed or (not restart_from and not failed.retryable):
                raise ApiError("PROJECT_NOT_RETRYABLE", "No retryable failed node", 409)
            # 自动重试次数耗尽不应阻断用户手动从失败节点恢复。保留历史
            # attempts 作为审计，只增加一个新的调度槽供下一次 attempt 使用。
            attempt_count = (
                s.scalar(
                    select(func.count())
                    .select_from(WorkflowNodeAttempt)
                    .where(WorkflowNodeAttempt.workflow_node_id == failed.id)
                )
                or 0
            )
            failed.max_attempts = max(failed.max_attempts, attempt_count + 1)
            failed.state = "queued"
            workflow.state = "queued"
            workflow.state_version += 1
            p.status = "queued"
            # 失败收口已经按本次主扣费退款。手动恢复是一次新的有偿执行：
            # 仅从启动时冻结的总价重扣，绝不读取已变更的价格表或设置。新
            # idempotency key 绑定新的 workflow state，重复同一次请求不会二扣。
            frozen_charge = s.get(VideoTranslationCharge, project_id)
            if frozen_charge is None:
                raise ApiError(
                    "PROJECT_CHARGE_UNAVAILABLE",
                    "Translation charge snapshot is unavailable",
                    409,
                )
            last_charge = s.scalar(
                select(CreditLedger)
                .where(
                    CreditLedger.reference_id == project_id,
                    CreditLedger.entry_type == "charge",
                    CreditLedger.reason == "video_translation_charge",
                )
                .order_by(CreditLedger.id.desc())
                .with_for_update()
            )
            if last_charge is None:
                raise ApiError(
                    "PROJECT_CHARGE_UNAVAILABLE",
                    "Translation charge is unavailable",
                    409,
                )
            refunded = s.scalar(
                select(CreditLedger.id).where(
                    CreditLedger.user_id == user.id,
                    CreditLedger.idempotency_key
                    == f"refund:{project_id}:{last_charge.id}",
                )
            )
            if refunded is None:
                raise ApiError(
                    "PROJECT_REFUND_PENDING",
                    "Translation refund has not been finalized",
                    409,
                )
            try:
                _apply_credit(
                    s,
                    user_id=user.id,
                    entry_type="charge",
                    amount=-frozen_charge.total_credits,
                    idempotency_key=(
                        f"charge:{project_id}:retry:{workflow.state_version}"
                    ),
                    reference_id=project_id,
                    reason="video_translation_charge",
                )
            except InsufficientCreditsError as exc:
                raise ApiError(
                    "INSUFFICIENT_CREDITS", "Insufficient credits", 409
                ) from exc
            session_key = (
                f"workflow-retry:{workflow.id}:{failed.id}:{workflow.state_version}"
            )
            s.add(
                WorkflowOutbox(
                    id=_new_id("obx"),
                    workflow_id=workflow.id,
                    workflow_node_id=failed.id,
                    event_type="workflow.retry_requested",
                    idempotency_key=session_key,
                    payload={
                        "product": PRODUCT,
                        "node": restart_from or failed.name,
                        "preserve_completed_assets": True,
                        "state_version": workflow.state_version,
                    },
                    status="pending",
                )
            )
            data = RetryData(
                workflow_id=workflow.id, resumed_from_node=restart_from or failed.name
            )
    return ApiResponse(
        code="VIDEO_TRANSLATION_RETRY_QUEUED",
        message="Failed node queued for retry",
        data=data,
        request_id=request_id,
    )


class TranslationRenderData(StrictModel):
    workflow_id: str
    status: str


class TranslationResultArtifact(StrictModel):
    id: str
    kind: str
    cdn_url: str


class TranslationResultData(StrictModel):
    project_id: str
    artifacts: list[TranslationResultArtifact]


@router.post(
    "/projects/{project_id}/video-translation/render",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=ApiResponse[TranslationRenderData],
)
def render_translation(
    project_id: str,
    request: Request,
    token: Annotated[str, Depends(bearer_token)],
    auth: Annotated[AuthService, Depends(get_auth_service)],
    request_id: Annotated[str, Depends(get_request_id)],
):
    """冻结已编辑的翻译片段并请求通用 Core Render，不读取短剧解说草稿。"""
    user = auth.resolve_user(token)
    with Session(request.app.state.database_engine) as session:
        with session.begin():
            project = _owned(session, user.id, project_id, True)
            workflow = session.scalar(
                select(Workflow)
                .where(Workflow.project_id == project_id)
                .with_for_update()
            )
            setting = _settings(session.get(VideoTranslationSettings, project_id))
            if not workflow:
                raise ApiError(
                    "PROJECT_WORKFLOW_UNAVAILABLE", "Workflow is unavailable", 409
                )
            tts = session.scalar(
                select(WorkflowNode).where(
                    WorkflowNode.workflow_id == workflow.id, WorkflowNode.name == "tts"
                )
            )
            render = session.scalar(
                select(WorkflowNode)
                .where(
                    WorkflowNode.workflow_id == workflow.id,
                    WorkflowNode.name == "video_render",
                )
                .with_for_update()
            )
            publish = session.scalar(
                select(WorkflowNode)
                .where(
                    WorkflowNode.workflow_id == workflow.id,
                    WorkflowNode.name == "publish_artifacts",
                )
                .with_for_update()
            )
            rewrite = session.scalar(
                select(WorkflowNode).where(
                    WorkflowNode.workflow_id == workflow.id,
                    WorkflowNode.name == "subtitle_rewrite",
                )
            )
            if not tts or not render or not publish:
                raise ApiError(
                    "TRANSLATION_TTS_INCOMPLETE",
                    "Translation voices are not ready",
                    409,
                )
            if rewrite is not None and rewrite.state in {"queued", "running"}:
                return ApiResponse(
                    code="VIDEO_TRANSLATION_REWRITE_QUEUED",
                    message="Translation shortening is in progress before TTS",
                    data=TranslationRenderData(
                        workflow_id=workflow.id, status=project.status
                    ),
                    request_id=request_id,
                )
            # 成片已经完成时，Render 页可能因浏览器路由缓存再次挂载。该请求应
            # 幂等成功，让前端跳到导出页，不能错误展示“项目尚不可渲染”。
            if project.status == "completed" and project.current_stage == "export":
                return ApiResponse(
                    code="VIDEO_TRANSLATION_RENDER_QUEUED",
                    message="Video translation already completed",
                    data=TranslationRenderData(
                        workflow_id=workflow.id, status=project.status
                    ),
                    request_id=request_id,
                )
            # 失败收口已退回最近一笔主扣费。Render 页刷新或直接调用本接口
            # 绝不能把失败节点免费重新入队；必须走 /retry，以冻结价格重新扣费
            # 并创建与本轮 state_version 绑定的收费/退款边界。
            if workflow.state in {"failed", "cancelled"}:
                raise ApiError(
                    "PROJECT_RETRY_REQUIRED",
                    "Failed translation workflow must use the retry endpoint",
                    409,
                )
            if setting.execution_mode == "manual" and project.current_stage not in {
                "edit",
                "generate",
            }:
                raise ApiError(
                    "PROJECT_RENDER_NOT_READY", "Project is not ready to render", 409
                )
            if render.state == "completed":
                return ApiResponse(
                    code="VIDEO_TRANSLATION_RENDER_QUEUED",
                    message="Render already queued",
                    data=TranslationRenderData(
                        workflow_id=workflow.id, status=project.status
                    ),
                    request_id=request_id,
                )
            # 兼容已被旧逻辑提前标记为 generate 的项目：修复门控，并重新
            # 投递 TTS。绝不能因历史 render_queued 状态跳过 0/N 的配音。
            if project.current_stage == "generate" and tts.state in {
                "queued",
                "running",
                "completed",
            }:
                if tts.state != "completed":
                    # 历史失败可能已把节点重置为 queued，但历史 attempts 已经
                    # 用尽自动预算。若不增加新的手动恢复槽，dispatcher 每次都会
                    # 因 retry budget exhausted 返回 False，最终永久停在 0/N。
                    attempt_count = (
                        session.scalar(
                            select(func.count())
                            .select_from(WorkflowNodeAttempt)
                            .where(WorkflowNodeAttempt.workflow_node_id == tts.id)
                        )
                        or 0
                    )
                    if attempt_count >= tts.max_attempts:
                        tts.max_attempts = attempt_count + 1
                    tts.manual_gate = False
                    render.manual_gate = True
                    project.status = "queued" if tts.state == "queued" else "analyzing"
                    workflow.state = "queued" if tts.state == "queued" else "running"
                    workflow.state_version += 1
                    if tts.state == "queued":
                        session.add(
                            WorkflowOutbox(
                                id=_new_id("obx"),
                                workflow_id=workflow.id,
                                workflow_node_id=tts.id,
                                event_type="workflow.dispatch_ready",
                                idempotency_key=(
                                    f"translation-tts-recover:{project_id}:"
                                    f"{workflow.state_version}"
                                ),
                                payload={"product": PRODUCT, "recovered_tts": True},
                                status="pending",
                            )
                        )
                else:
                    # TTS 已完成的历史项目同样必须解除 render 门并投递；此前
                    # 这里直接 return，造成 24/N 后 video_render 永久 queued。
                    render.manual_gate = False
                    project.status = "render_queued"
                    workflow.state = "running"
                    workflow.state_version += 1
                    session.add(
                        WorkflowOutbox(
                            id=_new_id("obx"),
                            workflow_id=workflow.id,
                            workflow_node_id=render.id,
                            event_type="workflow.dispatch_ready",
                            idempotency_key=(
                                f"translation-render-recover:{project_id}:"
                                f"{workflow.state_version}"
                            ),
                            payload={"product": PRODUCT, "recovered_render": True},
                            status="pending",
                        )
                    )
                return ApiResponse(
                    code="VIDEO_TRANSLATION_RENDER_QUEUED",
                    message="Translation TTS is queued before render",
                    data=TranslationRenderData(
                        workflow_id=workflow.id, status=project.status
                    ),
                    request_id=request_id,
                )
            if tts.state == "failed":
                # “重新生成”从失败的 TTS 节点恢复，不重新翻译也不删除用户已编辑台词。
                # 旧的失败 attempt 保留审计记录，Orchestrator 会创建新的 attempt。
                tts.state = "queued"
            elif tts.state not in {"queued", "running", "completed"}:
                raise ApiError(
                    "TRANSLATION_TTS_INCOMPLETE",
                    "Translation voices are not ready",
                    409,
                )
            render.state = "queued"
            publish.state = "queued"
            # 此操作只释放 TTS。video_render 仍受门控，必须等 TTS 的成功回调
            # 解除，避免“render_queued 但 0/N 段配音”的伪进度。
            tts.manual_gate = False
            render.manual_gate = True
            project.current_stage = "generate"
            project.status = "queued"
            workflow.state = "queued"
            workflow.state_version += 1
            segments = session.scalars(
                select(VideoTranslationSegment)
                .where(VideoTranslationSegment.project_id == project_id)
                .order_by(VideoTranslationSegment.segment_index)
            ).all()
            session.add(
                WorkflowOutbox(
                    id=_new_id("obx"),
                    workflow_id=workflow.id,
                    workflow_node_id=tts.id,
                    event_type="workflow.dispatch_ready",
                    idempotency_key=(
                        f"translation-render:{project_id}:{workflow.state_version}"
                    ),
                    payload={
                        "product": PRODUCT,
                        "state": "queued",
                        # Render 必须以项目的单一原视频为连续画面时间轴；segments
                        # 只描述字幕/配音时序，绝不能再被解释为待拼接的视频片段。
                        "render_mode": "video_translation",
                        "translation_audio_mode": setting.original_sound_mode,
                        "translation_settings": setting.model_dump(),
                        "segments": [
                            {
                                "id": x.id,
                                "start_ms": x.start_ms,
                                "end_ms": x.end_ms,
                                "source_text": x.source_text,
                                "translated_text": x.translated_text,
                                "voice_id": x.voice_id,
                                "speed": x.speed,
                                "volume": x.volume,
                                "tts_duration_ms": x.tts_duration_ms,
                                "timing_fit_status": x.timing_fit_status,
                                "timing_overflow_ms": x.timing_overflow_ms,
                                "fitted_speed": x.fitted_speed,
                                "allowed_duration_ms": x.end_ms - x.start_ms,
                                "timing_tolerance_ms": TTS_TIMING_TOLERANCE_MS,
                            }
                            for x in segments
                        ],
                    },
                    status="pending",
                )
            )
            data = TranslationRenderData(workflow_id=workflow.id, status=project.status)
    return ApiResponse(
        code="VIDEO_TRANSLATION_RENDER_QUEUED",
        message="Video render queued",
        data=data,
        request_id=request_id,
    )


@router.get(
    "/projects/{project_id}/video-translation/result",
    response_model=ApiResponse[TranslationResultData],
)
def translation_result(
    project_id: str,
    request: Request,
    token: Annotated[str, Depends(bearer_token)],
    auth: Annotated[AuthService, Depends(get_auth_service)],
    request_id: Annotated[str, Depends(get_request_id)],
):
    user = auth.resolve_user(token)
    with Session(request.app.state.database_engine) as session:
        project = _owned(session, user.id, project_id)
        if project.status != "completed" or project.current_stage != "export":
            raise ApiError(
                "PROJECT_RESULT_NOT_COMPLETED", "Translation result is not ready", 409
            )
        artifacts = list_registered_artifacts(session, project=project)
        data = TranslationResultData(
            project_id=project.id,
            artifacts=[
                TranslationResultArtifact(id=x.id, kind=x.kind, cdn_url=x.cdn_url)
                for x in artifacts
            ],
        )
    return ApiResponse(
        code="VIDEO_TRANSLATION_RESULT_RETRIEVED",
        message="Translation result retrieved",
        data=data,
        request_id=request_id,
    )
