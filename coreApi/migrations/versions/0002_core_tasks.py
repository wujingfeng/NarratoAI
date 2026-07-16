"""建立 Core Task、Attempt 和 Callback Outbox。

Revision ID: 0002_core_tasks
Revises: 0001_core_base
Create Date: 2026-07-16
"""

from typing import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_core_tasks"
down_revision: str | None = "0001_core_base"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

core_task_status = sa.Enum(
    "queued",
    "running",
    "retry_wait",
    "succeeded",
    "failed",
    name="core_task_status",
    native_enum=False,
    create_constraint=True,
)
core_attempt_status = sa.Enum(
    "running",
    "succeeded",
    "failed",
    "expired",
    name="core_attempt_status",
    native_enum=False,
    create_constraint=True,
)
callback_outbox_status = sa.Enum(
    "pending",
    "sent",
    name="callback_outbox_status",
    native_enum=False,
    create_constraint=True,
)


def upgrade() -> None:
    """创建可靠 Core Task 运行时所需的数据表和唯一约束。"""

    op.create_table(
        "core_tasks",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("task_type", sa.String(length=80), nullable=False),
        sa.Column("caller", sa.String(length=120), nullable=False),
        sa.Column("caller_task_id", sa.String(length=80), nullable=True),
        sa.Column("idempotency_scope", sa.String(length=512), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("request_digest", sa.String(length=64), nullable=False),
        sa.Column("input_snapshot", sa.JSON(), nullable=False),
        sa.Column("status", core_task_status, nullable=False),
        sa.Column("phase", sa.String(length=80), nullable=True),
        sa.Column("progress", sa.Integer(), nullable=False),
        sa.Column("state_version", sa.Integer(), nullable=False),
        sa.Column("current_attempt_no", sa.Integer(), nullable=False),
        sa.Column("max_retries", sa.Integer(), nullable=False),
        sa.Column("error", sa.JSON(), nullable=True),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "idempotency_scope", name="uq_core_tasks_idempotency_scope"
        ),
    )
    op.create_index(
        "ix_core_tasks_status_created_at",
        "core_tasks",
        ["status", "created_at"],
        unique=False,
    )

    op.create_table(
        "core_task_attempts",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("core_task_id", sa.String(length=40), nullable=False),
        sa.Column("attempt_no", sa.Integer(), nullable=False),
        sa.Column("status", core_attempt_status, nullable=False),
        sa.Column("lease_token", sa.String(length=128), nullable=False),
        sa.Column("lease_version", sa.Integer(), nullable=False),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.JSON(), nullable=True),
        sa.Column("late_result_audit", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(
            ["core_task_id"], ["core_tasks.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "core_task_id", "attempt_no", name="uq_core_task_attempts_task_no"
        ),
    )
    op.create_index(
        "ix_core_task_attempts_lease_expiry",
        "core_task_attempts",
        ["status", "lease_expires_at"],
        unique=False,
    )

    op.create_table(
        "callback_outbox",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("event_id", sa.String(length=80), nullable=False),
        sa.Column("core_task_id", sa.String(length=40), nullable=False),
        sa.Column("attempt_no", sa.Integer(), nullable=False),
        sa.Column("state_version", sa.Integer(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", callback_outbox_status, nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["core_task_id"], ["core_tasks.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id", name="uq_callback_outbox_event_id"),
        sa.UniqueConstraint(
            "core_task_id",
            "state_version",
            name="uq_callback_outbox_task_state_version",
        ),
    )
    op.create_index(
        "ix_callback_outbox_pending",
        "callback_outbox",
        ["status", "next_attempt_at"],
        unique=False,
    )


def downgrade() -> None:
    """按依赖逆序移除 Core Task 运行时数据表。"""

    op.drop_index("ix_callback_outbox_pending", table_name="callback_outbox")
    op.drop_table("callback_outbox")
    op.drop_index(
        "ix_core_task_attempts_lease_expiry", table_name="core_task_attempts"
    )
    op.drop_table("core_task_attempts")
    op.drop_index("ix_core_tasks_status_created_at", table_name="core_tasks")
    op.drop_table("core_tasks")
