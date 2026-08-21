"""Generalize the model catalog and document AI video persistence.

Revision ID: 0029_general_models_comments
Revises: 0028_ai_video_generation

``0028`` may already be installed.  This migration deliberately evolves that
schema instead of changing history: the existing table is renamed, every
existing image/video value is copied to the unambiguous ``model_type`` column,
and the legacy ``output_type`` column is removed.
"""

from typing import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0029_general_models_comments"
down_revision: str | None = "0028_ai_video_generation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_MODEL_COMMENTS = {
    None: "运营配置的通用 AI 模型目录，涵盖图片、视频和 LLM 模型。",
    "id": "模型配置的稳定主键。",
    "display_name": "面向用户展示的模型名称。",
    "provider_code": "供应商代码，例如 volcengine。",
    "provider_model_id": "供应商侧的模型标识。",
    "model_type": "模型输出类别：image、video 或 llm。",
    "provider_config": "仅服务端读取的供应商连接及认证配置。",
    "capabilities": "模型支持的输入素材和生成参数能力。",
    "price_config": "模型计费规则配置。",
    "description": "面向用户展示的模型简介。",
    "cover_url": "模型目录卡片封面地址。",
    "category": "模型目录的运营分类。",
    "sort_order": "模型目录排序值，数值越小越靠前。",
    "is_enabled": "模型是否允许在产品中被选择和调用。",
    "is_default": "该模型类型是否为默认模型。",
    "created_at": "模型配置创建时间（UTC）。",
    "updated_at": "模型配置最后更新时间（UTC）。",
}

_TASK_COMMENTS = {
    None: "AI 视频生成任务、计费快照与供应商回执的事实记录。",
    "id": "AI 视频任务主键。",
    "project_id": "承载该任务的 AI 视频草稿项目。",
    "user_id": "创建任务的用户。",
    "model_id": "本次任务使用的通用模型配置。",
    "task_type": "任务输出类型：image 或 video。",
    "status": "任务生命周期状态。",
    "idempotency_key": "用户维度的提交幂等键。",
    "provider_task_id": "供应商返回的远端任务标识。",
    "input_snapshot": "提交时冻结的提示词、素材与生成参数。",
    "price_snapshot": "提交时冻结的计费规则和报价。",
    "provider_request": "向供应商发起请求的可审计摘要。",
    "provider_response": "供应商最后一次返回的可审计摘要。",
    "output": "供应商生成成功后的输出信息。",
    "credits": "本次尝试需要扣除的积分。",
    "attempt_count": "任务提交尝试次数。",
    "error_code": "最近一次失败的标准错误码。",
    "error_message": "最近一次失败的用户可读错误信息。",
    "submitted_at": "最近一次向供应商提交成功的时间（UTC）。",
    "created_at": "任务创建时间（UTC）。",
    "updated_at": "任务最后更新时间（UTC）。",
}


def _comment_postgresql(table_name: str, comments: dict[str | None, str]) -> None:
    """Apply PostgreSQL comments after SQLite-compatible structural changes."""

    if op.get_bind().dialect.name != "postgresql":
        return
    for column_name, comment in comments.items():
        literal = comment.replace("'", "''")
        if column_name is None:
            op.execute(sa.text(f"COMMENT ON TABLE {table_name} IS '{literal}'"))
        else:
            op.execute(sa.text(f"COMMENT ON COLUMN {table_name}.{column_name} IS '{literal}'"))


def upgrade() -> None:
    """Rename the deployed catalog, preserve data, and add PostgreSQL documentation."""

    op.rename_table("ai_video_models", "models")

    # Add nullable first so installed databases can be backfilled before a NOT NULL
    # constraint is added.  batch_alter_table keeps this sequence usable by SQLite
    # migration tests as well as PostgreSQL production databases.
    with op.batch_alter_table("models") as batch_op:
        batch_op.add_column(sa.Column("model_type", sa.String(length=16), nullable=True))

    op.execute(
        sa.text(
            "UPDATE models "
            "SET model_type = CASE "
            "WHEN output_type IN ('image', 'video') THEN output_type "
            "ELSE 'video' END"
        )
    )

    with op.batch_alter_table("models") as batch_op:
        batch_op.drop_constraint("ck_ai_video_models_id", type_="check")
        batch_op.drop_constraint("ck_ai_video_models_sort_order", type_="check")
        batch_op.drop_constraint("ck_ai_video_models_output_type", type_="check")
        batch_op.drop_column("output_type")
        batch_op.alter_column(
            "model_type",
            existing_type=sa.String(length=16),
            nullable=False,
            server_default="video",
        )
        batch_op.create_check_constraint(
            "ck_models_model_type", "model_type IN ('image', 'video', 'llm')"
        )
        batch_op.create_check_constraint("ck_models_id", "length(id) BETWEEN 1 AND 64")
        batch_op.create_check_constraint("ck_models_sort_order", "sort_order >= 0")

    _comment_postgresql("models", _MODEL_COMMENTS)
    _comment_postgresql("ai_video_tasks", _TASK_COMMENTS)


def downgrade() -> None:
    """Restore the video-only catalog without silently dropping LLM configuration."""

    llm_count = op.get_bind().execute(
        sa.text("SELECT count(*) FROM models WHERE model_type = 'llm'")
    ).scalar_one()
    if llm_count:
        raise RuntimeError("cannot downgrade 0029 while llm model configurations exist")

    with op.batch_alter_table("models") as batch_op:
        batch_op.drop_constraint("ck_models_model_type", type_="check")
        batch_op.drop_constraint("ck_models_id", type_="check")
        batch_op.drop_constraint("ck_models_sort_order", type_="check")
        batch_op.add_column(
            sa.Column("output_type", sa.String(length=16), nullable=True)
        )

    op.execute(sa.text("UPDATE models SET output_type = model_type"))

    with op.batch_alter_table("models") as batch_op:
        batch_op.drop_column("model_type")
        batch_op.alter_column(
            "output_type",
            existing_type=sa.String(length=16),
            nullable=False,
            server_default="video",
        )
        batch_op.create_check_constraint(
            "ck_ai_video_models_output_type", "output_type IN ('image', 'video')"
        )
        batch_op.create_check_constraint("ck_ai_video_models_id", "length(id) BETWEEN 1 AND 64")
        batch_op.create_check_constraint("ck_ai_video_models_sort_order", "sort_order >= 0")

    op.rename_table("models", "ai_video_models")
