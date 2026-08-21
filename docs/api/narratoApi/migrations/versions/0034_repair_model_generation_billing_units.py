"""Repair legacy billing-unit checks in normalized model price tables.

Revision ID: 0034_repair_model_generation_billing_units
Revises: 0033_repair_model_generation_price_columns
Create Date: 2026-08-17

Early deployed drafts used the same check-constraint names as the normalized
schema but allowed different billing-unit values.  Databases stamped as 0032
therefore reject the current API value ``second`` even after 0033 restores the
rate columns.  Normalize recognised legacy values, then recreate the named
checks with the current contract.
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0034_repair_model_generation_billing_units"
down_revision: str | None = "0033_repair_model_generation_price_columns"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_ALLOWED_UNITS = ("second", "token", "usage")
_TABLE_CONSTRAINTS = {
    "model_play_mode_provider_prices": "ck_model_play_mode_provider_prices_unit",
    "model_task_charges": "ck_model_task_charges_unit",
}


def _normalize_legacy_values(table_name: str) -> None:
    """Map known draft spellings before enforcing the current enum."""
    op.execute(
        sa.text(
            f"""
            UPDATE {table_name}
            SET billing_unit = CASE lower(trim(billing_unit))
                WHEN 'per_second' THEN 'second'
                WHEN 'per-second' THEN 'second'
                WHEN 'per_output_second' THEN 'second'
                WHEN 'per_output_seconds' THEN 'second'
                WHEN 'seconds' THEN 'second'
                WHEN 'per_usage' THEN 'usage'
                WHEN 'per-use' THEN 'usage'
                WHEN 'per_request' THEN 'usage'
                WHEN 'per_million_token' THEN 'token'
                WHEN 'per_million_tokens' THEN 'token'
                WHEN 'per_1m_token' THEN 'token'
                WHEN 'per_1m_tokens' THEN 'token'
                ELSE billing_unit
            END
            """
        )
    )


def _assert_no_unknown_units(table_name: str) -> None:
    bind = op.get_bind()
    values = bind.execute(
        sa.text(
            f"""
            SELECT DISTINCT billing_unit
            FROM {table_name}
            WHERE billing_unit NOT IN ('second', 'token', 'usage')
            ORDER BY billing_unit
            """
        )
    ).scalars().all()
    if values:
        raise RuntimeError(
            f"{table_name} has unsupported billing_unit values: {', '.join(map(str, values))}. "
            "Map them to second, token or usage before rerunning the migration."
        )


def _drop_unit_constraint(table_name: str, constraint_name: str) -> None:
    inspector = sa.inspect(op.get_bind())
    check_names = {
        constraint["name"]
        for constraint in inspector.get_check_constraints(table_name)
        if constraint["name"]
    }
    if constraint_name in check_names:
        with op.batch_alter_table(table_name) as batch:
            batch.drop_constraint(constraint_name, type_="check")


def _create_unit_constraint(table_name: str, constraint_name: str) -> None:
    with op.batch_alter_table(table_name) as batch:
        batch.create_check_constraint(
            constraint_name,
            "billing_unit IN ('second', 'token', 'usage')",
        )


def upgrade() -> None:
    for table_name, constraint_name in _TABLE_CONSTRAINTS.items():
        _drop_unit_constraint(table_name, constraint_name)
        _normalize_legacy_values(table_name)
        _assert_no_unknown_units(table_name)
        _create_unit_constraint(table_name, constraint_name)


def downgrade() -> None:
    raise RuntimeError(
        "0034_repair_model_generation_billing_units is intentionally irreversible"
    )
