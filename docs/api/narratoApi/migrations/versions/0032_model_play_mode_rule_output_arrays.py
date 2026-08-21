"""Store model play-mode output options as varchar arrays.

Revision ID: 0032_model_play_mode_rule_output_arrays
Revises: 0031_normalize_model_generation
Create Date: 2026-08-17
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY


revision = "0032_model_play_mode_rule_output_arrays"
down_revision = "0031_normalize_model_generation"
branch_labels = None
depends_on = None


StringArray = ARRAY(sa.String(32)).with_variant(sa.JSON(), "sqlite")


def _values(row: sa.RowMapping) -> list[str]:
    """Convert pre-0032 scalar/range/adaptive output settings into one option list."""
    kind = row["output_option_type"]
    if kind == "resolution" and row["resolution"] is not None:
        return [str(row["resolution"])]
    if kind == "ratio" and row["ratio"] is not None:
        result = [str(row["ratio"])]
    elif kind == "duration":
        if row["duration_seconds"] is not None:
            result = [str(row["duration_seconds"])]
        elif row["min_duration_seconds"] is not None and row["max_duration_seconds_output"] is not None:
            result = [str(value) for value in range(row["min_duration_seconds"], row["max_duration_seconds_output"] + 1)]
        else:
            result = []
    else:
        result = []
    if row["is_adaptive"] and "adaptive" not in result:
        result.insert(0, "adaptive")
    return result


def _consolidate_output_rows(rows: list[sa.RowMapping]) -> dict[tuple[str, str], tuple[str, list[str], list[str]]]:
    """Keep one row for each play-mode/output type and merge its old scalar rows."""
    grouped: dict[tuple[str, str], tuple[str, list[str], list[str]]] = {}
    for row in rows:
        key = (str(row["play_mode_id"]), str(row["output_option_type"]))
        values = _values(row)
        if key not in grouped:
            grouped[key] = (str(row["id"]), [], [])
        keeper, combined, duplicates = grouped[key]
        for value in values:
            if value not in combined:
                combined.append(value)
        if str(row["id"]) != keeper:
            duplicates.append(str(row["id"]))
    return grouped


def upgrade() -> None:
    bind = op.get_bind()
    rows = bind.execute(sa.text("""
        SELECT id, play_mode_id, output_option_type, resolution, ratio, duration_seconds,
               min_duration_seconds, max_duration_seconds_output, is_adaptive
        FROM model_play_mode_rules
        WHERE rule_kind = 'output_option'
        ORDER BY play_mode_id, output_option_type, sort_order DESC, id
    """)).mappings().all()
    grouped = _consolidate_output_rows(rows)

    # PostgreSQL requires explicit scalar-to-array USING expressions. SQLite
    # uses JSON only for local migration/test compatibility.
    if bind.dialect.name == "postgresql":
        # 0031 的时长列带有 ``duration_seconds > 0`` 约束。若先改为数组，
        # PostgreSQL 会在重建列类型时尝试把该表达式解释为 ``varchar[] > int``，
        # 从而使类型变更失败；必须先移除依赖旧标量类型的约束。
        op.drop_constraint("ck_model_play_mode_rules_duration", "model_play_mode_rules", type_="check")
        op.drop_constraint("ck_model_play_mode_rules_min_duration", "model_play_mode_rules", type_="check")
        op.drop_constraint("ck_model_play_mode_rules_max_duration_output", "model_play_mode_rules", type_="check")
        op.execute("""
            ALTER TABLE model_play_mode_rules
            ALTER COLUMN resolution TYPE VARCHAR(32)[]
            USING CASE WHEN resolution IS NULL THEN NULL ELSE ARRAY[resolution] END
        """)
        op.execute("""
            ALTER TABLE model_play_mode_rules
            ALTER COLUMN ratio TYPE VARCHAR(32)[]
            USING CASE WHEN ratio IS NULL THEN NULL ELSE ARRAY[ratio] END
        """)
        op.execute("""
            ALTER TABLE model_play_mode_rules
            ALTER COLUMN duration_seconds TYPE VARCHAR(32)[]
            USING CASE WHEN duration_seconds IS NULL THEN NULL ELSE ARRAY[duration_seconds::VARCHAR] END
        """)
        with op.batch_alter_table("model_play_mode_rules") as batch:
            batch.drop_column("min_duration_seconds")
            batch.drop_column("max_duration_seconds_output")
            batch.drop_column("is_adaptive")
    else:
        with op.batch_alter_table("model_play_mode_rules") as batch:
            batch.drop_constraint("ck_model_play_mode_rules_duration", type_="check")
            batch.drop_constraint("ck_model_play_mode_rules_min_duration", type_="check")
            batch.drop_constraint("ck_model_play_mode_rules_max_duration_output", type_="check")
            batch.alter_column("resolution", existing_type=sa.String(32), type_=sa.JSON())
            batch.alter_column("ratio", existing_type=sa.String(16), type_=sa.JSON())
            batch.alter_column("duration_seconds", existing_type=sa.Integer(), type_=sa.JSON())
            batch.drop_column("min_duration_seconds")
            batch.drop_column("max_duration_seconds_output")
            batch.drop_column("is_adaptive")

    rules = sa.table(
        "model_play_mode_rules",
        sa.column("id", sa.String(64)),
        sa.column("resolution", StringArray),
        sa.column("ratio", StringArray),
        sa.column("duration_seconds", StringArray),
    )
    for (_play_mode_id, kind), (keeper, values, duplicates) in grouped.items():
        payload = {"resolution": None, "ratio": None, "duration_seconds": None}
        if kind == "resolution":
            payload["resolution"] = values
        elif kind == "ratio":
            payload["ratio"] = values
        elif kind == "duration":
            payload["duration_seconds"] = values
        bind.execute(rules.update().where(rules.c.id == keeper).values(**payload))
        if duplicates:
            bind.execute(sa.delete(rules).where(rules.c.id.in_(duplicates)))


def downgrade() -> None:
    raise RuntimeError("0032_model_play_mode_rule_output_arrays is intentionally irreversible")
