"""Persist Business API ownership of AI video provider polling.

Revision ID: 0030_ai_video_provider_polling
Revises: 0029_general_models_comments
"""

from typing import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0030_ai_video_provider_polling"
down_revision: str | None = "0029_general_models_comments"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_COMMENTS = {
    "next_poll_at": "下一次允许 Business Worker 轮询供应商的时间（UTC）。",
    "poll_lease_token": "轮询 Worker 的短租约令牌，防止多 Worker 重复处理。",
    "poll_lease_until": "轮询 Worker 租约的过期时间（UTC）。",
    "poll_error_count": "连续供应商轮询或恢复提交失败次数，用于指数退避。",
    "last_polled_at": "最近一次 Business Worker 发起供应商轮询的时间（UTC）。",
}


def _comment_postgresql() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    for column_name, comment in _COMMENTS.items():
        literal = comment.replace("'", "''")
        op.execute(
            sa.text(
                f"COMMENT ON COLUMN ai_video_tasks.{column_name} IS '{literal}'"
            )
        )


def upgrade() -> None:
    """Add durable poll scheduling, leases, and failure backoff state."""

    with op.batch_alter_table("ai_video_tasks") as batch_op:
        batch_op.add_column(sa.Column("next_poll_at", sa.DateTime(timezone=True)))
        batch_op.add_column(sa.Column("poll_lease_token", sa.String(length=64)))
        batch_op.add_column(sa.Column("poll_lease_until", sa.DateTime(timezone=True)))
        batch_op.add_column(
            sa.Column(
                "poll_error_count",
                sa.Integer(),
                nullable=False,
                server_default="0",
            )
        )
        batch_op.add_column(sa.Column("last_polled_at", sa.DateTime(timezone=True)))

    # Existing in-flight provider tasks must enter the first sweep without
    # waiting for a browser refresh. Submitting rows without a remote id are
    # deliberately left NULL and recovered only after the worker grace period.
    op.execute(
        sa.text(
            "UPDATE ai_video_tasks SET next_poll_at = CURRENT_TIMESTAMP "
            "WHERE status IN ('queued', 'processing') AND provider_task_id IS NOT NULL"
        )
    )
    op.create_index(
        "ix_ai_video_tasks_poll_due",
        "ai_video_tasks",
        ["status", "next_poll_at"],
    )
    _comment_postgresql()


def downgrade() -> None:
    op.drop_index("ix_ai_video_tasks_poll_due", table_name="ai_video_tasks")
    with op.batch_alter_table("ai_video_tasks") as batch_op:
        batch_op.drop_column("last_polled_at")
        batch_op.drop_column("poll_error_count")
        batch_op.drop_column("poll_lease_until")
        batch_op.drop_column("poll_lease_token")
        batch_op.drop_column("next_poll_at")
