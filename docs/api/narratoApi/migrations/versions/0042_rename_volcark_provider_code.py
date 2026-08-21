"""Rename the Volcengine Ark provider code.

Revision ID: 0042_rename_volcark_provider_code
Revises: 0041_normalize_duoyuanx_price_resolutions
Create Date: 2026-08-19

``volcark`` named an API product, rather than the provider.  Persist provider
rows under the provider-level code ``volcengine`` while keeping the existing
Ark adapter implementation and endpoint configuration unchanged.
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0042_rename_volcark_provider_code"
down_revision: str | None = "0041_normalize_duoyuanx_price_resolutions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _rename(*, old: str, new: str) -> None:
    providers = sa.table(
        "model_play_mode_providers",
        sa.column("provider_code", sa.String),
    )
    op.execute(
        sa.update(providers)
        .where(providers.c.provider_code == old)
        .values(provider_code=new)
    )


def upgrade() -> None:
    _rename(old="volcark", new="volcengine")


def downgrade() -> None:
    _rename(old="volcengine", new="volcark")
