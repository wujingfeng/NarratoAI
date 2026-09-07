"""Expose multilingual TTS capability for the video translation voice catalog."""

from typing import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0006_volcengine_multilingual_voices"
down_revision: str | None = "0005_core_task_checkpoints"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_LANGUAGES = [
    "zh-CN", "en", "ja", "ko", "de", "fr", "es", "pt", "ru",
    "vi", "th", "id", "ar",
]


def _update_languages(languages: list[str]) -> None:
    voices = sa.table(
        "core_voices",
        sa.column("provider_id", sa.String()),
        sa.column("languages", sa.JSON()),
    )
    providers = sa.table(
        "core_providers",
        sa.column("id", sa.String()),
        sa.column("code", sa.String()),
    )
    provider_id = sa.select(providers.c.id).where(
        providers.c.code == "volcengine"
    ).scalar_subquery()
    op.execute(
        voices.update()
        .where(voices.c.provider_id == provider_id)
        .values(languages=languages)
    )


def upgrade() -> None:
    _update_languages(_LANGUAGES)


def downgrade() -> None:
    _update_languages(["zh-CN"])
