"""建立最小编辑草稿快照表。

Revision ID: 0008_editor_revisions
Revises: 0007_workflow_reconciliation
Create Date: 2026-07-17
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0008_editor_revisions"
down_revision = "0007_workflow_reconciliation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """创建等待编辑阶段的不可变草稿快照表。"""

    op.create_table(
        "editor_revisions",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("content", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    """删除编辑草稿快照表。"""

    op.drop_table("editor_revisions")
