"""支持项目背景音乐和音频上传资产。

Revision ID: 0015_background_music
Revises: 0014_asset_duration
Create Date: 2026-07-22
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0015_background_music"
down_revision = "0014_asset_duration"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """扩展资产类型，并为每个项目建立一条可选 BGM 配置。"""

    with op.batch_alter_table("assets") as batch_op:
        batch_op.drop_constraint("ck_assets_type", type_="check")
        batch_op.create_check_constraint(
            "ck_assets_type", "asset_type IN ('video', 'subtitle', 'audio')"
        )
    op.create_table(
        "project_background_music",
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("asset_id", sa.String(length=64), nullable=False),
        sa.Column("volume", sa.Integer(), nullable=False, server_default="50"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("volume BETWEEN 0 AND 100", name="ck_project_bgm_volume"),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("project_id"),
    )


def downgrade() -> None:
    """删除可选 BGM 设置，并恢复原上传类型限制。"""

    op.drop_table("project_background_music")
    with op.batch_alter_table("assets") as batch_op:
        batch_op.drop_constraint("ck_assets_type", type_="check")
        batch_op.create_check_constraint(
            "ck_assets_type", "asset_type IN ('video', 'subtitle')"
        )
