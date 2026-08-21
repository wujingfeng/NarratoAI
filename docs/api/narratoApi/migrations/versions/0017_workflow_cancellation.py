"""Add cancellation terminal states for workflow propagation.

Revision ID: 0017_workflow_cancellation
Revises: 0016_project_stages
Create Date: 2026-07-23
"""

from __future__ import annotations

from alembic import op

revision = "0017_workflow_cancellation"
down_revision = "0016_project_stages"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # SQLite cannot alter CHECK constraints; production PostgreSQL gets explicit
    # replacement constraints. Fresh installs use ORM metadata / schema SQL.
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.drop_constraint("ck_projects_status", "projects", type_="check")
    op.create_check_constraint(
        "ck_projects_status", "projects",
        "status IN ('draft', 'uploading', 'validating', 'ready', 'queued', 'analyzing', "
        "'waiting_for_edit', 'render_queued', 'rendering', 'completed', 'failed', "
        "'cancelled', 'deleting', 'deleted')",
    )
    op.drop_constraint("ck_workflows_state", "workflows", type_="check")
    op.create_check_constraint(
        "ck_workflows_state", "workflows",
        "state IN ('draft', 'queued', 'running', 'waiting_for_edit', 'render_queued', "
        "'completed', 'failed', 'cancelled')",
    )
    op.drop_constraint("ck_workflow_nodes_state", "workflow_nodes", type_="check")
    op.create_check_constraint(
        "ck_workflow_nodes_state", "workflow_nodes",
        "state IN ('queued', 'running', 'waiting_for_edit', 'completed', 'failed', 'cancelled')",
    )
    op.drop_constraint("ck_workflow_node_attempts_state", "workflow_node_attempts", type_="check")
    op.create_check_constraint(
        "ck_workflow_node_attempts_state", "workflow_node_attempts",
        "state IN ('queued', 'running', 'completed', 'failed', 'cancelled')",
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.drop_constraint("ck_projects_status", "projects", type_="check")
    op.create_check_constraint(
        "ck_projects_status", "projects",
        "status IN ('draft', 'uploading', 'validating', 'ready', 'queued', 'analyzing', "
        "'waiting_for_edit', 'render_queued', 'rendering', 'completed', 'failed', "
        "'deleting', 'deleted')",
    )
    op.drop_constraint("ck_workflows_state", "workflows", type_="check")
    op.create_check_constraint(
        "ck_workflows_state", "workflows",
        "state IN ('draft', 'queued', 'running', 'waiting_for_edit', 'render_queued', "
        "'completed', 'failed')",
    )
    op.drop_constraint("ck_workflow_nodes_state", "workflow_nodes", type_="check")
    op.create_check_constraint(
        "ck_workflow_nodes_state", "workflow_nodes",
        "state IN ('queued', 'running', 'waiting_for_edit', 'completed', 'failed')",
    )
    op.drop_constraint("ck_workflow_node_attempts_state", "workflow_node_attempts", type_="check")
    op.create_check_constraint(
        "ck_workflow_node_attempts_state", "workflow_node_attempts",
        "state IN ('queued', 'running', 'completed', 'failed')",
    )
