"""Persist actual video-translation TTS timing and fit diagnostics.

Revision ID: 0026_video_translation_timing
Revises: 0025_video_translation_price_30
Create Date: 2026-08-12
"""

from typing import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0026_video_translation_timing"
down_revision: str | None = "0025_video_translation_price_30"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "video_translation_segments",
        sa.Column("tts_duration_ms", sa.Integer(), nullable=True),
    )
    op.add_column(
        "video_translation_segments",
        sa.Column(
            "timing_fit_status",
            sa.String(length=32),
            nullable=False,
            server_default="pending",
        ),
    )
    op.add_column(
        "video_translation_segments",
        sa.Column(
            "timing_overflow_ms",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "video_translation_segments",
        sa.Column("fitted_speed", sa.Float(), nullable=True),
    )
    # 历史 JSON 设置只表达“静音/保留完整原声”。升级后将其收敛为明确的
    # “替换人声/仅译文配音”，避免新旧 worker 对同一项目产生不同音轨。
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        op.execute(
            """
            UPDATE project_video_translation_settings
            SET settings = jsonb_set(
                settings::jsonb,
                '{original_sound_mode}',
                to_jsonb(CASE
                    WHEN settings->>'original_sound_mode' = 'mute'
                        THEN 'translated_voice_only'
                    ELSE 'voice_replacement'
                END::text),
                true
            )
            WHERE settings->>'original_sound_mode' IN ('mute', 'keep', 'preserve')
            """
        )
    elif dialect == "sqlite":
        op.execute(
            """
            UPDATE project_video_translation_settings
            SET settings = json_set(
                settings,
                '$.original_sound_mode',
                CASE
                    WHEN json_extract(settings, '$.original_sound_mode') = 'mute'
                        THEN 'translated_voice_only'
                    ELSE 'voice_replacement'
                END
            )
            WHERE json_extract(settings, '$.original_sound_mode')
                IN ('mute', 'keep', 'preserve')
            """
        )


def downgrade() -> None:
    op.drop_column("video_translation_segments", "fitted_speed")
    op.drop_column("video_translation_segments", "timing_overflow_ms")
    op.drop_column("video_translation_segments", "timing_fit_status")
    op.drop_column("video_translation_segments", "tts_duration_ms")
