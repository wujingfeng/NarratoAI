"""建立项目可导出产物登记表。

Revision ID: 0010_registered_artifacts
Revises: 0009_editor_drafts
Create Date: 2026-07-17
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0010_registered_artifacts"
down_revision = "0009_editor_drafts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """创建按项目归属的最小可导出产物登记表。"""

    op.create_table(
        "artifacts",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("cdn_url", sa.String(length=2048), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_artifacts_project_created",
        "artifacts",
        ["project_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    """删除项目可导出产物登记表。"""

    op.drop_index("ix_artifacts_project_created", table_name="artifacts")
    op.drop_table("artifacts")
