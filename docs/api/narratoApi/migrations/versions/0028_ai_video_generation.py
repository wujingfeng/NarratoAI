"""Add database-configured AI video models and direct-provider tasks.

Revision ID: 0028_ai_video_generation
Revises: 0027_video_translation_voice_replacement_charge
"""
from typing import Sequence
from alembic import op
import sqlalchemy as sa

revision: str = "0028_ai_video_generation"
down_revision: str | None = "0027_video_translation_voice_replacement_charge"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_video_models",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("display_name", sa.String(128), nullable=False),
        sa.Column("provider_code", sa.String(64), nullable=False),
        sa.Column("provider_model_id", sa.String(128), nullable=False),
        sa.Column("output_type", sa.String(16), nullable=False, server_default="video"),
        sa.Column("provider_config", sa.JSON(), nullable=False),
        sa.Column("capabilities", sa.JSON(), nullable=False),
        sa.Column("price_config", sa.JSON(), nullable=False),
        sa.Column("description", sa.String(512)),
        sa.Column("cover_url", sa.String(2048)),
        sa.Column("category", sa.String(64), nullable=False, server_default="all"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("length(id) BETWEEN 1 AND 64", name="ck_ai_video_models_id"),
        sa.CheckConstraint("sort_order >= 0", name="ck_ai_video_models_sort_order"),
        sa.CheckConstraint("output_type IN ('image', 'video')", name="ck_ai_video_models_output_type"),
    )
    op.create_table(
        "ai_video_tasks",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("user_id", sa.String(64), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("model_id", sa.String(64), sa.ForeignKey("ai_video_models.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("task_type", sa.String(16), nullable=False, server_default="video"),
        sa.Column("status", sa.String(16), nullable=False, server_default="submitting"),
        sa.Column("idempotency_key", sa.String(256), nullable=False),
        sa.Column("provider_task_id", sa.String(256), unique=True),
        sa.Column("input_snapshot", sa.JSON(), nullable=False),
        sa.Column("price_snapshot", sa.JSON(), nullable=False),
        sa.Column("provider_request", sa.JSON()), sa.Column("provider_response", sa.JSON()), sa.Column("output", sa.JSON()),
        sa.Column("credits", sa.Integer(), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("error_code", sa.String(64)), sa.Column("error_message", sa.String(512)),
        sa.Column("submitted_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("task_type IN ('image', 'video')", name="ck_ai_video_tasks_type"),
        sa.CheckConstraint("status IN ('submitting', 'queued', 'processing', 'succeeded', 'failed')", name="ck_ai_video_tasks_status"),
        sa.CheckConstraint("credits >= 0", name="ck_ai_video_tasks_credits"),
        sa.CheckConstraint("attempt_count > 0", name="ck_ai_video_tasks_attempt_count"),
        sa.UniqueConstraint("user_id", "idempotency_key", name="uq_ai_video_tasks_user_idempotency"),
    )
    op.create_index("ix_ai_video_tasks_user_created", "ai_video_tasks", ["user_id", "created_at"])
    op.create_index("ix_ai_video_tasks_project", "ai_video_tasks", ["project_id"])
    op.create_index("ix_ai_video_tasks_provider_task", "ai_video_tasks", ["provider_task_id"])
    # 既有统一上传资产需要图片类型；旧视频/字幕/音频约束保持不变。
    with op.batch_alter_table("assets") as batch_op:
        batch_op.drop_constraint("ck_assets_type", type_="check")
        batch_op.create_check_constraint("ck_assets_type", "asset_type IN ('image', 'video', 'subtitle', 'audio')")


def downgrade() -> None:
    image_count = op.get_bind().execute(sa.text("SELECT count(*) FROM assets WHERE asset_type = 'image'")).scalar_one()
    if image_count:
        raise RuntimeError("cannot downgrade 0028 while image assets exist")
    with op.batch_alter_table("assets") as batch_op:
        batch_op.drop_constraint("ck_assets_type", type_="check")
        batch_op.create_check_constraint("ck_assets_type", "asset_type IN ('video', 'subtitle', 'audio')")
    op.drop_index("ix_ai_video_tasks_provider_task", table_name="ai_video_tasks")
    op.drop_index("ix_ai_video_tasks_project", table_name="ai_video_tasks")
    op.drop_index("ix_ai_video_tasks_user_created", table_name="ai_video_tasks")
    op.drop_table("ai_video_tasks")
    op.drop_table("ai_video_models")
