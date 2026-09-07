"""Add durable rolling context memory to assistant conversation threads.

Revision ID: 0045_conversation_context_memory
Revises: 0044_conversation_agent_runs
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0045_conversation_context_memory"
down_revision: str | None = "0044_conversation_agent_runs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("conversation_threads", sa.Column("chat_summary", sa.Text()))
    op.add_column(
        "conversation_threads",
        sa.Column("chat_memory", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )
    op.add_column(
        "conversation_threads",
        sa.Column("chat_memory_updated_at", sa.DateTime(timezone=True)),
    )


def downgrade() -> None:
    op.drop_column("conversation_threads", "chat_memory_updated_at")
    op.drop_column("conversation_threads", "chat_memory")
    op.drop_column("conversation_threads", "chat_summary")
