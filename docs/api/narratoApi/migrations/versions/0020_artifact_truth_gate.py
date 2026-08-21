"""Remove legacy demo drafts and enforce one final artifact per kind.

Revision ID: 0020_artifact_truth_gate
Revises: 0019_short_drama_workflow_v2
Create Date: 2026-08-03
"""

from __future__ import annotations

import json
from collections.abc import Mapping

import sqlalchemy as sa
from alembic import op


revision = "0020_artifact_truth_gate"
down_revision = "0019_short_drama_workflow_v2"
branch_labels = None
depends_on = None


def _contains_legacy_demo_media(content: object) -> bool:
    if isinstance(content, str):
        try:
            content = json.loads(content)
        except json.JSONDecodeError:
            return False
    if not isinstance(content, Mapping):
        return False
    clips = content.get("clips")
    if not isinstance(clips, list):
        return False
    return any(
        isinstance(clip, Mapping)
        and isinstance(clip.get("asset_id"), str)
        and clip["asset_id"].startswith("/media/narration-editor/")
        for clip in clips
    )


def upgrade() -> None:
    bind = op.get_bind()
    drafts = sa.table(
        "editor_drafts",
        sa.column("project_id", sa.String),
        sa.column("content", sa.JSON),
    )
    legacy_project_ids = [
        project_id
        for project_id, content in bind.execute(
            sa.select(drafts.c.project_id, drafts.c.content)
        )
        if _contains_legacy_demo_media(content)
    ]
    if legacy_project_ids:
        bind.execute(
            sa.delete(drafts).where(drafts.c.project_id.in_(legacy_project_ids))
        )

    inspector = sa.inspect(bind)
    unique_constraints = {
        item["name"] for item in inspector.get_unique_constraints("artifacts")
    }
    unique_indexes = {
        item["name"]
        for item in inspector.get_indexes("artifacts")
        if item.get("unique")
    }
    if "uq_artifacts_project_kind" not in unique_constraints | unique_indexes:
        with op.batch_alter_table("artifacts") as batch_op:
            batch_op.create_unique_constraint(
                "uq_artifacts_project_kind", ["project_id", "kind"]
            )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "uq_artifacts_project_kind" in {
        item["name"] for item in inspector.get_unique_constraints("artifacts")
    }:
        with op.batch_alter_table("artifacts") as batch_op:
            batch_op.drop_constraint(
                "uq_artifacts_project_kind", type_="unique"
            )
