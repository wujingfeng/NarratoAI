"""增加工作流 Core 结果收口的持久化去重键。

Revision ID: 0007_workflow_reconciliation
Revises: 0006_workflows
Create Date: 2026-07-17
"""
from typing import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_workflow_reconciliation"
down_revision: str | None = "0006_workflows"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


def upgrade() -> None:
    """为节点尝试增加版本，并创建事件与版本的去重事实表。"""

    with op.batch_alter_table("workflow_node_attempts") as batch_op:
        batch_op.add_column(sa.Column("state_version", sa.Integer(), nullable=False, server_default="0"))
        batch_op.create_check_constraint(
            "ck_workflow_node_attempts_state_version", "state_version >= 0"
        )
    op.create_table(
        "workflow_reconciliation_events",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("workflow_node_attempt_id", sa.String(length=64), nullable=False),
        sa.Column("event_id", sa.String(length=128), nullable=False),
        sa.Column("state_version", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "state_version >= 0", name="ck_workflow_reconciliation_events_state_version"
        ),
        sa.ForeignKeyConstraint(
            ["workflow_node_attempt_id"], ["workflow_node_attempts.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workflow_node_attempt_id", "event_id", name="uq_workflow_reconciliation_events_attempt_event"
        ),
        sa.UniqueConstraint(
            "workflow_node_attempt_id",
            "state_version",
            name="uq_workflow_reconciliation_events_attempt_state_version",
        ),
    )


def downgrade() -> None:
    """删除 Task 14D 的收口去重结构。"""

    op.drop_table("workflow_reconciliation_events")
    with op.batch_alter_table("workflow_node_attempts") as batch_op:
        batch_op.drop_constraint("ck_workflow_node_attempts_state_version", type_="check")
        batch_op.drop_column("state_version")
