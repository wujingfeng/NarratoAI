from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from narrato_api.assets.models import Asset
from narrato_api.auth.models import User
from narrato_api.billing.models import CreditAccount, CreditLedger
from narrato_api.billing.service import BillingService, InsufficientCreditsError
from narrato_api.database import Base
from narrato_api.projects.models import Project


def _billing_service() -> tuple[BillingService, sessionmaker, str]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    user_id = "usr_ledger"
    with sessions.begin() as session:
        session.add(
            User(
                id=user_id,
                email="ledger@example.com",
                password_hash="test-hash",
                status="active",
            )
        )
    return BillingService(sessions), sessions, user_id


def test_charge_never_allows_negative_balance() -> None:
    billing, sessions, user_id = _billing_service()
    billing.grant(user_id, 19, reason="operator_grant", idempotency_key="grant:one")

    with pytest.raises(InsufficientCreditsError):
        billing.charge_project(user_id, "prj_1", 20)

    with sessions() as session:
        account = session.get(CreditAccount, user_id)
        assert account is not None and account.balance == 19
        assert session.scalars(select(CreditLedger)).all()[0].amount == 19


def test_charge_is_idempotent_and_records_a_single_immutable_debit() -> None:
    billing, sessions, user_id = _billing_service()
    billing.grant(user_id, 100, reason="operator_grant", idempotency_key="grant:one")
    billing.charge_project(user_id, "prj_1", 20)
    billing.charge_project(user_id, "prj_1", 20)

    with sessions() as session:
        account = session.get(CreditAccount, user_id)
        entries = session.scalars(
            select(CreditLedger).where(CreditLedger.reference_id == "prj_1")
        ).all()
        assert account is not None and account.balance == 80
        assert [(entry.entry_type, entry.amount) for entry in entries] == [
            ("charge", -20)
        ]


def test_cli_grant_is_idempotent_against_a_migrated_sqlite_database(
    tmp_path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """CLI 的固定运维充值命令重复执行时只能产生一笔入账。"""

    from alembic import command
    from alembic.config import Config

    from narrato_api.cli import main

    database_path = tmp_path / "cli.db"
    project_root = Path(__file__).resolve().parents[2]
    alembic_config = Config(str(project_root / "alembic.ini"))
    alembic_config.set_main_option("script_location", str(project_root / "migrations"))
    alembic_config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path}")
    command.upgrade(alembic_config, "head")

    engine = create_engine(f"sqlite:///{database_path}")
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    with sessions.begin() as session:
        session.add(
            User(
                id="usr_cli",
                email="cli@example.com",
                password_hash="test-hash",
                status="active",
            )
        )
    engine.dispose()

    config_path = tmp_path / "cli.toml"
    config_path.write_text(f'database_url = "sqlite:///{database_path}"\n')
    monkeypatch.setenv("NARRATO_API_CONFIG", str(config_path))
    command_args = [
        "credits",
        "grant",
        "--email",
        "cli@example.com",
        "--amount",
        "25",
        "--reason",
        "operator_grant",
    ]

    assert main(command_args) == 0
    assert capsys.readouterr().out == "applied\n"
    assert main(command_args) == 0
    assert capsys.readouterr().out == "already_applied\n"

    with sessions() as session:
        account = session.get(CreditAccount, "usr_cli")
        entries = session.scalars(select(CreditLedger)).all()
        assert account is not None and account.balance == 25
        assert len(entries) == 1


def test_cli_rewrites_only_legacy_oss_asset_urls(
    tmp_path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from alembic import command
    from alembic.config import Config

    from narrato_api.cli import main

    database_path = tmp_path / "assets.db"
    project_root = Path(__file__).resolve().parents[2]
    alembic_config = Config(str(project_root / "alembic.ini"))
    alembic_config.set_main_option("script_location", str(project_root / "migrations"))
    alembic_config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path}")
    command.upgrade(alembic_config, "head")

    engine = create_engine(f"sqlite:///{database_path}")
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    with sessions.begin() as session:
        session.add_all(
            [
                User(id="usr_cli", email="cli@example.com", password_hash="test-hash"),
                Project(id="prj_cli", user_id="usr_cli", product="short_drama"),
                Asset(
                    id="ast_legacy",
                    user_id="usr_cli",
                    project_id="prj_cli",
                    asset_type="video",
                    status="ready",
                    filename="episode.mp4",
                    bucket="bucket",
                    object_key="narrato/api/episode.mp4",
                    cdn_url="https://bucket.oss.example.test/narrato/api/episode.mp4",
                    size_bytes=100,
                ),
            ]
        )
    engine.dispose()

    config_path = tmp_path / "cli.toml"
    config_path.write_text(
        "\n".join(
            [
                f'database_url = "sqlite:///{database_path}"',
                'oss_url = "https://bucket.oss.example.test"',
                'cdn_public_base_url = "https://cdn.example.test"',
            ]
        )
        + "\n"
    )
    monkeypatch.setenv("NARRATO_API_CONFIG", str(config_path))

    assert main(["assets", "rewrite-cdn-urls"]) == 0
    assert capsys.readouterr().out == "would_update=1\n"
    assert main(["assets", "rewrite-cdn-urls", "--apply"]) == 0
    assert capsys.readouterr().out == "updated=1\n"

    with sessions() as session:
        asset = session.get(Asset, "ast_legacy")
        assert asset is not None
        assert asset.cdn_url == "https://cdn.example.test/narrato/api/episode.mp4"
