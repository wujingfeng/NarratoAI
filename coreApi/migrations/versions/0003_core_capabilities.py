"""建立统一供应商、模型和音色能力目录。

Revision ID: 0003_core_capabilities
Revises: 0002_core_tasks
Create Date: 2026-07-16
"""

from typing import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_core_capabilities"
down_revision: str | None = "0002_core_tasks"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """创建 Core 数据库唯一事实源的能力配置表。"""

    op.create_table(
        "core_providers",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("code", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("secret_ref", sa.String(length=160), nullable=False),
        sa.Column("settings", sa.JSON(), nullable=False),
        sa.Column("limits", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_core_providers_code"),
    )
    op.create_table(
        "core_models",
        sa.Column("model_id", sa.String(length=40), nullable=False),
        sa.Column("provider_id", sa.String(length=40), nullable=False),
        sa.Column("provider_model_code", sa.String(length=160), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("capability_types", sa.JSON(), nullable=False),
        sa.Column("languages", sa.JSON(), nullable=False),
        sa.Column("limits", sa.JSON(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["provider_id"], ["core_providers.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("model_id"),
        sa.UniqueConstraint(
            "provider_id",
            "provider_model_code",
            name="uq_core_models_provider_code",
        ),
    )
    op.create_index(
        "ix_core_models_provider_enabled",
        "core_models",
        ["provider_id", "enabled"],
        unique=False,
    )
    op.create_table(
        "core_voices",
        sa.Column("voice_id", sa.String(length=40), nullable=False),
        sa.Column("provider_id", sa.String(length=40), nullable=False),
        sa.Column("provider_voice_code", sa.String(length=160), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("languages", sa.JSON(), nullable=False),
        sa.Column("gender", sa.String(length=32), nullable=True),
        sa.Column("styles", sa.JSON(), nullable=False),
        sa.Column("sample_url", sa.String(length=2048), nullable=True),
        sa.Column("supported_formats", sa.JSON(), nullable=False),
        sa.Column("supported_sample_rates", sa.JSON(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["provider_id"], ["core_providers.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("voice_id"),
        sa.UniqueConstraint(
            "provider_id",
            "provider_voice_code",
            name="uq_core_voices_provider_code",
        ),
    )
    op.create_index(
        "ix_core_voices_provider_enabled",
        "core_voices",
        ["provider_id", "enabled"],
        unique=False,
    )


def downgrade() -> None:
    """按外键依赖逆序删除能力目录表。"""

    op.drop_index("ix_core_voices_provider_enabled", table_name="core_voices")
    op.drop_table("core_voices")
    op.drop_index("ix_core_models_provider_enabled", table_name="core_models")
    op.drop_table("core_models")
    op.drop_table("core_providers")
