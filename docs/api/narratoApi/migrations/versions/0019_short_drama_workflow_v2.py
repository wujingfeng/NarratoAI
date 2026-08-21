"""Publish the executable short-drama narration V2 workflow snapshot.

Revision ID: 0019_short_drama_workflow_v2
Revises: 0018_workflow_outbox_leases
Create Date: 2026-08-03
"""

from __future__ import annotations

from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op


revision = "0019_short_drama_workflow_v2"
down_revision = "0018_workflow_outbox_leases"
branch_labels = None
depends_on = None


_DEFINITION = {
    "nodes": [
        {"name": "subtitle_recognition", "depends_on": []},
        {"name": "plot_structure", "depends_on": ["subtitle_recognition"]},
        {"name": "conflict_highlights", "depends_on": ["plot_structure"]},
        {"name": "highlight_scoring", "depends_on": ["conflict_highlights"]},
        {"name": "script_generation", "depends_on": ["highlight_scoring"]},
        {"name": "waiting_for_edit", "depends_on": ["script_generation"], "retryable": False, "manual_gate": True},
        {"name": "video_render", "depends_on": ["waiting_for_edit"]},
        {"name": "publish_artifacts", "depends_on": ["video_render"], "retryable": False, "manual_gate": True},
    ]
}


def upgrade() -> None:
    table = sa.table(
        "workflow_template_snapshots",
        sa.column("id", sa.String),
        sa.column("template_name", sa.String),
        sa.column("version", sa.String),
        sa.column("definition", sa.JSON),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    bind = op.get_bind()
    exists = bind.execute(
        sa.text(
            "SELECT 1 FROM workflow_template_snapshots "
            "WHERE template_name = :name AND version = :version"
        ),
        {"name": "short_drama_narration", "version": "short_drama_narration_v2"},
    ).scalar()
    if exists is None:
        op.bulk_insert(
            table,
            [{
                "id": "tpl_short_drama_narration_v2",
                "template_name": "short_drama_narration",
                "version": "short_drama_narration_v2",
                "definition": _DEFINITION,
                "created_at": datetime.now(timezone.utc),
            }],
        )


def downgrade() -> None:
    op.execute(
        "DELETE FROM workflow_template_snapshots "
        "WHERE template_name = 'short_drama_narration' "
        "AND version = 'short_drama_narration_v2'"
    )
