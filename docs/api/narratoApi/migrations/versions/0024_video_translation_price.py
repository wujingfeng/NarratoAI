"""为视频翻译写入首个按分钟计费版本。

Revision ID: 0024_video_translation_price
Revises: 0023_video_translation
Create Date: 2026-08-11
"""

from typing import Sequence

from alembic import op


revision: str = "0024_video_translation_price"
down_revision: str | None = "0023_video_translation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """视频翻译首版定价：每个计费分钟 30 创作点。

    价格表是版本化的，已有人工配置时不得覆盖；首次部署才写入版本 1。
    """

    op.execute(
        """
        INSERT INTO product_prices (product, version, credits_per_minute, created_at)
        SELECT 'video_translation', 1, 30, CURRENT_TIMESTAMP
        WHERE NOT EXISTS (
            SELECT 1 FROM product_prices WHERE product = 'video_translation'
        )
        """
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM product_prices "
        "WHERE product = 'video_translation' AND version = 1 AND credits_per_minute = 30"
    )
