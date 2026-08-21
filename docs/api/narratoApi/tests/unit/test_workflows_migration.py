from __future__ import annotations

import json
import logging
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from narrato_api.logging import configure_logging


def test_alembic_migration_does_not_disable_business_logger(
    tmp_path, monkeypatch
) -> None:
    """迁移加载 logging 配置后，进程内业务日志仍必须可用。"""

    project_root = Path(__file__).resolve().parents[2]
    database_path = tmp_path / "logging.db"
    config = Config(str(project_root / "alembic.ini"))
    config.set_main_option("script_location", str(project_root / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path}")
    configure_logging()
    namespace = logging.getLogger("narrato_api")
    monkeypatch.setattr(namespace, "disabled", False)

    command.upgrade(config, "head")

    assert namespace.disabled is False


def test_workflows_migration_upgrades_task_13b_head_with_durable_workflow_tables(
    tmp_path,
) -> None:
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
        "ix_workflow_outbox_status_created",
        "ix_workflow_outbox_sending_lease",
    }


def test_outbox_lease_migration_accepts_bootstrap_schema_drift(tmp_path) -> None:
    """最新 bootstrap 结构被旧 revision stamp 后仍应安全推进到 head。"""

    project_root = Path(__file__).resolve().parents[2]
    database_path = tmp_path / "bootstrap-drift.db"
    config = Config(str(project_root / "alembic.ini"))
    config.set_main_option("script_location", str(project_root / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path}")

    command.upgrade(config, "0016_project_stages")
    engine = create_engine(f"sqlite:///{database_path}")
    with engine.begin() as connection:
        connection.execute(
            text("ALTER TABLE workflow_outbox ADD COLUMN dispatch_lease_id VARCHAR(64)")
        )
        connection.execute(
            text("ALTER TABLE workflow_outbox ADD COLUMN dispatch_started_at DATETIME")
        )
        connection.execute(
            text(
                "CREATE INDEX ix_workflow_outbox_sending_lease "
                "ON workflow_outbox (status, dispatch_started_at)"
            )
        )

    command.upgrade(config, "head")

    inspector = inspect(engine)
    assert {item["name"] for item in inspector.get_columns("workflow_outbox")} >= {
        "dispatch_lease_id",
        "dispatch_started_at",
    }
    assert "ix_workflow_outbox_sending_lease" in {
        item["name"] for item in inspector.get_indexes("workflow_outbox")
    }
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == (
            "0027_video_translation_voice_replacement_charge"
        )


def test_artifact_truth_gate_removes_only_legacy_demo_drafts(tmp_path) -> None:
    project_root = Path(__file__).resolve().parents[2]
    database_path = tmp_path / "artifact-truth-gate.db"
    config = Config(str(project_root / "alembic.ini"))
    config.set_main_option("script_location", str(project_root / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path}")

    command.upgrade(config, "0019_short_drama_workflow_v2")
    engine = create_engine(f"sqlite:///{database_path}")
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO editor_drafts (project_id, id, content, updated_at) "
                "VALUES (:project_id, :id, :content, CURRENT_TIMESTAMP)"
            ),
            [
                {
                    "project_id": "prj_legacy",
                    "id": "edr_legacy",
                    "content": json.dumps(
                        {"clips": [{"asset_id": "/media/narration-editor/demo.mp4"}]}
                    ),
                },
                {
                    "project_id": "prj_real",
                    "id": "edr_real",
                    "content": json.dumps({"clips": [{"asset_id": "ast_real"}]}),
                },
            ],
        )

    command.upgrade(config, "head")

    with engine.connect() as connection:
        assert connection.execute(
            text("SELECT id FROM editor_drafts ORDER BY id")
        ).scalars().all() == ["edr_real"]
    inspector = inspect(engine)
    assert "uq_artifacts_project_kind" in {
        item["name"] for item in inspector.get_unique_constraints("artifacts")
    }


def test_asset_sort_order_backfills_existing_assets_per_project_and_type(
    tmp_path,
) -> None:
    project_root = Path(__file__).resolve().parents[2]
    database_path = tmp_path / "asset-sort-order.db"
    config = Config(str(project_root / "alembic.ini"))
    config.set_main_option("script_location", str(project_root / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path}")

    command.upgrade(config, "0020_artifact_truth_gate")
    engine = create_engine(f"sqlite:///{database_path}")
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO users "
                "(id, email, password_hash, status, password_version, created_at, updated_at) "
                "VALUES ('usr_order', 'order@example.test', 'hash', 'active', 1, "
                "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO projects "
                "(id, user_id, product, status, is_locked, current_stage, created_at, updated_at) "
                "VALUES ('prj_order', 'usr_order', 'short_drama_narration', 'draft', 0, "
                "'created', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            )
        )
        for asset_id, asset_type, created_at in (
            ("ast_video_2", "video", "2026-08-04 00:00:02"),
            ("ast_video_1", "video", "2026-08-04 00:00:01"),
            ("ast_audio_1", "audio", "2026-08-04 00:00:03"),
        ):
            connection.execute(
                text(
                    "INSERT INTO assets "
                    "(id, user_id, project_id, asset_type, status, filename, bucket, object_key, "
                    "cdn_url, size_bytes, created_at, updated_at) "
                    "VALUES (:id, 'usr_order', 'prj_order', :asset_type, 'ready', :filename, "
                    "'bucket', :object_key, :cdn_url, 1, :created_at, :created_at)"
                ),
                {
                    "id": asset_id,
                    "asset_type": asset_type,
                    "filename": f"{asset_id}.mp4",
                    "object_key": asset_id,
                    "cdn_url": f"https://cdn.example/{asset_id}",
                    "created_at": created_at,
                },
            )

    command.upgrade(config, "head")

    with engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT id, sort_order FROM assets ORDER BY asset_type, sort_order, id"
            )
        ).all()
    assert rows == [
        ("ast_audio_1", 0),
        ("ast_video_1", 0),
        ("ast_video_2", 1),
    ]
    columns = {item["name"]: item for item in inspect(engine).get_columns("assets")}
    assert columns["sort_order"]["nullable"] is False


def test_runtime_bootstrap_uses_current_video_translation_base_price() -> None:
    project_root = Path(__file__).resolve().parents[2]
    bootstrap = (
        project_root / "sql" / "bootstrap-runtime-data.postgresql.sql"
    ).read_text(encoding="utf-8")

    assert "VALUES ('video_translation', 1, 20" not in bootstrap
    assert "VALUES ('video_translation', 1, 30" in bootstrap
    assert "VALUES ('video_translation', 2, 30" in bootstrap
    assert bootstrap.index("VALUES ('video_translation', 2, 30") < bootstrap.index(
        "COMMIT;"
    )
