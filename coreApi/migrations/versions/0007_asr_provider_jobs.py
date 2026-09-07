"""Persist recoverable third-party ASR jobs.

Revision ID: 0007_asr_provider_jobs
Revises: 0006_volcengine_multilingual_voices
Create Date: 2026-08-25
"""

from typing import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_asr_provider_jobs"
down_revision: str | None = "0006_volcengine_multilingual_voices"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "asr_provider_jobs",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("core_task_id", sa.String(length=40), nullable=False),
        sa.Column("source_index", sa.Integer(), nullable=False),
        sa.Column("source_asset_id", sa.String(length=80), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("provider_task_id", sa.String(length=160), nullable=True),
        sa.Column("callback_key", sa.String(length=128), nullable=False),
        sa.Column("prepared_audio_url", sa.String(length=2048), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("response_payload", sa.JSON(), nullable=True),
        sa.Column("error", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('preparing', 'submitted', 'succeeded', 'failed')",
            name="ck_asr_provider_jobs_status",
        ),
        sa.ForeignKeyConstraint(
            ["core_task_id"], ["core_tasks.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "core_task_id", "source_index", name="uq_asr_provider_jobs_task_source"
        ),
        sa.UniqueConstraint(
            "provider", "provider_task_id", name="uq_asr_provider_jobs_remote"
        ),
        sa.UniqueConstraint("callback_key", name="uq_asr_provider_jobs_callback_key"),
    )
    op.create_index(
        "ix_asr_provider_jobs_status",
        "asr_provider_jobs",
        ["status", "updated_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_asr_provider_jobs_status", table_name="asr_provider_jobs")
    op.drop_table("asr_provider_jobs")
