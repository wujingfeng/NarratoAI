from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect


def test_0004_upgrades_a_0003_database_with_project_and_asset_tables(tmp_path) -> None:
    project_root = Path(__file__).resolve().parents[2]
    database_path = tmp_path / "projects-assets.db"
    config = Config(str(project_root / "alembic.ini"))
    config.set_main_option("script_location", str(project_root / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path}")

    command.upgrade(config, "0003_billing")
    command.upgrade(config, "head")

    engine = create_engine(f"sqlite:///{database_path}")
    inspector = inspect(engine)
    assert {"projects", "assets"} <= set(inspector.get_table_names())
    assert {item["name"] for item in inspector.get_indexes("projects")} >= {
        "ix_projects_user_created"
    }
    assert {item["name"] for item in inspector.get_indexes("assets")} >= {
        "ix_assets_project_type",
        "ix_assets_user_created",
    }
