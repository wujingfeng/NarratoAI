"""建立用户项目和上传资产表。

Revision ID: 0004_projects_assets
Revises: 0003_billing
Create Date: 2026-07-17
"""

from typing import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_projects_assets"
down_revision: str | None = "0003_billing"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """创建项目归属、状态及 OSS 资产持久化基础。"""

    op.create_table(
        "projects",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("product", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("is_locked", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('draft', 'uploading', 'validating', 'ready', 'queued', "
            "'analyzing', 'waiting_for_edit', 'render_queued', 'rendering', "
            "'completed', 'failed', 'deleting', 'deleted')",
            name="ck_projects_status",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_projects_user_created", "projects", ["user_id", "created_at"])
    op.create_table(
        "assets",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("asset_type", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("bucket", sa.String(length=255), nullable=False),
        sa.Column("object_key", sa.String(length=1024), nullable=False),
        sa.Column("cdn_url", sa.String(length=2048), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "asset_type IN ('video', 'subtitle')", name="ck_assets_type"
        ),
        sa.CheckConstraint(
            "status IN ('validating', 'ready', 'invalid')", name="ck_assets_status"
        ),
        sa.CheckConstraint(
            "length(filename) BETWEEN 1 AND 255", name="ck_assets_filename_length"
        ),
        sa.CheckConstraint("size_bytes >= 0", name="ck_assets_size_bytes"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("bucket", "object_key", name="uq_assets_bucket_object_key"),
    )
    op.create_index("ix_assets_project_type", "assets", ["project_id", "asset_type"])
    op.create_index("ix_assets_user_created", "assets", ["user_id", "created_at"])


def downgrade() -> None:
    """以依赖反序删除资产和项目表。"""

    op.drop_index("ix_assets_user_created", table_name="assets")
    op.drop_index("ix_assets_project_type", table_name="assets")
    op.drop_table("assets")
    op.drop_index("ix_projects_user_created", table_name="projects")
    op.drop_table("projects")
