from __future__ import annotations

import json
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


REVISION_0032 = "0032_model_play_mode_rule_output_arrays"
REVISION_0036 = "0036_admin_rbac"
REVISION_0039 = "0039_admin_menu_ui_paths"
REVISION_0040 = "0040_normalize_duoyuanx_resolution_options"
REVISION_0041 = "0041_normalize_duoyuanx_price_resolutions"
PRICE_COLUMNS = {
    "per_million_input_credits",
    "per_million_output_credits",
    "per_usage_credits",
    "per_second_credits",
}


def _config(database_path: Path) -> Config:
    project_root = Path(__file__).resolve().parents[2]
    config = Config(str(project_root / "alembic.ini"))
    config.set_main_option("script_location", str(project_root / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path}")
    return config


def test_0033_restores_missing_price_columns_from_a_stamped_0032_schema(tmp_path) -> None:
    database_path = tmp_path / "model-generation-repair.db"
    config = _config(database_path)
    command.upgrade(config, REVISION_0032)

    engine = create_engine(f"sqlite:///{database_path}")
    with engine.begin() as connection:
        # Simulate the historic partial 0031 table definition while the
        # Alembic version table still records 0032.
        connection.execute(text("DROP TABLE model_task_charges"))
        connection.execute(text("DROP TABLE model_play_mode_provider_prices"))
        connection.execute(text("""
            CREATE TABLE model_play_mode_provider_prices (
                id VARCHAR(64) PRIMARY KEY,
                provider_id VARCHAR(64) NOT NULL,
                resolution VARCHAR(32),
                billing_unit VARCHAR(40) NOT NULL
                    CONSTRAINT ck_model_play_mode_provider_prices_unit
                    CHECK (billing_unit IN ('per_second', 'per_output_second', 'per_usage', 'per_million_tokens')),
                unit_price_usd NUMERIC NOT NULL,
                is_enabled BOOLEAN NOT NULL DEFAULT 1,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL
            )
        """))
        connection.execute(text("""
            CREATE TABLE model_task_charges (
                id VARCHAR(64) PRIMARY KEY,
                task_id VARCHAR(64) NOT NULL,
                billing_unit VARCHAR(40) NOT NULL
                    CONSTRAINT ck_model_task_charges_unit
                    CHECK (billing_unit IN ('per_second', 'per_usage', 'per_million_tokens')),
                resolution VARCHAR(32),
                unit_price_usd NUMERIC NOT NULL,
                quantity NUMERIC NOT NULL DEFAULT 0,
                credits INTEGER NOT NULL DEFAULT 0,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL
            )
        """))
        connection.execute(text("""
            INSERT INTO model_play_mode_provider_prices (
                id, provider_id, resolution, billing_unit, unit_price_usd, created_at, updated_at
            ) VALUES ('price', 'provider', '480P', 'per_output_second', 0.00285714, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """))
        connection.execute(text("""
            INSERT INTO model_task_charges (
                id, task_id, billing_unit, unit_price_usd, created_at, updated_at
            ) VALUES ('charge', 'task', 'per_usage', 0.01, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """))

    command.upgrade(config, "head")

    inspector = inspect(engine)
    for table_name in ("model_play_mode_provider_prices", "model_task_charges"):
        columns = {column["name"]: column for column in inspector.get_columns(table_name)}
        assert PRICE_COLUMNS <= set(columns)
        assert columns["unit_price_usd"]["nullable"] is True

    with engine.connect() as connection:
        assert connection.execute(
            text("SELECT billing_unit FROM model_play_mode_provider_prices WHERE id = 'price'")
        ).scalar_one() == "second"
        assert connection.execute(
            text("SELECT billing_unit FROM model_task_charges WHERE id = 'charge'")
        ).scalar_one() == "usage"
        connection.execute(text("""
            INSERT INTO model_task_charges (
                id, task_id, billing_unit, created_at, updated_at
            ) VALUES ('charge_without_usd', 'task', 'second', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """))


def test_0037_maps_legacy_duoyuanx_endpoint_to_registered_provider_code(tmp_path) -> None:
    database_path = tmp_path / "duoyuanx-provider.db"
    config = _config(database_path)
    command.upgrade(config, REVISION_0036)

    engine = create_engine(f"sqlite:///{database_path}")
    with engine.begin() as connection:
        connection.execute(text("""
            INSERT INTO model_play_mode_providers (
                id, play_mode_id, provider_code, provider_model_id, submit_url,
                status_query_url, status_query_method, api_key, is_enabled, created_at, updated_at
            ) VALUES (
                'legacy-duoyuanx-provider', 'legacy-mode', 'volcengine', 'seedance1.0',
                'https://duoyuanx.com/v1/video/generations', NULL, 'POST', 'key', 1,
                CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
        """))

    command.upgrade(config, "head")

    with engine.connect() as connection:
        row = connection.execute(text("""
            SELECT provider_code, status_query_url, status_query_method
            FROM model_play_mode_providers
            WHERE id = 'legacy-duoyuanx-provider'
        """)).mappings().one()
    assert dict(row) == {
        "provider_code": "duoyuanx",
        "status_query_url": "https://duoyuanx.com/v1/video/generations/{task_id}",
        "status_query_method": "GET",
    }


def test_0040_normalizes_only_duoyuanx_resolution_values(tmp_path) -> None:
    database_path = tmp_path / "duoyuanx-resolution.db"
    config = _config(database_path)
    command.upgrade(config, REVISION_0039)

    engine = create_engine(f"sqlite:///{database_path}")
    with engine.begin() as connection:
        connection.execute(text("""
            INSERT INTO model_play_mode_providers (
                id, play_mode_id, provider_code, provider_model_id, submit_url,
                status_query_method, api_key, is_enabled, created_at, updated_at
            ) VALUES (
                'duoyuanx-provider', 'duoyuanx-mode', 'duoyuanx', 'seedance',
                'https://duoyuanx.com/v1/video/generations', 'GET', 'key', 1,
                CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            ), (
                'other-provider', 'other-mode', 'anyfast', 'seedance',
                'https://www.anyfast.ai/v1/video/generations', 'GET', 'key', 1,
                CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
        """))
        connection.execute(text("""
            INSERT INTO model_play_mode_rules (
                id, play_mode_id, rule_kind, output_option_type, resolution,
                is_supported, is_required, supports_mention, sort_order, created_at, updated_at
            ) VALUES
                ('duoyuanx-resolution', 'duoyuanx-mode', 'output_option', 'resolution',
                 '["480P", "720P", "4K"]', 1, 0, 0, 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
                ('other-resolution', 'other-mode', 'output_option', 'resolution',
                 '["480P"]', 1, 0, 0, 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """))

    command.upgrade(config, REVISION_0040)

    with engine.connect() as connection:
        rows = connection.execute(text("""
            SELECT id, resolution
            FROM model_play_mode_rules
            WHERE id IN ('duoyuanx-resolution', 'other-resolution')
            ORDER BY id
        """)).all()
    assert {row.id: json.loads(row.resolution) for row in rows} == {
        "duoyuanx-resolution": ["480p", "720p", "4k"],
        "other-resolution": ["480P"],
    }


def test_0041_normalizes_only_duoyuanx_price_resolution_values(tmp_path) -> None:
    database_path = tmp_path / "duoyuanx-price-resolution.db"
    config = _config(database_path)
    command.upgrade(config, REVISION_0040)

    engine = create_engine(f"sqlite:///{database_path}")
    with engine.begin() as connection:
        connection.execute(text("""
            INSERT INTO model_play_mode_providers (
                id, play_mode_id, provider_code, provider_model_id, submit_url,
                status_query_method, api_key, is_enabled, created_at, updated_at
            ) VALUES
                ('duoyuanx-provider', 'duoyuanx-mode', 'duoyuanx', 'seedance',
                 'https://duoyuanx.com/v1/video/generations', 'GET', 'key', 1,
                 CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
                ('other-provider', 'other-mode', 'anyfast', 'seedance',
                 'https://www.anyfast.ai/v1/video/generations', 'GET', 'key', 1,
                 CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """))
        connection.execute(text("""
            INSERT INTO model_play_mode_provider_prices (
                id, provider_id, resolution, billing_unit, per_second_credits,
                is_enabled, created_at, updated_at
            ) VALUES
                ('duoyuanx-price', 'duoyuanx-provider', '480P', 'second', 1, 1,
                 CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
                ('other-price', 'other-provider', '480P', 'second', 1, 1,
                 CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """))

    command.upgrade(config, REVISION_0041)

    with engine.connect() as connection:
        rows = connection.execute(text("""
            SELECT id, resolution
            FROM model_play_mode_provider_prices
            WHERE id IN ('duoyuanx-price', 'other-price')
            ORDER BY id
        """)).all()
    assert {row.id: row.resolution for row in rows} == {
        "duoyuanx-price": "480p",
        "other-price": "480P",
    }
