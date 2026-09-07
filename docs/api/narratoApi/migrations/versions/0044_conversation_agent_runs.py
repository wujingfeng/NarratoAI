"""Persist AI assistant conversation threads, messages, and agent runs.

Revision ID: 0044_conversation_agent_runs
Revises: 0043_model_task_asset_provider_roles
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0044_conversation_agent_runs"
down_revision: str | None = "0043_model_task_asset_provider_roles"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    modes = "'chat', 'short_drama_narration', 'video_translation', 'video_generation'"
    op.create_table(
        "conversation_threads",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.String(64), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("mode", sa.String(32), nullable=False, server_default="chat"),
        sa.Column("title", sa.String(200)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(f"mode IN ({modes})", name="ck_conversation_threads_mode"),
    )
    op.create_index("ix_conversation_threads_user_updated", "conversation_threads", ["user_id", "updated_at"])
    op.create_table(
        "conversation_messages",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("thread_id", sa.String(64), sa.ForeignKey("conversation_threads.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("user_id", sa.String(64), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("mode", sa.String(32), nullable=False),
        sa.Column("content", sa.Text(), nullable=False, server_default=""),
        sa.Column("attachments", sa.JSON(), nullable=False),
        sa.Column("idempotency_key", sa.String(256)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("role IN ('user', 'assistant', 'system')", name="ck_conversation_messages_role"),
        sa.CheckConstraint(f"mode IN ({modes})", name="ck_conversation_messages_mode"),
        sa.UniqueConstraint("thread_id", "idempotency_key", name="uq_conversation_messages_idempotency"),
    )
    op.create_index("ix_conversation_messages_thread_created", "conversation_messages", ["thread_id", "created_at"])
    op.create_table(
        "agent_runs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("thread_id", sa.String(64), sa.ForeignKey("conversation_threads.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("message_id", sa.String(64), sa.ForeignKey("conversation_messages.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("user_id", sa.String(64), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("mode", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("idempotency_key", sa.String(256), nullable=False),
        sa.Column("input_config", sa.JSON(), nullable=False),
        sa.Column("resolved_config", sa.JSON(), nullable=False),
        sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id", ondelete="RESTRICT")),
        sa.Column("workflow_id", sa.String(64), sa.ForeignKey("workflows.id", ondelete="RESTRICT")),
        sa.Column("model_task_id", sa.String(64), sa.ForeignKey("model_tasks.id", ondelete="RESTRICT")),
        sa.Column("result", sa.JSON()),
        sa.Column("error_code", sa.String(64)),
        sa.Column("error_message", sa.String(512)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("mode IN ('short_drama_narration', 'video_translation', 'video_generation')", name="ck_agent_runs_mode"),
        sa.CheckConstraint("status IN ('pending', 'queued', 'running', 'completed', 'failed')", name="ck_agent_runs_status"),
        sa.UniqueConstraint("user_id", "idempotency_key", name="uq_agent_runs_user_idempotency"),
    )
    op.create_index("ix_agent_runs_thread_created", "agent_runs", ["thread_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_agent_runs_thread_created", table_name="agent_runs")
    op.drop_table("agent_runs")
    op.drop_index("ix_conversation_messages_thread_created", table_name="conversation_messages")
    op.drop_table("conversation_messages")
    op.drop_index("ix_conversation_threads_user_updated", table_name="conversation_threads")
    op.drop_table("conversation_threads")
