"""Freeze provider media roles on model task assets.

Revision ID: 0043_model_task_asset_provider_roles
Revises: 0042_rename_volcark_provider_code
Create Date: 2026-08-19

Task assets are a submission snapshot.  The provider role must therefore be
stored with the asset instead of being inferred from a later model change.
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0043_model_task_asset_provider_roles"
down_revision: str | None = "0042_rename_volcark_provider_code"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("model_task_assets") as batch:
        batch.add_column(
            sa.Column(
                "provider_role",
                sa.String(64),
                nullable=True,
                comment="提交给供应商的媒体角色，例如 reference_image。",
            )
        )
    assets = sa.table(
        "model_task_assets",
        sa.column("input_type", sa.String),
        sa.column("provider_role", sa.String),
    )
    for input_type in ("image", "video", "audio"):
        op.execute(
            sa.update(assets)
            .where(assets.c.input_type == input_type)
            .values(provider_role=f"reference_{input_type}")
        )


def downgrade() -> None:
    with op.batch_alter_table("model_task_assets") as batch:
        batch.drop_column("provider_role")
