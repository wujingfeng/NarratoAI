"""建立 Core OSS 产物登记表。

Revision ID: 0004_core_artifacts
Revises: 0003_core_capabilities
Create Date: 2026-07-17
"""

from typing import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_core_artifacts"
down_revision: str | None = "0003_core_capabilities"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """创建统一 Core Artifact 事实表。"""

    op.add_column(
        "core_tasks",
        sa.Column("initial_response", sa.JSON(), nullable=False, server_default="{}"),
    )

    op.create_table(
        "core_artifacts",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("core_task_id", sa.String(length=40), nullable=False),
        sa.Column("attempt_no", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=80), nullable=False),
        sa.Column("bucket", sa.String(length=255), nullable=False),
        sa.Column("object_key", sa.String(length=1024), nullable=False),
        sa.Column("url", sa.String(length=2048), nullable=False),
        sa.Column("content_type", sa.String(length=255), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("checksum", sa.String(length=80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["core_task_id"], ["core_tasks.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["core_task_id", "attempt_no"],
            ["core_task_attempts.core_task_id", "core_task_attempts.attempt_no"],
            name="fk_core_artifacts_task_attempt",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint("attempt_no > 0", name="ck_core_artifacts_attempt_positive"),
        sa.CheckConstraint("size > 0", name="ck_core_artifacts_size_positive"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("object_key", name="uq_core_artifacts_object_key"),
    )
    op.create_index(
        "ix_core_artifacts_task_attempt",
        "core_artifacts",
        ["core_task_id", "attempt_no"],
        unique=False,
    )
    op.create_table(
        "core_dispatch_outbox",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("core_task_id", sa.String(length=40), nullable=False),
        sa.Column("state_version", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "sent",
                name="core_dispatch_status",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.String(length=80), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("recover_after", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["core_task_id"], ["core_tasks.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "core_task_id", "state_version", name="uq_core_dispatch_task_state"
        ),
    )
    op.create_index(
        "ix_core_dispatch_pending",
        "core_dispatch_outbox",
        ["status", "available_at"],
        unique=False,
    )
    op.create_index(
        "ix_core_dispatch_recovery",
        "core_dispatch_outbox",
        ["status", "recover_after"],
        unique=False,
    )
    bind = op.get_bind()
    json_expression = (
        "json_build_object('core_task_id', id, 'status', 'queued')"
        if bind.dialect.name == "postgresql"
        else "json_object('core_task_id', id, 'status', 'queued')"
    )
    op.execute(sa.text(f"UPDATE core_tasks SET initial_response = {json_expression}"))
    # 0003 已存在的 queued/retry_wait 必须在同次升级获得可投递事实；running
    # 由 lease/heartbeat recovery scanner 判定，避免迁移时误判活跃 Worker。
    op.execute(
        sa.text(
            """
            INSERT INTO core_dispatch_outbox (
                id, core_task_id, state_version, status, available_at,
                attempt_count, last_error, sent_at, recover_after, created_at, updated_at
            )
            SELECT id, id, state_version, 'pending', COALESCE(updated_at, created_at),
                   0, NULL, NULL, NULL, created_at, updated_at
            FROM core_tasks
            WHERE status IN ('queued', 'retry_wait')
            """
        )
    )


def downgrade() -> None:
    """删除 Core Artifact 表。"""

    op.drop_index("ix_core_dispatch_pending", table_name="core_dispatch_outbox")
    op.drop_index("ix_core_dispatch_recovery", table_name="core_dispatch_outbox")
    op.drop_table("core_dispatch_outbox")
    op.drop_index("ix_core_artifacts_task_attempt", table_name="core_artifacts")
    op.drop_table("core_artifacts")
    op.drop_column("core_tasks", "initial_response")
