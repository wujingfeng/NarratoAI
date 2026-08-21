"""Normalize legacy Duoyuanx resolution labels to the provider API enum.

Revision ID: 0040_normalize_duoyuanx_resolution_options
Revises: 0039_admin_menu_ui_paths
Create Date: 2026-08-18

The public API documents lower-case resolution values (``480p``, ``720p``,
``1080p`` and ``4k``).  Earlier operational capability rows used labels such
as ``480P`` and therefore produced provider HTTP 400 responses.
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0040_normalize_duoyuanx_resolution_options"
down_revision: str | None = "0039_admin_menu_ui_paths"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        # Only touch play modes which actually submit through the Duoyuanx
        # adapter.  Other providers may use case-sensitive, different enums.
        op.execute(
            sa.text(
                """
                UPDATE model_play_mode_rules AS rule
                SET resolution = ARRAY(
                    SELECT lower(option)
                    FROM unnest(rule.resolution) AS option
                ),
                    updated_at = CURRENT_TIMESTAMP
                WHERE rule.rule_kind = 'output_option'
                  AND rule.output_option_type = 'resolution'
                  AND rule.resolution IS NOT NULL
                  AND EXISTS (
                    SELECT 1
                    FROM model_play_mode_providers AS provider
                    WHERE provider.play_mode_id = rule.play_mode_id
                      AND provider.provider_code = 'duoyuanx'
                  )
                """
            )
        )
        return

    # SQLite is used by migration tests and stores StringArray as JSON.
    rules = sa.table(
        "model_play_mode_rules",
        sa.column("id", sa.String),
        sa.column("play_mode_id", sa.String),
        sa.column("rule_kind", sa.String),
        sa.column("output_option_type", sa.String),
        sa.column("resolution", sa.JSON),
    )
    providers = sa.table(
        "model_play_mode_providers",
        sa.column("play_mode_id", sa.String),
        sa.column("provider_code", sa.String),
    )
    rows = bind.execute(
        sa.select(rules.c.id, rules.c.resolution)
        .join(providers, providers.c.play_mode_id == rules.c.play_mode_id)
        .where(
            providers.c.provider_code == "duoyuanx",
            rules.c.rule_kind == "output_option",
            rules.c.output_option_type == "resolution",
            rules.c.resolution.is_not(None),
        )
    ).all()
    for row in rows:
        if isinstance(row.resolution, list):
            bind.execute(
                sa.update(rules)
                .where(rules.c.id == row.id)
                .values(resolution=[str(value).lower() for value in row.resolution])
            )


def downgrade() -> None:
    raise RuntimeError(
        "0040_normalize_duoyuanx_resolution_options is intentionally irreversible; "
        "the former mixed-case labels are not valid provider API values."
    )
