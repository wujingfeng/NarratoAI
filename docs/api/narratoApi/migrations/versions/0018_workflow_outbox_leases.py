"""Add crash-recovery leases to workflow Outbox delivery.

Revision ID: 0018_workflow_outbox_leases
Revises: 0017_workflow_cancellation
Create Date: 2026-07-23
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0018_workflow_outbox_leases"
down_revision = "0017_workflow_cancellation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 部分早期环境通过最新 bootstrap schema 建表后仍停留在 0016 stamp；
    # 迁移必须接受这种“结构已存在、版本未推进”的状态，避免重复列中断升级。
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {item["name"] for item in inspector.get_columns("workflow_outbox")}
    if "dispatch_lease_id" not in columns:
        op.add_column(
            "workflow_outbox",
            sa.Column("dispatch_lease_id", sa.String(length=64), nullable=True),
        )
    if "dispatch_started_at" not in columns:
        op.add_column(
            "workflow_outbox",
            sa.Column("dispatch_started_at", sa.DateTime(timezone=True), nullable=True),
        )
    indexes = {item["name"] for item in inspector.get_indexes("workflow_outbox")}
    if "ix_workflow_outbox_sending_lease" not in indexes:
        op.create_index(
            "ix_workflow_outbox_sending_lease",
            "workflow_outbox",
            ["status", "dispatch_started_at"],
        )
    # 将升级前可能遗留的 sending 事件纳入租约回收；这些事件没有旧 lease，
    # 但其 created_at 足以作为保守的认领起点。
    op.execute(
        "UPDATE workflow_outbox SET dispatch_started_at = created_at "
        "WHERE status = 'sending' AND dispatch_started_at IS NULL"
    )


def downgrade() -> None:
    op.drop_index("ix_workflow_outbox_sending_lease", table_name="workflow_outbox")
    op.drop_column("workflow_outbox", "dispatch_started_at")
    op.drop_column("workflow_outbox", "dispatch_lease_id")
