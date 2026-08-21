"""Align seeded admin-menu links with the standalone UI routes.

Revision ID: 0039_admin_menu_ui_paths
Revises: 0038_admin_overview_menu_path
Create Date: 2026-08-17
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0039_admin_menu_ui_paths"
down_revision: str | None = "0038_admin_overview_menu_path"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_PATHS = {
    "menu_tasks_drama": "/tasks/short-drama",
    "menu_tasks_translation": "/tasks/video-translation",
    "menu_tasks_ai": "/tasks/ai-video",
    "menu_models": "/config/models",
    "menu_system": "/config/system",
    "menu_operation_logs": "/logs/operations",
    "menu_credit_logs": "/logs/credits",
}

_LEGACY_PATHS = {
    "menu_tasks_drama": "/tasks?category=short_drama",
    "menu_tasks_translation": "/tasks?category=video_translation",
    "menu_tasks_ai": "/tasks?category=ai_video",
    "menu_models": "/models",
    "menu_system": "/system-configs",
    "menu_operation_logs": "/operation-logs",
    "menu_credit_logs": "/credit-ledger",
}


def _apply_paths(paths: dict[str, str]) -> None:
    for menu_id, path in paths.items():
        op.execute(
            sa.text("UPDATE admin_menus SET path = :path WHERE id = :menu_id").bindparams(
                path=path, menu_id=menu_id
            )
        )


def upgrade() -> None:
    _apply_paths(_PATHS)


def downgrade() -> None:
    _apply_paths(_LEGACY_PATHS)
