"""持久化版本化工作流 DAG、节点尝试和 Outbox。

Revision ID: 0006_workflows
Revises: 0005_asset_probe_reservations
Create Date: 2026-07-17
"""

from typing import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_workflows"
down_revision: str | None = "0005_asset_probe_reservations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


def upgrade() -> None:
    """创建工作流持久化所需的数据库结构，不启动运行时行为。"""

    op.create_table(
        "workflow_template_snapshots",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("template_name", sa.String(length=128), nullable=False),
        sa.Column("version", sa.String(length=64), nullable=False),
        sa.Column("definition", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "template_name", "version", name="uq_workflow_templates_name_version"
        ),
    )
    op.create_table(
        "workflows",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("template_snapshot_id", sa.String(length=64), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("state_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "state IN ('draft', 'queued', 'running', 'waiting_for_edit', "
            "'render_queued', 'completed', 'failed')",
            name="ck_workflows_state",
        ),
        sa.CheckConstraint("state_version >= 0", name="ck_workflows_state_version"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["template_snapshot_id"],
            ["workflow_template_snapshots.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", name="uq_workflows_project_id"),
    )
    op.create_index("ix_workflows_user_created", "workflows", ["user_id", "created_at"])
    op.create_table(
        "workflow_nodes",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("workflow_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("depends_on", sa.JSON(), nullable=False),
        sa.Column("retryable", sa.Boolean(), nullable=False),
        sa.Column("manual_gate", sa.Boolean(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "state IN ('queued', 'running', 'waiting_for_edit', 'completed', 'failed')",
            name="ck_workflow_nodes_state",
        ),
        sa.CheckConstraint("max_attempts >= 1", name="ck_workflow_nodes_max_attempts"),
        sa.ForeignKeyConstraint(["workflow_id"], ["workflows.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workflow_id", "name", name="uq_workflow_nodes_workflow_name"
        ),
    )
    op.create_index(
        "ix_workflow_nodes_workflow_state", "workflow_nodes", ["workflow_id", "state"]
    )
    op.create_table(
        "workflow_node_attempts",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("workflow_node_id", sa.String(length=64), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("core_task_id", sa.String(length=128), nullable=True),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "state IN ('queued', 'running', 'completed', 'failed')",
            name="ck_workflow_node_attempts_state",
        ),
        sa.CheckConstraint(
            "attempt_number >= 1", name="ck_workflow_node_attempts_number"
        ),
        sa.ForeignKeyConstraint(
            ["workflow_node_id"], ["workflow_nodes.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "core_task_id", name="uq_workflow_node_attempts_core_task_id"
        ),
        sa.UniqueConstraint(
            "workflow_node_id",
            "attempt_number",
            name="uq_workflow_node_attempts_node_number",
        ),
    )
    op.create_index(
        "ix_workflow_node_attempts_node_state",
        "workflow_node_attempts",
        ["workflow_node_id", "state"],
    )
    op.create_table(
        "workflow_outbox",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("workflow_id", sa.String(length=64), nullable=False),
        sa.Column("workflow_node_id", sa.String(length=64), nullable=True),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending', 'sending', 'sent', 'dead')",
            name="ck_workflow_outbox_status",
        ),
        sa.ForeignKeyConstraint(["workflow_id"], ["workflows.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["workflow_node_id"], ["workflow_nodes.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "idempotency_key", name="uq_workflow_outbox_idempotency_key"
        ),
    )
    op.create_index(
        "ix_workflow_outbox_status_created", "workflow_outbox", ["status", "created_at"]
    )


def downgrade() -> None:
    """删除本迁移创建的工作流表。"""

    op.drop_index("ix_workflow_outbox_status_created", table_name="workflow_outbox")
    op.drop_table("workflow_outbox")
    op.drop_index(
        "ix_workflow_node_attempts_node_state", table_name="workflow_node_attempts"
    )
    op.drop_table("workflow_node_attempts")
    op.drop_index("ix_workflow_nodes_workflow_state", table_name="workflow_nodes")
    op.drop_table("workflow_nodes")
    op.drop_index("ix_workflows_user_created", table_name="workflows")
    op.drop_table("workflows")
    op.drop_table("workflow_template_snapshots")
