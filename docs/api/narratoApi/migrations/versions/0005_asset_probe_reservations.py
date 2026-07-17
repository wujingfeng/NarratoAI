"""持久化 Core 探测任务和有限 OSS 策略预留。

Revision ID: 0005_asset_probe_reservations
Revises: 0004_projects_assets
Create Date: 2026-07-17
"""
from typing import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_asset_probe_reservations"
down_revision: str | None = "0004_projects_assets"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


def upgrade() -> None:
    """追加异步探测关联和过期预留字段。"""

    op.add_column("assets", sa.Column("core_task_id", sa.String(length=128), nullable=True))
    op.add_column(
        "assets", sa.Column("reservation_expires_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    """移除 Task 13B 追加字段。"""

    op.drop_column("assets", "reservation_expires_at")
    op.drop_column("assets", "core_task_id")
