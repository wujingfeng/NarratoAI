from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect


def test_workflows_migration_upgrades_task_13b_head_with_durable_workflow_tables(tmp_path) -> None:
    project_root = Path(__file__).resolve().parents[2]
    database_path = tmp_path / "workflows.db"
    config = Config(str(project_root / "alembic.ini"))
    config.set_main_option("script_location", str(project_root / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path}")

    command.upgrade(config, "0005_asset_probe_reservations")
    command.upgrade(config, "head")

    inspector = inspect(create_engine(f"sqlite:///{database_path}"))
    assert {
        "workflow_template_snapshots",
        "workflows",
        "workflow_nodes",
        "workflow_node_attempts",
        "workflow_outbox",
        "workflow_reconciliation_events",
    } <= set(inspector.get_table_names())
    assert {item["name"] for item in inspector.get_indexes("workflow_outbox")} >= {
        "ix_workflow_outbox_status_created"
    }
