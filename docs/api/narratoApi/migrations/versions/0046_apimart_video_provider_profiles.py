"""Add explicit provider request profiles and frozen provider options.

Revision ID: 0046_apimart_video_provider_profiles
Revises: 0045_conversation_context_memory
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0046_apimart_video_provider_profiles"
down_revision: str | None = "0045_conversation_context_memory"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("model_play_mode_providers") as batch:
        batch.add_column(
            sa.Column(
                "request_profile",
                sa.String(64),
                nullable=False,
                server_default="default",
                comment="Provider 请求协议 Profile；Adapter 由 provider_code 选择。",
            )
        )
    with op.batch_alter_table("model_tasks") as batch:
        batch.add_column(
            sa.Column(
                "provider_options",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'{}'"),
                comment="已校验并冻结的 Provider 专有请求参数。",
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("model_tasks") as batch:
        batch.drop_column("provider_options")
    with op.batch_alter_table("model_play_mode_providers") as batch:
        batch.drop_column("request_profile")
