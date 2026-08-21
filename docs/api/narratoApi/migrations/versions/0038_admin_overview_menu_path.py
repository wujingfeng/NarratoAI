"""Align the seeded admin overview menu with the standalone UI route.

Revision ID: 0038_admin_overview_menu_path
Revises: 0037_register_duoyuanx_provider
Create Date: 2026-08-17
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0038_admin_overview_menu_path"
down_revision: str | None = "0037_register_duoyuanx_provider"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """修正已执行 0036 的环境中的固定菜单路径。"""
    op.execute(
        sa.text(
            "UPDATE admin_menus SET path = '/overview' "
            "WHERE id = 'menu_dashboard' AND path = '/dashboard'"
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE admin_menus SET path = '/dashboard' "
            "WHERE id = 'menu_dashboard' AND path = '/overview'"
        )
    )
