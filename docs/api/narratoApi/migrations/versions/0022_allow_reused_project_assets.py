"""Allow retry drafts to reference the same immutable source upload.

Revision ID: 0022_allow_reused_project_assets
Revises: 0021_asset_sort_order
Create Date: 2026-08-04
"""

from __future__ import annotations

from alembic import op


revision = "0022_allow_reused_project_assets"
down_revision = "0021_asset_sort_order"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("assets") as batch_op:
        batch_op.drop_constraint("uq_assets_bucket_object_key", type_="unique")


def downgrade() -> None:
    with op.batch_alter_table("assets") as batch_op:
        batch_op.create_unique_constraint(
            "uq_assets_bucket_object_key", ["bucket", "object_key"]
        )
