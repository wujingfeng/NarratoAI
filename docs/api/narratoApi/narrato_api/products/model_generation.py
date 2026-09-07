"""通用模型、玩法、供应商、计费与任务持久化模型。

配置采用关系表而非能力/价格 JSON；供应商的字段和状态差异由代码中的
Provider adapter 处理。当前只实现火山方舟，表结构允许后续增加其他 provider。
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from narrato_api.database import Base


# PostgreSQL 生产库使用 VARCHAR[]；SQLite 测试环境使用等价 JSON 数组。
StringArray = ARRAY(String(32)).with_variant(JSON, "sqlite")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Model(Base):
    """通用模型目录；连接供应商的机密信息只存在 Provider 明细行。"""

    __tablename__ = "models"
    __table_args__ = (
        CheckConstraint("model_type IN ('image', 'video', 'llm')", name="ck_models_model_type"),
        CheckConstraint("sort_order >= 0", name="ck_models_sort_order"),
        Index(
            "uq_models_default_by_type",
            "model_type",
            unique=True,
            postgresql_where=text("is_default"),
            sqlite_where=text("is_default = 1"),
        ),
        {"comment": "通用 AI 模型基础表，支持 LLM、图片与视频模型。"},
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, comment="模型稳定标识。")
    display_name: Mapped[str] = mapped_column(String(128), nullable=False, comment="用户侧模型名称。")
    model_type: Mapped[str] = mapped_column(String(16), nullable=False, comment="模型类型：llm、image 或 video。")
    description: Mapped[str | None] = mapped_column(String(512), comment="模型介绍。")
    cover_url: Mapped[str | None] = mapped_column(String(2048), comment="模型封面 URL。")
    category: Mapped[str] = mapped_column(String(64), nullable=False, default="all", comment="运营分类。")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="排序值，数值越小越靠前。")
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, comment="是否对用户可用。")
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, comment="该模型类型的默认模型。")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, comment="创建时间 UTC。")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now, comment="更新时间 UTC。")


class ModelPlayMode(Base):
    """同一模型的一个可提交玩法，例如 text_to_video 或 reference_to_video。"""

    __tablename__ = "model_play_modes"
    __table_args__ = (
        CheckConstraint("sort_order >= 0", name="ck_model_play_modes_sort_order"),
        UniqueConstraint("model_id", "code", name="uq_model_play_modes_model_code"),
        Index("ix_model_play_modes_model_enabled", "model_id", "is_enabled"),
        {"comment": "模型玩法表；每条玩法拥有独立能力、默认积分和当前供应商。"},
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, comment="玩法稳定标识。")
    model_id: Mapped[str] = mapped_column(String(64), ForeignKey("models.id", ondelete="RESTRICT"), nullable=False, comment="所属模型。")
    code: Mapped[str] = mapped_column(String(64), nullable=False, comment="玩法代码，例如 text_to_video。")
    display_name: Mapped[str] = mapped_column(String(128), nullable=False, comment="玩法展示名称。")
    description: Mapped[str | None] = mapped_column(String(512), comment="玩法说明。")
    default_credits: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="提交时的最低预扣积分；Token 实际用量结算前的保底值。")
    active_provider_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("model_play_mode_providers.id", ondelete="RESTRICT", use_alter=True, name="fk_model_play_modes_active_provider"), nullable=True, comment="当前生效的玩法供应商明细 ID。")
    supports_generate_audio: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, comment="是否支持生成同步音频，仅视频玩法使用。")
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, comment="玩法是否可选。")
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, comment="该模型的默认玩法。")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="玩法排序值。")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, comment="创建时间 UTC。")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now, comment="更新时间 UTC。")


class ModelPlayModeRule(Base):
    """输入约束和输出选项统一的规则行；每个输出类型用数组保存可选值。"""

    __tablename__ = "model_play_mode_rules"
    __table_args__ = (
        CheckConstraint("rule_kind IN ('input_constraint', 'output_option')", name="ck_model_play_mode_rules_kind"),
        CheckConstraint("input_type IS NULL OR input_type IN ('text', 'image', 'video', 'audio')", name="ck_model_play_mode_rules_input_type"),
        CheckConstraint("output_option_type IS NULL OR output_option_type IN ('resolution', 'ratio', 'duration')", name="ck_model_play_mode_rules_output_type"),
        CheckConstraint("max_count IS NULL OR max_count >= 0", name="ck_model_play_mode_rules_max_count"),
        CheckConstraint("max_file_size_bytes IS NULL OR max_file_size_bytes >= 0", name="ck_model_play_mode_rules_max_file_size"),
        CheckConstraint("max_duration_seconds IS NULL OR max_duration_seconds >= 0", name="ck_model_play_mode_rules_max_duration"),
        CheckConstraint("max_text_units IS NULL OR max_text_units >= 0", name="ck_model_play_mode_rules_max_text"),
        CheckConstraint("sort_order >= 0", name="ck_model_play_mode_rules_sort_order"),
        Index("ix_model_play_mode_rules_mode_kind", "play_mode_id", "rule_kind", "sort_order"),
        {"comment": "玩法规则表：输入限制逐行配置；分辨率、比例、时长的可选值以数组保存。"},
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, comment="规则稳定标识。")
    play_mode_id: Mapped[str] = mapped_column(String(64), ForeignKey("model_play_modes.id", ondelete="CASCADE"), nullable=False, comment="所属玩法。")
    rule_kind: Mapped[str] = mapped_column(String(32), nullable=False, comment="规则类别：input_constraint 或 output_option。")
    input_type: Mapped[str | None] = mapped_column(String(16), comment="输入类型：text/image/video/audio。")
    is_supported: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, comment="该输入类型或输出选项是否支持。")
    is_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, comment="该输入类型是否必填。")
    max_count: Mapped[int | None] = mapped_column(Integer, comment="该输入类型允许的最大文件数量。")
    max_file_size_bytes: Mapped[int | None] = mapped_column(BigInteger, comment="单文件最大字节数。")
    max_duration_seconds: Mapped[int | None] = mapped_column(Integer, comment="单视频或音频最大时长（秒）。")
    max_text_units: Mapped[int | None] = mapped_column(Integer, comment="中文字符数与英文单词数之和的最大值。")
    supports_mention: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, comment="是否允许 @ 引用本次上传素材。")
    output_option_type: Mapped[str | None] = mapped_column(String(32), comment="输出选项类型：resolution/ratio/duration。")
    resolution: Mapped[list[str] | None] = mapped_column(StringArray, comment="输出分辨率候选数组，例如 {480P,720P,1080P,4K}。")
    ratio: Mapped[list[str] | None] = mapped_column(StringArray, comment="输出比例候选数组，adaptive 表示自适应。")
    duration_seconds: Mapped[list[str] | None] = mapped_column(StringArray, comment="输出时长候选数组（秒字符串）；adaptive 表示自适应时长。")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="选项倒序排序值，数值越大越靠前。")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, comment="创建时间 UTC。")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now, comment="更新时间 UTC。")


class ModelPlayModeProvider(Base):
    """玩法可用供应商，火山方舟以 provider_code=volcengine 保存。"""

    __tablename__ = "model_play_mode_providers"
    __table_args__ = (
        CheckConstraint("status_query_method IN ('GET', 'POST')", name="ck_model_play_mode_providers_query_method"),
        UniqueConstraint("play_mode_id", "provider_code", "provider_model_id", name="uq_model_play_mode_providers_provider_model"),
        Index("ix_model_play_mode_providers_mode_enabled", "play_mode_id", "is_enabled"),
        {"comment": "玩法供应商明细；请求字段和状态映射由代码 Adapter 管理。"},
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, comment="玩法供应商稳定标识。")
    play_mode_id: Mapped[str] = mapped_column(String(64), ForeignKey("model_play_modes.id", ondelete="CASCADE"), nullable=False, comment="所属玩法。")
    provider_code: Mapped[str] = mapped_column(String(64), nullable=False, comment="供应商代码，例如 volcengine。")
    request_profile: Mapped[str] = mapped_column(String(64), nullable=False, default="default", comment="Provider 请求协议 Profile；Adapter 由 provider_code 选择。")
    provider_model_id: Mapped[str] = mapped_column(String(128), nullable=False, comment="供应商模型或 Endpoint ID。")
    submit_url: Mapped[str] = mapped_column(String(2048), nullable=False, comment="供应商提交 URL。")
    status_query_url: Mapped[str | None] = mapped_column(String(2048), comment="任务状态查询 URL，可使用 {task_id} 模板。")
    status_query_method: Mapped[str] = mapped_column(String(8), nullable=False, default="GET", comment="状态查询方法：GET 或 POST。")
    api_key: Mapped[str] = mapped_column(Text, nullable=False, comment="供应商 API Key，按当前要求明文保存。")
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, comment="供应商是否可用。")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, comment="创建时间 UTC。")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now, comment="更新时间 UTC。")


class ModelPlayModeProviderPrice(Base):
    """面向用户的玩法积分规则；提交时冻结到任务收费明细。"""

    __tablename__ = "model_play_mode_provider_prices"
    __table_args__ = (
        CheckConstraint("billing_unit IN ('second', 'token', 'usage')", name="ck_model_play_mode_provider_prices_unit"),
        CheckConstraint("per_million_input_credits IS NULL OR per_million_input_credits >= 0", name="ck_model_play_mode_provider_prices_input_credits"),
        CheckConstraint("per_million_output_credits IS NULL OR per_million_output_credits >= 0", name="ck_model_play_mode_provider_prices_output_credits"),
        CheckConstraint("per_usage_credits IS NULL OR per_usage_credits >= 0", name="ck_model_play_mode_provider_prices_usage_credits"),
        CheckConstraint("per_second_credits IS NULL OR per_second_credits >= 0", name="ck_model_play_mode_provider_prices_second_credits"),
        CheckConstraint("billing_unit != 'second' OR per_second_credits IS NOT NULL", name="ck_model_play_mode_provider_prices_second_value"),
        CheckConstraint("billing_unit != 'usage' OR per_usage_credits IS NOT NULL", name="ck_model_play_mode_provider_prices_usage_value"),
        CheckConstraint("billing_unit != 'token' OR per_million_input_credits IS NOT NULL OR per_million_output_credits IS NOT NULL", name="ck_model_play_mode_provider_prices_token_value"),
        UniqueConstraint("provider_id", "resolution", "billing_unit", name="uq_model_play_mode_provider_prices_key"),
        Index("ix_model_play_mode_provider_prices_provider", "provider_id", "is_enabled"),
        {"comment": "用户积分价格配置表；按分辨率和结算单位配置，不存储金额或汇率。"},
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, comment="价格规则稳定标识。")
    provider_id: Mapped[str] = mapped_column(String(64), ForeignKey("model_play_mode_providers.id", ondelete="CASCADE"), nullable=False, comment="所属玩法供应商。")
    resolution: Mapped[str | None] = mapped_column(String(32), nullable=True, comment="适用分辨率；NULL 表示所有分辨率。")
    billing_unit: Mapped[str] = mapped_column(String(40), nullable=False, comment="计费单位。")
    per_million_input_credits: Mapped[int | None] = mapped_column(Integer, comment="每百万输入 Token 扣除的积分，仅 token 规则使用。")
    per_million_output_credits: Mapped[int | None] = mapped_column(Integer, comment="每百万输出 Token 扣除的积分，仅 token 规则使用。")
    per_usage_credits: Mapped[int | None] = mapped_column(Integer, comment="每次调用或每个实际图片输出扣除的积分，仅 usage 规则使用。")
    per_second_credits: Mapped[int | None] = mapped_column(Integer, comment="每秒实际视频输出扣除的积分，仅 second 规则使用。")
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, comment="该价格规则是否生效。")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, comment="创建时间 UTC。")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now, comment="更新时间 UTC。")


class ModelTask(Base):
    """统一模型任务；不保存 input/price snapshot JSON。"""

    __tablename__ = "model_tasks"
    __table_args__ = (
        CheckConstraint("task_type IN ('llm', 'image', 'video')", name="ck_model_tasks_type"),
        CheckConstraint("status IN ('submitting', 'queued', 'processing', 'finalizing', 'succeeded', 'succeeded_with_partial_output', 'failed')", name="ck_model_tasks_status"),
        CheckConstraint("attempt_count > 0", name="ck_model_tasks_attempt_count"),
        UniqueConstraint("user_id", "idempotency_key", name="uq_model_tasks_user_idempotency"),
        Index("ix_model_tasks_user_created", "user_id", "created_at"),
        Index("ix_model_tasks_project", "project_id"),
        Index("ix_model_tasks_provider_task", "provider_task_id"),
        Index("ix_model_tasks_poll_due", "status", "next_poll_at"),
        {"comment": "统一 LLM、图片、视频生成任务及结算事实。"},
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, comment="任务稳定标识。")
    project_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("projects.id", ondelete="RESTRICT"), nullable=True, comment="关联项目；LLM API 任务可为空。")
    user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, comment="任务创建用户。")
    model_id: Mapped[str] = mapped_column(String(64), ForeignKey("models.id", ondelete="RESTRICT"), nullable=False, comment="使用的模型。")
    play_mode_id: Mapped[str] = mapped_column(String(64), ForeignKey("model_play_modes.id", ondelete="RESTRICT"), nullable=False, comment="使用的模型玩法。")
    provider_id: Mapped[str] = mapped_column(String(64), ForeignKey("model_play_mode_providers.id", ondelete="RESTRICT"), nullable=False, comment="提交时锁定的供应商配置。")
    task_type: Mapped[str] = mapped_column(String(16), nullable=False, comment="任务类型：llm/image/video。")
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="submitting", comment="任务生命周期状态。")
    idempotency_key: Mapped[str] = mapped_column(String(256), nullable=False, comment="用户维度幂等键。")
    provider_task_id: Mapped[str | None] = mapped_column(String(256), unique=True, comment="供应商远端任务 ID。")
    prompt: Mapped[str | None] = mapped_column(Text, comment="提交的文本提示词。")
    resolution: Mapped[str | None] = mapped_column(String(32), comment="本次锁定的输出分辨率。")
    ratio: Mapped[str | None] = mapped_column(String(16), comment="本次锁定的输出比例。")
    requested_duration_seconds: Mapped[int | None] = mapped_column(Integer, comment="请求的视频时长（秒）。")
    audio_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, comment="是否请求生成同步音频。")
    provider_options: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict, comment="已校验并冻结的 Provider 专有请求参数。")
    provider_request: Mapped[dict | None] = mapped_column(JSON, comment="脱敏后的供应商请求审计数据。")
    provider_response: Mapped[dict | None] = mapped_column(JSON, comment="供应商最后响应审计数据。")
    default_credits_charged: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="提交时预扣积分。")
    final_credits: Mapped[int | None] = mapped_column(Integer, comment="按实际用量最终应扣积分。")
    input_token: Mapped[int | None] = mapped_column(Integer, comment="供应商返回的实际输入 Token。")
    output_token: Mapped[int | None] = mapped_column(Integer, comment="供应商返回的实际输出 Token。")
    actual_output_duration_seconds: Mapped[float | None] = mapped_column(comment="实际输出视频时长（秒）。")
    actual_output_image_count: Mapped[int | None] = mapped_column(Integer, comment="实际成功输出图片张数。")
    settlement_status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending", comment="结算状态：pending/settled/refunded/billing_failed。")
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1, comment="提交尝试次数。")
    error_code: Mapped[str | None] = mapped_column(String(64), comment="标准错误码。")
    error_message: Mapped[str | None] = mapped_column(String(512), comment="用户可读错误信息。")
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), comment="供应商提交成功时间 UTC。")
    next_poll_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), comment="下次业务 Worker 处理时间 UTC。")
    poll_lease_token: Mapped[str | None] = mapped_column(String(64), comment="Worker 租约令牌。")
    poll_lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), comment="Worker 租约到期时间 UTC。")
    poll_error_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="连续轮询失败次数。")
    last_polled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), comment="最后处理时间 UTC。")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, comment="创建时间 UTC。")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now, comment="更新时间 UTC。")


class ModelTaskAsset(Base):
    __tablename__ = "model_task_assets"
    __table_args__ = (
        CheckConstraint("input_type IN ('text', 'image', 'video', 'audio')", name="ck_model_task_assets_type"),
        CheckConstraint("sort_order >= 0", name="ck_model_task_assets_sort_order"),
        UniqueConstraint("task_id", "asset_id", name="uq_model_task_assets_task_asset"),
        Index("ix_model_task_assets_task", "task_id", "sort_order"),
        {"comment": "任务引用的本次上传素材与 @ 引用标记。"},
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True, comment="任务素材关联主键。")
    task_id: Mapped[str] = mapped_column(String(64), ForeignKey("model_tasks.id", ondelete="CASCADE"), nullable=False, comment="所属任务。")
    asset_id: Mapped[str] = mapped_column(String(64), ForeignKey("assets.id", ondelete="RESTRICT"), nullable=False, comment="引用的项目素材。")
    input_type: Mapped[str] = mapped_column(String(16), nullable=False, comment="素材输入类型。")
    is_mentioned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, comment="是否被最终提示词明确指代。")
    provider_role: Mapped[str | None] = mapped_column(String(64), comment="提交给供应商的媒体角色，例如 reference_image。")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="同类素材提交顺序；用于冻结 @imageN/@videoN/@audioN 编号。")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, comment="创建时间 UTC。")


class ModelTaskOutput(Base):
    __tablename__ = "model_task_outputs"
    __table_args__ = (
        CheckConstraint("output_type IN ('text', 'image', 'video')", name="ck_model_task_outputs_type"),
        CheckConstraint("sort_order >= 0", name="ck_model_task_outputs_sort_order"),
        UniqueConstraint("task_id", "sort_order", name="uq_model_task_outputs_task_sort"),
        Index("ix_model_task_outputs_task", "task_id", "sort_order"),
        {"comment": "供应商成功产物转存 OSS 后的逐项输出记录。"},
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True, comment="任务输出主键。")
    task_id: Mapped[str] = mapped_column(String(64), ForeignKey("model_tasks.id", ondelete="CASCADE"), nullable=False, comment="所属任务。")
    output_type: Mapped[str] = mapped_column(String(16), nullable=False, comment="输出类型：text/image/video。")
    provider_url: Mapped[str | None] = mapped_column(String(2048), comment="供应商短期输出 URL，仅审计使用。")
    oss_bucket: Mapped[str | None] = mapped_column(String(255), comment="转存 OSS Bucket。")
    oss_object_key: Mapped[str | None] = mapped_column(String(1024), comment="转存 OSS 对象键。")
    cdn_url: Mapped[str | None] = mapped_column(String(2048), comment="长期可访问 CDN URL。")
    content_type: Mapped[str | None] = mapped_column(String(255), comment="输出内容类型。")
    size_bytes: Mapped[int | None] = mapped_column(BigInteger, comment="输出大小。")
    duration_seconds: Mapped[float | None] = mapped_column(comment="输出视频真实时长。")
    core_task_id: Mapped[str | None] = mapped_column(String(128), comment="Core 视频信息任务 ID。")
    text_content: Mapped[str | None] = mapped_column(Text, comment="LLM 文本输出。")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="输出顺序。")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, comment="创建时间 UTC。")


class ModelTaskCharge(Base):
    __tablename__ = "model_task_charges"
    __table_args__ = (
        CheckConstraint("billing_unit IN ('second', 'token', 'usage')", name="ck_model_task_charges_unit"),
        CheckConstraint("per_million_input_credits IS NULL OR per_million_input_credits >= 0", name="ck_model_task_charges_input_credits"),
        CheckConstraint("per_million_output_credits IS NULL OR per_million_output_credits >= 0", name="ck_model_task_charges_output_credits"),
        CheckConstraint("per_usage_credits IS NULL OR per_usage_credits >= 0", name="ck_model_task_charges_usage_credits"),
        CheckConstraint("per_second_credits IS NULL OR per_second_credits >= 0", name="ck_model_task_charges_second_credits"),
        CheckConstraint("billing_unit != 'second' OR per_second_credits IS NOT NULL", name="ck_model_task_charges_second_value"),
        CheckConstraint("billing_unit != 'usage' OR per_usage_credits IS NOT NULL", name="ck_model_task_charges_usage_value"),
        CheckConstraint("billing_unit != 'token' OR per_million_input_credits IS NOT NULL OR per_million_output_credits IS NOT NULL", name="ck_model_task_charges_token_value"),
        CheckConstraint("quantity >= 0", name="ck_model_task_charges_quantity"),
        UniqueConstraint("task_id", "billing_unit", name="uq_model_task_charges_task_unit"),
        {"comment": "任务提交时冻结的积分单价及结算后的实际数量。"},
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True, comment="任务收费明细主键。")
    task_id: Mapped[str] = mapped_column(String(64), ForeignKey("model_tasks.id", ondelete="CASCADE"), nullable=False, comment="所属任务。")
    billing_unit: Mapped[str] = mapped_column(String(40), nullable=False, comment="结算单位。")
    resolution: Mapped[str | None] = mapped_column(String(32), comment="提交时锁定的分辨率。")
    per_million_input_credits: Mapped[int | None] = mapped_column(Integer, comment="提交时锁定的每百万输入 Token 积分单价。")
    per_million_output_credits: Mapped[int | None] = mapped_column(Integer, comment="提交时锁定的每百万输出 Token 积分单价。")
    per_usage_credits: Mapped[int | None] = mapped_column(Integer, comment="提交时锁定的按次积分单价。")
    per_second_credits: Mapped[int | None] = mapped_column(Integer, comment="提交时锁定的每秒积分单价。")
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False, default=0, comment="最终实际计费数量。")
    credits: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="该收费明细计算出的积分。")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, comment="创建时间 UTC。")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now, comment="更新时间 UTC。")
