"""Allow normalized task charges to omit a legacy USD unit-price column.

Revision ID: 0035_allow_legacy_task_charge_usd_null
Revises: 0034_repair_model_generation_billing_units
Create Date: 2026-08-17

Some pre-normalization databases retain ``unit_price_usd`` as NOT NULL on
``model_task_charges``.  The normalized task path stores credit-unit rules
instead and deliberately does not write a currency amount, so task creation
fails when that legacy column remains mandatory.  Preserve historic values but
make the obsolete column optional where it still exists.
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0035_allow_legacy_task_charge_usd_null"
down_revision: str | None = "0034_repair_model_generation_billing_units"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _allow_null_legacy_usd_price(table_name: str) -> None:
    inspector = sa.inspect(op.get_bind())
    if table_name not in inspector.get_table_names():
        return
    columns = {column["name"]: column for column in inspector.get_columns(table_name)}
    legacy_column = columns.get("unit_price_usd")
    if legacy_column is None or legacy_column["nullable"]:
        return
    with op.batch_alter_table(table_name) as batch:
        batch.alter_column(
            "unit_price_usd",
            existing_type=legacy_column["type"],
            nullable=True,
            comment="历史美元单价；归一化积分计费不再写入该字段。",
        )


def upgrade() -> None:
    _allow_null_legacy_usd_price("model_task_charges")
    _allow_null_legacy_usd_price("model_play_mode_provider_prices")


def downgrade() -> None:
    raise RuntimeError(
        "0035_allow_legacy_task_charge_usd_null is intentionally irreversible"
    )
