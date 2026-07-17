"""持久化 Core 剪映 Manifest 资源元数据。

Revision ID: 0012_artifact_core_manifest_metadata
Revises: 0011_project_deletion_jobs
Create Date: 2026-07-17
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0012_artifact_core_manifest_metadata"
down_revision = "0011_project_deletion_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """为既有产物登记补充 Core 剪映资源描述字段。"""

    with op.batch_alter_table("artifacts") as batch_op:
        batch_op.add_column(sa.Column("size", sa.BigInteger(), nullable=True))
        batch_op.add_column(sa.Column("checksum", sa.String(length=72), nullable=True))
        batch_op.add_column(
            sa.Column("content_type", sa.String(length=255), nullable=True)
        )
        batch_op.add_column(sa.Column("width", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("height", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("duration", sa.Float(), nullable=True))


def downgrade() -> None:
    """删除 Core 剪映资源描述字段。"""

    with op.batch_alter_table("artifacts") as batch_op:
        batch_op.drop_column("duration")
        batch_op.drop_column("height")
        batch_op.drop_column("width")
        batch_op.drop_column("content_type")
        batch_op.drop_column("checksum")
        batch_op.drop_column("size")
