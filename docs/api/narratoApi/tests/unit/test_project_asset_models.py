from __future__ import annotations

import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from narrato_api.assets.models import Asset
from narrato_api.auth.models import User
from narrato_api.database import Base, create_database_engine
from narrato_api.projects.models import Project


def test_project_and_asset_models_have_owner_foreign_keys_and_named_constraints() -> (
    None
):
    engine = create_database_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    inspector = inspect(engine)

    project_foreign_keys = inspector.get_foreign_keys("projects")
    asset_foreign_keys = inspector.get_foreign_keys("assets")
    assert {item["referred_table"] for item in project_foreign_keys} == {"users"}
    assert {item["referred_table"] for item in asset_foreign_keys} == {
        "users",
        "projects",
    }
    assert {item["name"] for item in inspector.get_check_constraints("projects")} >= {
        "ck_projects_status"
    }
    assert {item["name"] for item in inspector.get_check_constraints("assets")} >= {
        "ck_assets_type",
        "ck_assets_status",
        "ck_assets_filename_length",
    }


def test_asset_database_constraints_reject_invalid_state_and_missing_owner() -> None:
    engine = create_database_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(
            Asset(
                id="ast_invalid",
                user_id="usr_missing",
                project_id="prj_missing",
                asset_type="video",
                status="unknown",
                filename="episode.mp4",
                bucket="narrato",
                object_key="narrato/api/episode.mp4",
                cdn_url="https://cdn.example/episode.mp4",
                size_bytes=1,
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()


def test_project_and_asset_persist_user_ownership_and_timestamps() -> None:
    engine = create_database_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(User(id="usr_1", email="owner@example.com", password_hash="hash"))
        session.add(
            Project(id="prj_1", user_id="usr_1", product="short_drama", status="draft")
        )
        session.flush()
        session.add(
            Asset(
                id="ast_1",
                user_id="usr_1",
                project_id="prj_1",
                asset_type="subtitle",
                status="validating",
                filename="episode.srt",
                bucket="narrato",
                object_key="narrato/api/episode.srt",
                cdn_url="https://cdn.example/episode.srt",
                size_bytes=1,
            )
        )
        session.commit()

        project = session.get(Project, "prj_1")
        asset = session.get(Asset, "ast_1")
        assert project is not None and project.created_at is not None
        assert asset is not None and asset.created_at is not None
        assert project.user_id == asset.user_id == "usr_1"
