"""Normalize generic AI model configuration and rename AI-video tasks.

Revision ID: 0031_normalize_model_generation
Revises: 0030_ai_video_provider_polling

The previous AI-video implementation placed provider connection details,
capabilities, prices and input snapshots in JSON columns.  This revision keeps
only provider request/response audit JSON and moves all operable configuration
into normalized tables.  Existing rows are migrated to one ``legacy`` play
mode/provider per model before the obsolete columns are removed.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0031_normalize_model_generation"
down_revision: str | None = "0030_ai_video_provider_polling"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _id(prefix: str, *parts: object) -> str:
    digest = hashlib.sha256("|".join(map(str, parts)).encode("utf-8")).hexdigest()[:32]
    return f"{prefix}_{digest}"


def _dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            data = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return data if isinstance(data, dict) else {}
    return {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _create_configuration_tables() -> None:
    op.create_table(
        "model_play_modes",
        sa.Column("id", sa.String(64), primary_key=True, comment="玩法稳定标识。"),
        sa.Column("model_id", sa.String(64), sa.ForeignKey("models.id", ondelete="RESTRICT"), nullable=False, comment="所属模型。"),
        sa.Column("code", sa.String(64), nullable=False, comment="玩法代码，例如 text_to_video。"),
        sa.Column("display_name", sa.String(128), nullable=False, comment="玩法展示名称。"),
        sa.Column("description", sa.String(512), comment="玩法说明。"),
        sa.Column("default_credits", sa.Integer(), nullable=False, server_default="0", comment="提交时最低预扣积分；Token 结算前的保底值。"),
        sa.Column("active_provider_id", sa.String(64), nullable=True, comment="当前生效供应商明细 ID。"),
        sa.Column("supports_generate_audio", sa.Boolean(), nullable=False, server_default=sa.false(), comment="是否支持生成同步音频。"),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.true(), comment="玩法是否可用。"),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false(), comment="该模型默认玩法。"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0", comment="玩法排序值。"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, comment="创建时间 UTC。"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, comment="更新时间 UTC。"),
        sa.CheckConstraint("sort_order >= 0", name="ck_model_play_modes_sort_order"),
        sa.UniqueConstraint("model_id", "code", name="uq_model_play_modes_model_code"),
        comment="模型玩法表；每条玩法拥有独立能力、默认积分和当前供应商。",
    )
    op.create_index("ix_model_play_modes_model_enabled", "model_play_modes", ["model_id", "is_enabled"])
    op.create_table(
        "model_play_mode_rules",
        sa.Column("id", sa.String(64), primary_key=True, comment="规则稳定标识。"),
        sa.Column("play_mode_id", sa.String(64), sa.ForeignKey("model_play_modes.id", ondelete="CASCADE"), nullable=False, comment="所属玩法。"),
        sa.Column("rule_kind", sa.String(32), nullable=False, comment="规则类别。"),
        sa.Column("input_type", sa.String(16), comment="输入类型。"),
        sa.Column("is_supported", sa.Boolean(), nullable=False, server_default=sa.true(), comment="是否支持。"),
        sa.Column("is_required", sa.Boolean(), nullable=False, server_default=sa.false(), comment="是否必填。"),
        sa.Column("max_count", sa.Integer(), comment="最大文件数量。"),
        sa.Column("max_file_size_bytes", sa.BigInteger(), comment="单文件最大大小。"),
        sa.Column("max_duration_seconds", sa.Integer(), comment="单视频或音频最大时长。"),
        sa.Column("max_text_units", sa.Integer(), comment="中文字符加英文单词的最大输入量。"),
        sa.Column("supports_mention", sa.Boolean(), nullable=False, server_default=sa.false(), comment="是否支持 @ 本次素材。"),
        sa.Column("output_option_type", sa.String(32), comment="输出选项类型。"),
        sa.Column("resolution", sa.String(32), comment="输出分辨率。"),
        sa.Column("ratio", sa.String(16), comment="输出比例。"),
        sa.Column("duration_seconds", sa.Integer(), comment="固定或候选时长。"),
        sa.Column("min_duration_seconds", sa.Integer(), comment="时长范围最小值。"),
        sa.Column("max_duration_seconds_output", sa.Integer(), comment="时长范围最大值。"),
        sa.Column("is_adaptive", sa.Boolean(), nullable=False, server_default=sa.false(), comment="是否自适应选项。"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0", comment="倒序展示排序值。"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, comment="创建时间 UTC。"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, comment="更新时间 UTC。"),
        sa.CheckConstraint("rule_kind IN ('input_constraint', 'output_option')", name="ck_model_play_mode_rules_kind"),
        sa.CheckConstraint("input_type IS NULL OR input_type IN ('text', 'image', 'video', 'audio')", name="ck_model_play_mode_rules_input_type"),
        sa.CheckConstraint("output_option_type IS NULL OR output_option_type IN ('resolution', 'ratio', 'duration')", name="ck_model_play_mode_rules_output_type"),
        sa.CheckConstraint("max_count IS NULL OR max_count >= 0", name="ck_model_play_mode_rules_max_count"),
        sa.CheckConstraint("max_file_size_bytes IS NULL OR max_file_size_bytes >= 0", name="ck_model_play_mode_rules_max_file_size"),
        sa.CheckConstraint("max_duration_seconds IS NULL OR max_duration_seconds >= 0", name="ck_model_play_mode_rules_max_duration"),
        sa.CheckConstraint("max_text_units IS NULL OR max_text_units >= 0", name="ck_model_play_mode_rules_max_text"),
        sa.CheckConstraint("duration_seconds IS NULL OR duration_seconds > 0", name="ck_model_play_mode_rules_duration"),
        sa.CheckConstraint("min_duration_seconds IS NULL OR min_duration_seconds > 0", name="ck_model_play_mode_rules_min_duration"),
        sa.CheckConstraint("max_duration_seconds_output IS NULL OR max_duration_seconds_output > 0", name="ck_model_play_mode_rules_max_duration_output"),
        sa.CheckConstraint("sort_order >= 0", name="ck_model_play_mode_rules_sort_order"),
        comment="玩法规则表：输入限制与输出选项逐行配置。",
    )
    op.create_index("ix_model_play_mode_rules_mode_kind", "model_play_mode_rules", ["play_mode_id", "rule_kind", "sort_order"])
    op.create_table(
        "model_play_mode_providers",
        sa.Column("id", sa.String(64), primary_key=True, comment="玩法供应商稳定标识。"),
        sa.Column("play_mode_id", sa.String(64), sa.ForeignKey("model_play_modes.id", ondelete="CASCADE"), nullable=False, comment="所属玩法。"),
        sa.Column("provider_code", sa.String(64), nullable=False, comment="供应商代码。"),
        sa.Column("provider_model_id", sa.String(128), nullable=False, comment="供应商模型或 Endpoint ID。"),
        sa.Column("submit_url", sa.String(2048), nullable=False, comment="供应商提交 URL。"),
        sa.Column("status_query_url", sa.String(2048), comment="状态查询 URL，可含 {task_id}。"),
        sa.Column("status_query_method", sa.String(8), nullable=False, server_default="GET", comment="状态查询方法。"),
        sa.Column("api_key", sa.Text(), nullable=False, comment="供应商 API Key，按当前要求明文保存。"),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.true(), comment="供应商是否可用。"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, comment="创建时间 UTC。"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, comment="更新时间 UTC。"),
        sa.CheckConstraint("status_query_method IN ('GET', 'POST')", name="ck_model_play_mode_providers_query_method"),
        sa.UniqueConstraint("play_mode_id", "provider_code", "provider_model_id", name="uq_model_play_mode_providers_provider_model"),
        comment="玩法供应商明细；字段和状态差异由代码 Adapter 适配。",
    )
    op.create_index("ix_model_play_mode_providers_mode_enabled", "model_play_mode_providers", ["play_mode_id", "is_enabled"])
    # ``active_provider_id`` closes the one-to-many relation after both sides
    # exist. It remains nullable so an operator can disable a mode safely.
    with op.batch_alter_table("model_play_modes") as batch:
        batch.create_foreign_key(
            "fk_model_play_modes_active_provider",
            "model_play_mode_providers",
            ["active_provider_id"],
            ["id"],
            ondelete="RESTRICT",
        )
    op.create_table(
        "model_play_mode_provider_prices",
        sa.Column("id", sa.String(64), primary_key=True, comment="价格规则稳定标识。"),
        sa.Column("provider_id", sa.String(64), sa.ForeignKey("model_play_mode_providers.id", ondelete="CASCADE"), nullable=False, comment="所属供应商。"),
        sa.Column("resolution", sa.String(32), nullable=True, comment="适用分辨率；NULL 表示全分辨率。"),
        sa.Column("billing_unit", sa.String(40), nullable=False, comment="计费单位。"),
        sa.Column("per_million_input_credits", sa.Integer(), nullable=True, comment="每百万输入 Token 扣除积分，仅 token 规则使用。"),
        sa.Column("per_million_output_credits", sa.Integer(), nullable=True, comment="每百万输出 Token 扣除积分，仅 token 规则使用。"),
        sa.Column("per_usage_credits", sa.Integer(), nullable=True, comment="每次调用或每个实际图片输出扣除积分，仅 usage 规则使用。"),
        sa.Column("per_second_credits", sa.Integer(), nullable=True, comment="每秒实际视频输出扣除积分，仅 second 规则使用。"),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.true(), comment="是否生效。"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, comment="创建时间 UTC。"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, comment="更新时间 UTC。"),
        sa.CheckConstraint("billing_unit IN ('second', 'token', 'usage')", name="ck_model_play_mode_provider_prices_unit"),
        sa.CheckConstraint("per_million_input_credits IS NULL OR per_million_input_credits >= 0", name="ck_model_play_mode_provider_prices_input_credits"),
        sa.CheckConstraint("per_million_output_credits IS NULL OR per_million_output_credits >= 0", name="ck_model_play_mode_provider_prices_output_credits"),
        sa.CheckConstraint("per_usage_credits IS NULL OR per_usage_credits >= 0", name="ck_model_play_mode_provider_prices_usage_credits"),
        sa.CheckConstraint("per_second_credits IS NULL OR per_second_credits >= 0", name="ck_model_play_mode_provider_prices_second_credits"),
        sa.CheckConstraint("billing_unit != 'second' OR per_second_credits IS NOT NULL", name="ck_model_play_mode_provider_prices_second_value"),
        sa.CheckConstraint("billing_unit != 'usage' OR per_usage_credits IS NOT NULL", name="ck_model_play_mode_provider_prices_usage_value"),
        sa.CheckConstraint("billing_unit != 'token' OR per_million_input_credits IS NOT NULL OR per_million_output_credits IS NOT NULL", name="ck_model_play_mode_provider_prices_token_value"),
        sa.UniqueConstraint("provider_id", "resolution", "billing_unit", name="uq_model_play_mode_provider_prices_key"),
        comment="用户积分价格配置表；按分辨率和结算单位配置，不存储金额或汇率。",
    )
    op.create_index("ix_model_play_mode_provider_prices_provider", "model_play_mode_provider_prices", ["provider_id", "is_enabled"])


def _migrate_legacy_models() -> dict[str, tuple[str, str]]:
    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT * FROM models")).mappings().all()
    mapping: dict[str, tuple[str, str]] = {}
    for row in rows:
        model_id = str(row["id"])
        mode_id = _id("mpm", model_id)
        provider_id = _id("mpp", model_id)
        caps = _dict(row.get("capabilities"))
        provider_cfg = _dict(row.get("provider_config"))
        prices = _dict(row.get("price_config"))
        default_credits = prices.get("fixed_credits", prices.get("minimum_credits", 0))
        if not isinstance(default_credits, int) or default_credits < 0:
            default_credits = 0
        bind.execute(sa.text("""
            INSERT INTO model_play_modes (id, model_id, code, display_name, default_credits, supports_generate_audio, is_enabled, is_default, sort_order, created_at, updated_at)
            VALUES (:id, :model_id, 'legacy', :display_name, :default_credits, :audio, :is_enabled, true, :sort_order, :created_at, :updated_at)
        """), {"id": mode_id, "model_id": model_id, "display_name": str(row.get("display_name") or model_id), "default_credits": default_credits,
              "audio": bool(caps.get("audio_switch")), "is_enabled": bool(row.get("is_enabled", True)), "sort_order": int(row.get("sort_order") or 0),
              "created_at": row["created_at"], "updated_at": row["updated_at"]})
        submit_url = provider_cfg.get("submit_url") if isinstance(provider_cfg.get("submit_url"), str) else ""
        status_url = provider_cfg.get("status_query_url_template") if isinstance(provider_cfg.get("status_query_url_template"), str) else provider_cfg.get("status_query_url")
        bind.execute(sa.text("""
            INSERT INTO model_play_mode_providers (id, play_mode_id, provider_code, provider_model_id, submit_url, status_query_url, status_query_method, api_key, is_enabled, created_at, updated_at)
            VALUES (:id, :play_mode_id, :provider_code, :provider_model_id, :submit_url, :status_query_url, 'GET', :api_key, :is_enabled, :created_at, :updated_at)
        """), {"id": provider_id, "play_mode_id": mode_id, "provider_code": str(row.get("provider_code") or "legacy"),
              "provider_model_id": str(row.get("provider_model_id") or model_id), "submit_url": submit_url,
              "status_query_url": status_url if isinstance(status_url, str) else None,
              "api_key": str(provider_cfg.get("api_key") or ""), "is_enabled": bool(row.get("is_enabled", True)),
              "created_at": row["created_at"], "updated_at": row["updated_at"]})
        bind.execute(sa.text("UPDATE model_play_modes SET active_provider_id=:provider_id WHERE id=:mode_id"), {"provider_id": provider_id, "mode_id": mode_id})
        mapping[model_id] = (mode_id, provider_id)
        for input_type, old_name in (("image", "image_upload"), ("video", "video_upload"), ("audio", "audio_upload")):
            item = _dict(caps.get(old_name))
            bind.execute(sa.text("""
                INSERT INTO model_play_mode_rules (id, play_mode_id, rule_kind, input_type, is_supported, is_required, max_count, supports_mention, sort_order, created_at, updated_at)
                VALUES (:id, :mode_id, 'input_constraint', :input_type, :supported, false, :max_count, :mention, 0, :created_at, :updated_at)
            """), {"id": _id("mpr", mode_id, input_type), "mode_id": mode_id, "input_type": input_type,
                  "supported": bool(item.get("enabled")), "max_count": int(item.get("max_count") or 0),
                  "mention": input_type == "image" and bool(caps.get("multi_subject_reference")),
                  "created_at": row["created_at"], "updated_at": row["updated_at"]})
        bind.execute(sa.text("""
            INSERT INTO model_play_mode_rules (id, play_mode_id, rule_kind, input_type, is_supported, is_required, max_text_units, supports_mention, sort_order, created_at, updated_at)
            VALUES (:id, :mode_id, 'input_constraint', 'text', true, true, 8000, false, 0, :created_at, :updated_at)
        """), {"id": _id("mpr", mode_id, "text"), "mode_id": mode_id, "created_at": row["created_at"], "updated_at": row["updated_at"]})
        for index, value in enumerate(_list(caps.get("resolutions"))):
            bind.execute(sa.text("""
                INSERT INTO model_play_mode_rules (id, play_mode_id, rule_kind, is_supported, output_option_type, resolution, sort_order, created_at, updated_at)
                VALUES (:id, :mode_id, 'output_option', true, 'resolution', :value, :sort_order, :created_at, :updated_at)
            """), {"id": _id("mpr", mode_id, "resolution", value), "mode_id": mode_id, "value": str(value), "sort_order": len(_list(caps.get("resolutions"))) - index, "created_at": row["created_at"], "updated_at": row["updated_at"]})
        for index, value in enumerate(_list(caps.get("ratios"))):
            bind.execute(sa.text("""
                INSERT INTO model_play_mode_rules (id, play_mode_id, rule_kind, is_supported, output_option_type, ratio, is_adaptive, sort_order, created_at, updated_at)
                VALUES (:id, :mode_id, 'output_option', true, 'ratio', :value, :adaptive, :sort_order, :created_at, :updated_at)
            """), {"id": _id("mpr", mode_id, "ratio", value), "mode_id": mode_id, "value": str(value), "adaptive": str(value) == "adaptive", "sort_order": len(_list(caps.get("ratios"))) - index, "created_at": row["created_at"], "updated_at": row["updated_at"]})
        duration = _dict(caps.get("duration"))
        mode = duration.get("mode")
        if mode in {"fixed", "options"}:
            for index, value in enumerate(_list(duration.get("options"))):
                if isinstance(value, int) and value > 0:
                    bind.execute(sa.text("""
                        INSERT INTO model_play_mode_rules (id, play_mode_id, rule_kind, is_supported, output_option_type, duration_seconds, sort_order, created_at, updated_at)
                        VALUES (:id, :mode_id, 'output_option', true, 'duration', :value, :sort_order, :created_at, :updated_at)
                    """), {"id": _id("mpr", mode_id, "duration", value), "mode_id": mode_id, "value": value, "sort_order": len(_list(duration.get("options"))) - index, "created_at": row["created_at"], "updated_at": row["updated_at"]})
        elif mode == "range":
            bind.execute(sa.text("""
                INSERT INTO model_play_mode_rules (id, play_mode_id, rule_kind, is_supported, output_option_type, min_duration_seconds, max_duration_seconds_output, sort_order, created_at, updated_at)
                VALUES (:id, :mode_id, 'output_option', true, 'duration', :min_value, :max_value, 1, :created_at, :updated_at)
            """), {"id": _id("mpr", mode_id, "duration", "range"), "mode_id": mode_id, "min_value": duration.get("min_seconds"), "max_value": duration.get("max_seconds"), "created_at": row["created_at"], "updated_at": row["updated_at"]})
        elif mode == "adaptive":
            bind.execute(sa.text("""
                INSERT INTO model_play_mode_rules (id, play_mode_id, rule_kind, is_supported, output_option_type, is_adaptive, sort_order, created_at, updated_at)
                VALUES (:id, :mode_id, 'output_option', true, 'duration', true, 1, :created_at, :updated_at)
            """), {"id": _id("mpr", mode_id, "duration", "adaptive"), "mode_id": mode_id, "created_at": row["created_at"], "updated_at": row["updated_at"]})
        # 历史配置本身就是积分，直接写入新的积分字段，不做金额或汇率转换。
        if isinstance(prices.get("credits_per_second"), (int, float)):
            billing_unit = "second"
            credits = {"per_second_credits": int(prices["credits_per_second"])}
        elif isinstance(prices.get("fixed_credits"), int):
            billing_unit = "usage"
            credits = {"per_usage_credits": prices["fixed_credits"]}
        else:
            billing_unit = "usage"
            credits = {"per_usage_credits": 0}
        bind.execute(sa.text("""
            INSERT INTO model_play_mode_provider_prices (
              id, provider_id, resolution, billing_unit,
              per_million_input_credits, per_million_output_credits,
              per_usage_credits, per_second_credits,
              is_enabled, created_at, updated_at
            ) VALUES (
              :id, :provider_id, NULL, :billing_unit,
              :per_million_input_credits, :per_million_output_credits,
              :per_usage_credits, :per_second_credits,
              true, :created_at, :updated_at
            )
        """), {"id": _id("mppp", provider_id, billing_unit), "provider_id": provider_id, "billing_unit": billing_unit,
              "per_million_input_credits": credits.get("per_million_input_credits"),
              "per_million_output_credits": credits.get("per_million_output_credits"),
              "per_usage_credits": credits.get("per_usage_credits"),
              "per_second_credits": credits.get("per_second_credits"),
              "created_at": row["created_at"], "updated_at": row["updated_at"]})
    return mapping


def _rename_and_expand_tasks(mapping: dict[str, tuple[str, str]]) -> None:
    bind = op.get_bind()
    op.drop_index("ix_ai_video_tasks_poll_due", table_name="ai_video_tasks")
    op.drop_index("ix_ai_video_tasks_provider_task", table_name="ai_video_tasks")
    op.drop_index("ix_ai_video_tasks_project", table_name="ai_video_tasks")
    op.drop_index("ix_ai_video_tasks_user_created", table_name="ai_video_tasks")
    op.rename_table("ai_video_tasks", "model_tasks")
    with op.batch_alter_table("model_tasks") as batch:
        batch.drop_constraint("ck_ai_video_tasks_type", type_="check")
        batch.drop_constraint("ck_ai_video_tasks_status", type_="check")
        batch.drop_constraint("ck_ai_video_tasks_credits", type_="check")
        batch.drop_constraint("ck_ai_video_tasks_attempt_count", type_="check")
        batch.drop_constraint("uq_ai_video_tasks_user_idempotency", type_="unique")
        batch.alter_column("project_id", existing_type=sa.String(64), nullable=True)
        batch.add_column(sa.Column("play_mode_id", sa.String(64), nullable=True, comment="使用的模型玩法。"))
        batch.add_column(sa.Column("provider_id", sa.String(64), nullable=True, comment="提交时锁定的供应商。"))
        batch.add_column(sa.Column("prompt", sa.Text(), nullable=True, comment="文本提示词。"))
        batch.add_column(sa.Column("resolution", sa.String(32), nullable=True, comment="输出分辨率。"))
        batch.add_column(sa.Column("ratio", sa.String(16), nullable=True, comment="输出比例。"))
        batch.add_column(sa.Column("requested_duration_seconds", sa.Integer(), nullable=True, comment="请求视频时长。"))
        batch.add_column(sa.Column("audio_enabled", sa.Boolean(), nullable=False, server_default=sa.false(), comment="是否请求生成音频。"))
        batch.add_column(sa.Column("default_credits_charged", sa.Integer(), nullable=False, server_default="0", comment="预扣积分。"))
        batch.add_column(sa.Column("final_credits", sa.Integer(), nullable=True, comment="最终积分。"))
        batch.add_column(sa.Column("input_token", sa.Integer(), nullable=True, comment="输入 Token。"))
        batch.add_column(sa.Column("output_token", sa.Integer(), nullable=True, comment="输出 Token。"))
        batch.add_column(sa.Column("actual_output_duration_seconds", sa.Float(), nullable=True, comment="实际输出视频时长。"))
        batch.add_column(sa.Column("actual_output_image_count", sa.Integer(), nullable=True, comment="实际输出图片张数。"))
        batch.add_column(sa.Column("settlement_status", sa.String(24), nullable=False, server_default="pending", comment="结算状态。"))
    rows = bind.execute(sa.text("SELECT id, model_id, task_type, status, input_snapshot, credits FROM model_tasks")).mappings().all()
    for row in rows:
        model_id = str(row["model_id"])
        if model_id not in mapping:
            raise RuntimeError(f"cannot migrate model task {row['id']}: model {model_id} has no legacy play mode")
        input_snapshot = _dict(row.get("input_snapshot"))
        mode_id, provider_id = mapping[model_id]
        status = str(row["status"])
        settlement = "settled" if status == "succeeded" else "refunded" if status == "failed" else "pending"
        bind.execute(sa.text("""
            UPDATE model_tasks SET play_mode_id=:play_mode_id, provider_id=:provider_id, prompt=:prompt,
              resolution=:resolution, ratio=:ratio, requested_duration_seconds=:duration, audio_enabled=:audio_enabled,
              default_credits_charged=credits, settlement_status=:settlement
            WHERE id=:id
        """), {"id": row["id"], "play_mode_id": mode_id, "provider_id": provider_id,
              "prompt": input_snapshot.get("prompt") if isinstance(input_snapshot.get("prompt"), str) else None,
              "resolution": input_snapshot.get("resolution") if isinstance(input_snapshot.get("resolution"), str) else None,
              "ratio": input_snapshot.get("ratio") if isinstance(input_snapshot.get("ratio"), str) else None,
              "duration": input_snapshot.get("duration_seconds") if isinstance(input_snapshot.get("duration_seconds"), int) else None,
              "audio_enabled": bool(input_snapshot.get("audio_enabled")), "settlement": settlement})
    # Keep legacy JSON columns until `_migrate_legacy_task_details` has
    # materialised historic asset/output rows in the new normalized tables.
    with op.batch_alter_table("model_tasks") as batch:
        batch.alter_column("play_mode_id", existing_type=sa.String(64), nullable=False)
        batch.alter_column("provider_id", existing_type=sa.String(64), nullable=False)
        batch.alter_column("task_type", existing_type=sa.String(16), nullable=False)
        batch.create_foreign_key("fk_model_tasks_play_mode", "model_play_modes", ["play_mode_id"], ["id"], ondelete="RESTRICT")
        batch.create_foreign_key("fk_model_tasks_provider", "model_play_mode_providers", ["provider_id"], ["id"], ondelete="RESTRICT")
        batch.create_check_constraint("ck_model_tasks_type", "task_type IN ('llm', 'image', 'video')")
        batch.create_check_constraint("ck_model_tasks_status", "status IN ('submitting', 'queued', 'processing', 'finalizing', 'succeeded', 'succeeded_with_partial_output', 'failed')")
        batch.create_check_constraint("ck_model_tasks_attempt_count", "attempt_count > 0")
        batch.create_unique_constraint("uq_model_tasks_user_idempotency", ["user_id", "idempotency_key"])
    op.create_index("ix_model_tasks_user_created", "model_tasks", ["user_id", "created_at"])
    op.create_index("ix_model_tasks_project", "model_tasks", ["project_id"])
    op.create_index("ix_model_tasks_provider_task", "model_tasks", ["provider_task_id"])
    op.create_index("ix_model_tasks_poll_due", "model_tasks", ["status", "next_poll_at"])


def _create_task_detail_tables() -> None:
    op.create_table(
        "model_task_assets",
        sa.Column("id", sa.String(64), primary_key=True, comment="任务素材关联主键。"),
        sa.Column("task_id", sa.String(64), sa.ForeignKey("model_tasks.id", ondelete="CASCADE"), nullable=False, comment="所属任务。"),
        sa.Column("asset_id", sa.String(64), sa.ForeignKey("assets.id", ondelete="RESTRICT"), nullable=False, comment="引用资产。"),
        sa.Column("input_type", sa.String(16), nullable=False, comment="输入类型。"),
        sa.Column("is_mentioned", sa.Boolean(), nullable=False, server_default=sa.false(), comment="是否被 @ 引用。"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0", comment="提交顺序。"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, comment="创建时间 UTC。"),
        sa.CheckConstraint("input_type IN ('text', 'image', 'video', 'audio')", name="ck_model_task_assets_type"),
        sa.CheckConstraint("sort_order >= 0", name="ck_model_task_assets_sort_order"),
        sa.UniqueConstraint("task_id", "asset_id", name="uq_model_task_assets_task_asset"),
        comment="任务引用的本次上传素材与 @ 引用标记。",
    )
    op.create_index("ix_model_task_assets_task", "model_task_assets", ["task_id", "sort_order"])
    op.create_table(
        "model_task_outputs",
        sa.Column("id", sa.String(64), primary_key=True, comment="任务输出主键。"),
        sa.Column("task_id", sa.String(64), sa.ForeignKey("model_tasks.id", ondelete="CASCADE"), nullable=False, comment="所属任务。"),
        sa.Column("output_type", sa.String(16), nullable=False, comment="输出类型。"),
        sa.Column("provider_url", sa.String(2048), nullable=True, comment="供应商短期输出 URL。"),
        sa.Column("oss_bucket", sa.String(255), nullable=True, comment="OSS Bucket。"),
        sa.Column("oss_object_key", sa.String(1024), nullable=True, comment="OSS 对象键。"),
        sa.Column("cdn_url", sa.String(2048), nullable=True, comment="长期 CDN URL。"),
        sa.Column("content_type", sa.String(255), nullable=True, comment="内容类型。"),
        sa.Column("size_bytes", sa.BigInteger(), nullable=True, comment="输出大小。"),
        sa.Column("duration_seconds", sa.Float(), nullable=True, comment="视频真实时长。"),
        sa.Column("core_task_id", sa.String(128), nullable=True, comment="Core 媒体信息任务 ID。"),
        sa.Column("text_content", sa.Text(), nullable=True, comment="LLM 文本输出。"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0", comment="输出顺序。"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, comment="创建时间 UTC。"),
        sa.CheckConstraint("output_type IN ('text', 'image', 'video')", name="ck_model_task_outputs_type"),
        sa.CheckConstraint("sort_order >= 0", name="ck_model_task_outputs_sort_order"),
        sa.UniqueConstraint("task_id", "sort_order", name="uq_model_task_outputs_task_sort"),
        comment="供应商成功产物转存 OSS 后的逐项输出记录。",
    )
    op.create_index("ix_model_task_outputs_task", "model_task_outputs", ["task_id", "sort_order"])
    op.create_table(
        "model_task_charges",
        sa.Column("id", sa.String(64), primary_key=True, comment="任务收费明细主键。"),
        sa.Column("task_id", sa.String(64), sa.ForeignKey("model_tasks.id", ondelete="CASCADE"), nullable=False, comment="所属任务。"),
        sa.Column("billing_unit", sa.String(40), nullable=False, comment="结算单位。"),
        sa.Column("resolution", sa.String(32), nullable=True, comment="锁定分辨率。"),
        sa.Column("per_million_input_credits", sa.Integer(), nullable=True, comment="锁定的每百万输入 Token 积分。"),
        sa.Column("per_million_output_credits", sa.Integer(), nullable=True, comment="锁定的每百万输出 Token 积分。"),
        sa.Column("per_usage_credits", sa.Integer(), nullable=True, comment="锁定的每次调用或每个图片输出积分。"),
        sa.Column("per_second_credits", sa.Integer(), nullable=True, comment="锁定的每秒视频输出积分。"),
        sa.Column("quantity", sa.Numeric(20, 6), nullable=False, server_default="0", comment="实际计费数量。"),
        sa.Column("credits", sa.Integer(), nullable=False, server_default="0", comment="该明细积分。"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, comment="创建时间 UTC。"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, comment="更新时间 UTC。"),
        sa.CheckConstraint("billing_unit IN ('second', 'token', 'usage')", name="ck_model_task_charges_unit"),
        sa.CheckConstraint("per_million_input_credits IS NULL OR per_million_input_credits >= 0", name="ck_model_task_charges_input_credits"),
        sa.CheckConstraint("per_million_output_credits IS NULL OR per_million_output_credits >= 0", name="ck_model_task_charges_output_credits"),
        sa.CheckConstraint("per_usage_credits IS NULL OR per_usage_credits >= 0", name="ck_model_task_charges_usage_credits"),
        sa.CheckConstraint("per_second_credits IS NULL OR per_second_credits >= 0", name="ck_model_task_charges_second_credits"),
        sa.CheckConstraint("billing_unit != 'second' OR per_second_credits IS NOT NULL", name="ck_model_task_charges_second_value"),
        sa.CheckConstraint("billing_unit != 'usage' OR per_usage_credits IS NOT NULL", name="ck_model_task_charges_usage_value"),
        sa.CheckConstraint("billing_unit != 'token' OR per_million_input_credits IS NOT NULL OR per_million_output_credits IS NOT NULL", name="ck_model_task_charges_token_value"),
        sa.CheckConstraint("quantity >= 0", name="ck_model_task_charges_quantity"),
        sa.UniqueConstraint("task_id", "billing_unit", name="uq_model_task_charges_task_unit"),
        comment="任务提交时冻结的积分规则及结算后的实际数量。",
    )


def _migrate_legacy_task_details() -> None:
    """Materialise old task JSON before removing the transitional columns."""

    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT id, task_type, status, input_snapshot, output, created_at FROM model_tasks")).mappings().all()
    for row in rows:
        task_id = str(row["id"])
        snapshot = _dict(row.get("input_snapshot"))
        mentioned = {str(value) for value in _list(snapshot.get("multi_subject_references")) if isinstance(value, str)}
        for input_type, key in (("image", "image_asset_ids"), ("video", "video_asset_ids"), ("audio", "audio_asset_ids")):
            values = snapshot.get(key)
            if not isinstance(values, list):
                # Older payloads used per-type object keys instead of *_asset_ids.
                values = snapshot.get(f"{input_type}_assets")
            for sort_order, value in enumerate(_list(values)):
                asset_id = value.get("asset_id") if isinstance(value, dict) else value
                if not isinstance(asset_id, str) or not asset_id:
                    continue
                bind.execute(sa.text("""
                    INSERT INTO model_task_assets (id, task_id, asset_id, input_type, is_mentioned, sort_order, created_at)
                    VALUES (:id, :task_id, :asset_id, :input_type, :is_mentioned, :sort_order, :created_at)
                    ON CONFLICT (task_id, asset_id) DO NOTHING
                """), {"id": _id("mta", task_id, asset_id), "task_id": task_id, "asset_id": asset_id,
                      "input_type": input_type, "is_mentioned": asset_id in mentioned,
                      "sort_order": sort_order, "created_at": row["created_at"]})
        output = _dict(row.get("output"))
        output_url = output.get("url") or output.get("video_url") or output.get("image_url")
        if isinstance(output_url, str) and output_url:
            output_type = str(row.get("task_type") or "video")
            if output_type not in {"image", "video"}:
                output_type = "video"
            bind.execute(sa.text("""
                INSERT INTO model_task_outputs (id, task_id, output_type, provider_url, cdn_url, sort_order, created_at)
                VALUES (:id, :task_id, :output_type, :provider_url, :cdn_url, 0, :created_at)
                ON CONFLICT (task_id, sort_order) DO NOTHING
            """), {"id": _id("mto", task_id, 0), "task_id": task_id, "output_type": output_type,
                  "provider_url": output_url, "cdn_url": output_url, "created_at": row["created_at"]})


def _drop_legacy_task_columns() -> None:
    with op.batch_alter_table("model_tasks") as batch:
        batch.drop_column("input_snapshot")
        batch.drop_column("price_snapshot")
        batch.drop_column("output")
        batch.drop_column("credits")


def _drop_legacy_model_columns() -> None:
    with op.batch_alter_table("models") as batch:
        batch.drop_column("provider_code")
        batch.drop_column("provider_model_id")
        batch.drop_column("provider_config")
        batch.drop_column("capabilities")
        batch.drop_column("price_config")


def _allow_negative_credit_balances() -> None:
    with op.batch_alter_table("credit_accounts") as batch:
        batch.drop_constraint("ck_credit_accounts_balance", type_="check")


def _enforce_one_default_model_per_type() -> None:
    """Keep the highest-ranked current default before creating a partial unique index."""
    op.execute(sa.text("""
        WITH ranked AS (
          SELECT id, row_number() OVER (
            PARTITION BY model_type ORDER BY sort_order DESC, id
          ) AS row_number
          FROM models
          WHERE is_default = true
        )
        UPDATE models SET is_default = false
        WHERE id IN (SELECT id FROM ranked WHERE row_number > 1)
    """))
    op.create_index(
        "uq_models_default_by_type",
        "models",
        ["model_type"],
        unique=True,
        postgresql_where=sa.text("is_default"),
        sqlite_where=sa.text("is_default = 1"),
    )


def upgrade() -> None:
    _create_configuration_tables()
    mapping = _migrate_legacy_models()
    _rename_and_expand_tasks(mapping)
    _create_task_detail_tables()
    _migrate_legacy_task_details()
    _drop_legacy_task_columns()
    _drop_legacy_model_columns()
    _allow_negative_credit_balances()
    _enforce_one_default_model_per_type()


def downgrade() -> None:
    raise RuntimeError("0031_normalize_model_generation is intentionally irreversible after task/config normalization")
