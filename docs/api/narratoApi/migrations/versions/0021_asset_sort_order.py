"""Persist the user-defined order of project assets.

Revision ID: 0021_asset_sort_order
Revises: 0020_artifact_truth_gate
Create Date: 2026-08-04
"""

from __future__ import annotations

from collections import defaultdict

import sqlalchemy as sa
from alembic import op


revision = "0021_asset_sort_order"
down_revision = "0020_artifact_truth_gate"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("assets", sa.Column("sort_order", sa.Integer(), nullable=True))

    bind = op.get_bind()
    assets = sa.table(
        "assets",
        sa.column("id", sa.String),
        sa.column("project_id", sa.String),
        sa.column("asset_type", sa.String),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("sort_order", sa.Integer),
    )
    positions: defaultdict[tuple[str, str], int] = defaultdict(int)
    rows = bind.execute(
        sa.select(
            assets.c.id,
            assets.c.project_id,
            assets.c.asset_type,
        ).order_by(
            assets.c.project_id,
            assets.c.asset_type,
            assets.c.created_at,
            assets.c.id,
        )
    ).all()
    for asset_id, project_id, asset_type in rows:
        key = (project_id, asset_type)
        bind.execute(
            sa.update(assets)
            .where(assets.c.id == asset_id)
            .values(sort_order=positions[key])
        )
        positions[key] += 1

    with op.batch_alter_table("assets") as batch_op:
        batch_op.alter_column("sort_order", existing_type=sa.Integer(), nullable=False)
        batch_op.create_check_constraint(
            "ck_assets_sort_order", "sort_order >= 0"
        )


def downgrade() -> None:
    with op.batch_alter_table("assets") as batch_op:
        batch_op.drop_constraint("ck_assets_sort_order", type_="check")
        batch_op.drop_column("sort_order")
