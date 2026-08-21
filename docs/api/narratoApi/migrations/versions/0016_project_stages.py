"""持久化不可逆的短剧解说阶段与参数快照。

Revision ID: 0016_project_stages
Revises: 0015_background_music
Create Date: 2026-07-23
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0016_project_stages"
down_revision = "0015_background_music"
branch_labels = None
depends_on = None

_STAGES = "'created', 'settings', 'analysis', 'edit', 'generate', 'export'"


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column("current_stage", sa.String(length=16), nullable=False, server_default="created"),
    )
    # SQLite 不支持 ALTER TABLE ADD CONSTRAINT；测试/本地 SQLite 依靠 ORM
    # metadata 的同名约束，生产 PostgreSQL 保持数据库级约束。
    if op.get_bind().dialect.name != "sqlite":
        op.create_check_constraint(
            "ck_projects_current_stage",
            "projects",
            f"current_stage IN ({_STAGES})",
        )
    # 旧项目按已有执行状态映射到最接近的不可逆阶段，避免等待编辑项目被误锁。
    op.execute(
        "UPDATE projects SET current_stage = CASE "
        "WHEN status IN ('waiting_for_edit') THEN 'edit' "
        "WHEN status IN ('render_queued', 'rendering') THEN 'generate' "
        "WHEN status IN ('completed') THEN 'export' "
        "WHEN status IN ('queued', 'analyzing') THEN 'analysis' "
        "WHEN status IN ('ready', 'uploading', 'validating') THEN 'settings' "
        "ELSE 'created' END"
    )
    op.create_table(
        "project_narration_settings",
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("settings", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("project_id"),
    )
    op.create_table(
        "project_stage_history",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("from_stage", sa.String(length=16), nullable=True),
        sa.Column("to_stage", sa.String(length=16), nullable=False),
        sa.Column("settings_snapshot", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "to_stage", name="uq_project_stage_history_stage"),
    )
    op.create_index(
        "ix_project_stage_history_project_created",
        "project_stage_history",
        ["project_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_project_stage_history_project_created", table_name="project_stage_history")
    op.drop_table("project_stage_history")
    op.drop_table("project_narration_settings")
    if op.get_bind().dialect.name != "sqlite":
        op.drop_constraint("ck_projects_current_stage", "projects", type_="check")
    op.drop_column("projects", "current_stage")
