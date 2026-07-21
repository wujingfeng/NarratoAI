"""建立终态项目删除请求审计表。

Revision ID: 0011_project_deletion_jobs
Revises: 0010_registered_artifacts
Create Date: 2026-07-17
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0011_project_deletion_jobs"
down_revision = "0010_registered_artifacts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """创建幂等删除请求审计记录，不创建任何实际删除执行器。"""

    op.create_table(
        "deletion_jobs",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('pending')", name="ck_deletion_jobs_status"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", name="uq_deletion_jobs_project_id"),
    )
    op.create_index(
        "ix_deletion_jobs_user_created",
        "deletion_jobs",
        ["user_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    """按依赖顺序移除项目删除审计表。"""

    op.drop_index("ix_deletion_jobs_user_created", table_name="deletion_jobs")
    op.drop_table("deletion_jobs")
