"""持久化可恢复项目删除 Worker 状态。

Revision ID: 0013_project_deletion_worker
Revises: 0012_artifact_core_manifest_metadata
Create Date: 2026-07-17
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0013_project_deletion_worker"
down_revision = "0012_artifact_core_manifest_metadata"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """为删除审计记录增加重试状态与错误摘要。"""

    with op.batch_alter_table("deletion_jobs") as batch_op:
        batch_op.drop_constraint("ck_deletion_jobs_status", type_="check")
        batch_op.add_column(
            sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0")
        )
        batch_op.add_column(
            sa.Column("last_error", sa.String(length=128), nullable=True)
        )
        batch_op.create_check_constraint(
            "ck_deletion_jobs_status",
            "status IN ('pending', 'retryable_failed', 'completed')",
        )


def downgrade() -> None:
    """恢复仅允许待执行删除审计记录的初始模型。"""

    with op.batch_alter_table("deletion_jobs") as batch_op:
        batch_op.drop_constraint("ck_deletion_jobs_status", type_="check")
        batch_op.drop_column("last_error")
        batch_op.drop_column("attempt_count")
        batch_op.create_check_constraint(
            "ck_deletion_jobs_status", "status IN ('pending')"
        )
