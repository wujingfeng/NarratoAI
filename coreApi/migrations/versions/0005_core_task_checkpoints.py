"""建立可跨 attempt 复用的 Core 任务阶段检查点。

Revision ID: 0005_core_task_checkpoints
Revises: 0004_core_artifacts
Create Date: 2026-08-04
"""

from typing import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_core_task_checkpoints"
down_revision: str | None = "0004_core_artifacts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """创建持久检查点与检查点文件事实表。"""

    op.add_column(
        "core_tasks",
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_table(
        "core_task_checkpoints",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("core_task_id", sa.String(length=40), nullable=False),
        sa.Column("stage", sa.String(length=80), nullable=False),
        sa.Column("stage_version", sa.Integer(), nullable=False),
        sa.Column("input_digest", sa.String(length=64), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "ready",
                "invalid",
                name="core_checkpoint_status",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("manifest", sa.JSON(), nullable=False),
        sa.Column("created_by_attempt_no", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("invalidated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "created_by_attempt_no > 0",
            name="ck_core_task_checkpoint_attempt_positive",
        ),
        sa.ForeignKeyConstraint(
            ["core_task_id"], ["core_tasks.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "core_task_id",
            "stage",
            "stage_version",
            "input_digest",
            name="uq_core_task_checkpoint_identity",
        ),
    )
    op.create_index(
        "ix_core_task_checkpoints_lookup",
        "core_task_checkpoints",
        ["core_task_id", "stage", "status"],
        unique=False,
    )
    op.create_table(
        "core_checkpoint_artifacts",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("checkpoint_id", sa.String(length=40), nullable=False),
        sa.Column("kind", sa.String(length=80), nullable=False),
        sa.Column("relative_path", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=255), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("checksum", sa.String(length=80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "size > 0", name="ck_core_checkpoint_artifact_size_positive"
        ),
        sa.ForeignKeyConstraint(
            ["checkpoint_id"], ["core_task_checkpoints.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "checkpoint_id", "kind", name="uq_core_checkpoint_artifact_kind"
        ),
    )
    op.create_index(
        "ix_core_checkpoint_artifacts_checkpoint",
        "core_checkpoint_artifacts",
        ["checkpoint_id"],
        unique=False,
    )


def downgrade() -> None:
    """删除阶段检查点表。"""

    op.drop_index(
        "ix_core_checkpoint_artifacts_checkpoint",
        table_name="core_checkpoint_artifacts",
    )
    op.drop_table("core_checkpoint_artifacts")
    op.drop_index(
        "ix_core_task_checkpoints_lookup", table_name="core_task_checkpoints"
    )
    op.drop_table("core_task_checkpoints")
    op.drop_column("core_tasks", "retry_count")
