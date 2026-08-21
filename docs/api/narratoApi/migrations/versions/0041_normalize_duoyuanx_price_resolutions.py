"""Normalize Duoyuanx price resolution labels.

Revision ID: 0041_normalize_duoyuanx_price_resolutions
Revises: 0040_normalize_duoyuanx_resolution_options
Create Date: 2026-08-18

Capability rows and price rows must use the same resolution key.  0040 fixed
the former; this migration fixes legacy ``480P``/``720P`` price rows so quote
and task creation continue to find their active per-resolution price.
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0041_normalize_duoyuanx_price_resolutions"
down_revision: str | None = "0040_normalize_duoyuanx_resolution_options"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            sa.text(
                """
                UPDATE model_play_mode_provider_prices AS price
                SET resolution = lower(price.resolution),
                    updated_at = CURRENT_TIMESTAMP
                WHERE price.resolution IS NOT NULL
                  AND EXISTS (
                    SELECT 1
                    FROM model_play_mode_providers AS provider
                    WHERE provider.id = price.provider_id
                      AND provider.provider_code = 'duoyuanx'
                  )
                """
            )
        )
        return

    prices = sa.table(
        "model_play_mode_provider_prices",
        sa.column("id", sa.String),
        sa.column("provider_id", sa.String),
        sa.column("resolution", sa.String),
    )
    providers = sa.table(
        "model_play_mode_providers",
        sa.column("id", sa.String),
        sa.column("provider_code", sa.String),
    )
    rows = bind.execute(
        sa.select(prices.c.id, prices.c.resolution)
        .join(providers, providers.c.id == prices.c.provider_id)
        .where(providers.c.provider_code == "duoyuanx", prices.c.resolution.is_not(None))
    ).all()
    for row in rows:
        bind.execute(sa.update(prices).where(prices.c.id == row.id).values(resolution=row.resolution.lower()))


def downgrade() -> None:
    raise RuntimeError(
        "0041_normalize_duoyuanx_price_resolutions is intentionally irreversible; "
        "mixed-case labels are not valid provider API values."
    )
