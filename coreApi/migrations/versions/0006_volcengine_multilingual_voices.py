"""Expose multilingual TTS capability for the video translation voice catalog."""

from typing import Sequence

from alembic import op


revision: str = "0006_volcengine_multilingual_voices"
down_revision: str | None = "0005_core_task_checkpoints"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_LANGUAGES = (
    '["zh-CN","en","ja","ko","de","fr","es","pt","ru",'
    '"vi","th","id","ar"]'
)


def upgrade() -> None:
    op.execute(
        "UPDATE core_voices SET languages = "
        f"'{_LANGUAGES}'::jsonb "
        "WHERE provider_id = (SELECT id FROM core_providers WHERE code = 'volcengine')"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE core_voices SET languages = '[\"zh-CN\"]'::jsonb "
        "WHERE provider_id = (SELECT id FROM core_providers WHERE code = 'volcengine')"
    )
