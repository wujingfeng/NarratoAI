"""Repair missing normalized model-generation price columns.

Revision ID: 0033_repair_model_generation_price_columns
Revises: 0032_model_play_mode_rule_output_arrays
Create Date: 2026-08-17

Some databases were stamped at revision 0031/0032 while an earlier draft of
the normalized model-generation schema was present.  Alembic does not rerun a
revision merely because its source file later gained columns, so those
databases can be missing the four rate columns read by the quote and task
settlement paths.  This forward-only repair adds only absent columns and is
safe for databases where 0031 already created the complete schema.
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0033_repair_model_generation_price_columns"
down_revision: str | None = "0032_model_play_mode_rule_output_arrays"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_PRICE_COLUMN_COMMENTS = {
    "per_million_input_credits": "每百万输入 Token 扣除的积分，仅 token 规则使用。",
    "per_million_output_credits": "每百万输出 Token 扣除的积分，仅 token 规则使用。",
    "per_usage_credits": "每次调用或每个实际图片输出扣除的积分，仅 usage 规则使用。",
    "per_second_credits": "每秒实际视频输出扣除的积分，仅 second 规则使用。",
}


def _price_column(name: str) -> sa.Column[object]:
    return sa.Column(
        name,
        sa.Integer(),
        nullable=True,
        comment=_PRICE_COLUMN_COMMENTS[name],
    )


def _add_missing_price_columns(table_name: str) -> None:
    """Add pricing columns only when a previously stamped schema lacks them."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if table_name not in inspector.get_table_names():
        raise RuntimeError(
            f"{table_name} is missing although the database is marked as 0032; "
            "restore the normalized model-generation tables before upgrading"
        )

    existing_columns = {column["name"] for column in inspector.get_columns(table_name)}
    for column_name in _PRICE_COLUMN_COMMENTS:
        if column_name not in existing_columns:
            op.add_column(table_name, _price_column(column_name))


def upgrade() -> None:
    """Restore price fields required by quote, precharge and final settlement."""
    _add_missing_price_columns("model_play_mode_provider_prices")
    _add_missing_price_columns("model_task_charges")


def downgrade() -> None:
    """Keep repaired columns: their pre-existing state cannot be distinguished safely."""
    raise RuntimeError(
        "0033_repair_model_generation_price_columns is intentionally irreversible"
    )
