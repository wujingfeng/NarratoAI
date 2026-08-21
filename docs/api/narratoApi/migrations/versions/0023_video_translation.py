"""Independent video translation product data.

Revision ID: 0023_video_translation
Revises: 0022_allow_reused_project_assets
"""

from alembic import op
import sqlalchemy as sa

revision = "0023_video_translation"
down_revision = "0022_allow_reused_project_assets"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "project_video_translation_settings",
        sa.Column(
            "project_id",
            sa.String(64),
            sa.ForeignKey("projects.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column("settings", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "video_translation_segments",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "project_id",
            sa.String(64),
            sa.ForeignKey("projects.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("segment_index", sa.Integer(), nullable=False),
        sa.Column("start_ms", sa.Integer(), nullable=False),
        sa.Column("end_ms", sa.Integer(), nullable=False),
        sa.Column("source_text", sa.String(4000), nullable=False),
        sa.Column("translated_text", sa.String(4000), nullable=False),
        sa.Column("voice_id", sa.String(128), nullable=False),
        sa.Column(
            "voice_overridden", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("speed", sa.Float(), nullable=False, server_default="1"),
        sa.Column("volume", sa.Integer(), nullable=False, server_default="100"),
        sa.Column(
            "keep_original_sound",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("preview_audio_url", sa.String(2048)),
        sa.Column("preview_digest", sa.String(64)),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "project_id", "segment_index", name="uq_translation_segment_index"
        ),
    )
    op.create_index(
        "ix_video_translation_segments_project_id",
        "video_translation_segments",
        ["project_id"],
    )
    op.create_table(
        "video_translation_preview_charges",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "project_id",
            sa.String(64),
            sa.ForeignKey("projects.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "segment_id",
            sa.String(64),
            sa.ForeignKey("video_translation_segments.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("idempotency_key", sa.String(256), nullable=False),
        sa.Column("core_task_id", sa.String(128), nullable=True),
        sa.Column("credits", sa.Integer(), nullable=False, server_default="12"),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "project_id",
            "segment_id",
            "idempotency_key",
            name="uq_translation_preview_charge",
        ),
        sa.UniqueConstraint("core_task_id", name="uq_translation_preview_core_task"),
    )
    op.create_index(
        "ix_translation_preview_charges_core_task",
        "video_translation_preview_charges",
        ["core_task_id"],
    )


def downgrade():
    op.drop_index(
        "ix_translation_preview_charges_core_task",
        table_name="video_translation_preview_charges",
    )
    op.drop_table("video_translation_preview_charges")
    op.drop_index(
        "ix_video_translation_segments_project_id",
        table_name="video_translation_segments",
    )
    op.drop_table("video_translation_segments")
    op.drop_table("project_video_translation_settings")
