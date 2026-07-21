"""初始化 Core API 迁移基线。

Revision ID: 0001_core_base
Revises:
Create Date: 2026-07-16
"""

from typing import Sequence

revision: str = "0001_core_base"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """建立迁移基线；业务表由后续任务按域加入。"""


def downgrade() -> None:
    """移除迁移基线；当前没有业务表需要删除。"""
