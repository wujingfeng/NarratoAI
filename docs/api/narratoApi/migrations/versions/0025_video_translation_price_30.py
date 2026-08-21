"""将早期视频翻译分钟价升级为 30 创作点。

Revision ID: 0025_video_translation_price_30
Revises: 0024_video_translation_price
Create Date: 2026-08-11
"""

from typing import Sequence

from alembic import op


revision: str = "0025_video_translation_price_30"
down_revision: str | None = "0024_video_translation_price"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """保留既有 20 点历史价格，追加 30 点版本供新报价读取。"""

    op.execute(
        """
        INSERT INTO product_prices (product, version, credits_per_minute, created_at)
        SELECT 'video_translation', 2, 30, CURRENT_TIMESTAMP
        WHERE EXISTS (
            SELECT 1 FROM product_prices
            WHERE product = 'video_translation' AND version = 1
              AND credits_per_minute = 20
        )
        AND NOT EXISTS (
            SELECT 1 FROM product_prices
            WHERE product = 'video_translation' AND version = 2
        )
        """
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM product_prices "
        "WHERE product = 'video_translation' AND version = 2 AND credits_per_minute = 30"
    )
