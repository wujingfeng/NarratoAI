"""Register the documented Duoyuanx adapter for legacy video provider rows.

Revision ID: 0037_register_duoyuanx_provider
Revises: 0036_admin_rbac
Create Date: 2026-08-17

Early operational rows used ``provider_code=volcengine`` while pointing at the
Duoyuanx endpoint.  There is no matching adapter for that generic code.  Map
unambiguous Duoyuanx rows to the concrete adapter code and add the documented
per-task GET URL when it was not configured.
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0037_register_duoyuanx_provider"
down_revision: str | None = "0036_admin_rbac"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ``substr``/``length`` and ``lower`` are supported by PostgreSQL and
    # SQLite, keeping migration verification representative of production.
    op.execute(
        sa.text(
            """
            UPDATE model_play_mode_providers AS provider
            SET
                provider_code = 'duoyuanx',
                status_query_url = CASE
                    WHEN provider.status_query_url IS NULL
                      OR trim(provider.status_query_url) = ''
                    THEN CASE
                        WHEN substr(provider.submit_url, length(provider.submit_url), 1) = '/'
                        THEN substr(provider.submit_url, 1, length(provider.submit_url) - 1) || '/{task_id}'
                        ELSE provider.submit_url || '/{task_id}'
                    END
                    ELSE provider.status_query_url
                END,
                status_query_method = 'GET',
                updated_at = CURRENT_TIMESTAMP
            WHERE provider.provider_code = 'volcengine'
              AND lower(provider.submit_url) LIKE 'https://duoyuanx.com/%'
              AND NOT EXISTS (
                  SELECT 1
                  FROM model_play_mode_providers AS existing
                  WHERE existing.play_mode_id = provider.play_mode_id
                    AND existing.provider_code = 'duoyuanx'
                    AND existing.provider_model_id = provider.provider_model_id
                    AND existing.id <> provider.id
              )
            """
        )
    )


def downgrade() -> None:
    raise RuntimeError(
        "0037_register_duoyuanx_provider is intentionally irreversible; "
        "it preserves operator endpoint configuration while replacing only its adapter code."
    )
