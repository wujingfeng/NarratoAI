"""建立可变编辑草稿表。

Revision ID: 0009_editor_drafts
Revises: 0008_editor_revisions
Create Date: 2026-07-17
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0009_editor_drafts"
down_revision = "0008_editor_revisions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """创建每项目唯一的当前可变编辑草稿表。"""

    op.create_table(
        "editor_drafts",
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("content", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("project_id"),
        sa.UniqueConstraint("id"),
    )


def downgrade() -> None:
    """删除可变编辑草稿表。"""

    op.drop_table("editor_drafts")
