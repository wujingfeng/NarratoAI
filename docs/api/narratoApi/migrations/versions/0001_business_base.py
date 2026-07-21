"""初始化 narratoApi 业务迁移基线。

Revision ID: 0001_business_base
Revises:
Create Date: 2026-07-17
"""

from typing import Sequence

revision: str = "0001_business_base"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """建立空迁移基线，领域表由后续任务加入。"""


def downgrade() -> None:
    """移除空迁移基线，无业务表需要删除。"""
