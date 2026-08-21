"""Freeze video-translation voice-replacement surcharge at workflow start.

Revision ID: 0027_video_translation_voice_replacement_charge
Revises: 0026_video_translation_timing
Create Date: 2026-08-13
"""

from typing import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0027_video_translation_voice_replacement_charge"
down_revision: str | None = "0026_video_translation_timing"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """保存总源时长、模式和单价，令扣费/退款可审计且不受后续改价影响。"""

    op.create_table(
        "video_translation_charges",
        sa.Column(
            "project_id",
            sa.String(length=64),
            sa.ForeignKey("projects.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column(
            "workflow_id",
            sa.String(length=64),
            sa.ForeignKey("workflows.id", ondelete="RESTRICT"),
            nullable=False,
            unique=True,
        ),
        sa.Column("price_version", sa.Integer(), nullable=False),
        sa.Column("total_source_seconds", sa.Integer(), nullable=False),
        sa.Column("billed_minutes", sa.Integer(), nullable=False),
        sa.Column("base_credits_per_minute", sa.Integer(), nullable=False),
        sa.Column("original_sound_mode", sa.String(length=32), nullable=False),
        sa.Column("voice_replacement_credits_per_minute", sa.Integer(), nullable=False),
        sa.Column("base_credits", sa.Integer(), nullable=False),
        sa.Column("voice_replacement_credits", sa.Integer(), nullable=False),
        sa.Column("total_credits", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "total_source_seconds > 0",
            name="ck_translation_charge_source_seconds_positive",
        ),
        sa.CheckConstraint(
            "billed_minutes > 0", name="ck_translation_charge_minutes_positive"
        ),
        sa.CheckConstraint(
            "base_credits_per_minute > 0",
            name="ck_translation_charge_base_rate_positive",
        ),
        sa.CheckConstraint(
            "voice_replacement_credits_per_minute >= 0",
            name="ck_translation_charge_surcharge_rate_nonnegative",
        ),
        sa.CheckConstraint(
            "base_credits >= 0", name="ck_translation_charge_base_nonnegative"
        ),
        sa.CheckConstraint(
            "voice_replacement_credits >= 0",
            name="ck_translation_charge_surcharge_nonnegative",
        ),
        sa.CheckConstraint(
            "total_credits = base_credits + voice_replacement_credits",
            name="ck_translation_charge_total_matches_breakdown",
        ),
        sa.CheckConstraint(
            "original_sound_mode IN ('voice_replacement', 'translated_voice_only')",
            name="ck_translation_charge_audio_mode",
        ),
    )


def downgrade() -> None:
    op.drop_table("video_translation_charges")
