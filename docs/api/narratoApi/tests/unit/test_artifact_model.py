from __future__ import annotations

from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session

from narrato_api.database import Base


def test_registered_artifact_persists_project_owned_export_identifiers() -> None:
    from narrato_api.auth.models import User
    from narrato_api.artifacts.models import RegisteredArtifact
    from narrato_api.projects.models import Project

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    columns = {
        column["name"]: column
        for column in inspect(engine).get_columns(RegisteredArtifact.__tablename__)
    }
    foreign_keys = inspect(engine).get_foreign_keys(RegisteredArtifact.__tablename__)

    assert RegisteredArtifact.__tablename__ == "artifacts"
    assert {"id", "project_id", "kind", "cdn_url", "created_at"} <= set(columns)
    assert columns["project_id"]["nullable"] is False
    assert columns["kind"]["nullable"] is False
    assert columns["cdn_url"]["nullable"] is False
    assert Project.__tablename__ == "projects"
    assert User.__tablename__ == "users"
    assert foreign_keys == [
        {
            "name": None,
            "constrained_columns": ["project_id"],
            "referred_schema": None,
            "referred_table": "projects",
            "referred_columns": ["id"],
            "options": {"ondelete": "RESTRICT"},
        }
    ]


def test_registered_artifact_persists_export_fields_for_its_project() -> None:
    from narrato_api.artifacts.models import RegisteredArtifact
    from narrato_api.auth.models import User
    from narrato_api.projects.models import Project

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        session.add(User(id="usr_1", email="owner@example.com", password_hash="hash"))
        session.add(
            Project(id="prj_1", user_id="usr_1", product="short_drama", status="completed")
        )
        session.add(
            RegisteredArtifact(
                id="art_1",
                project_id="prj_1",
                kind="video",
                cdn_url="https://cdn.example.test/exports/art_1.mp4",
            )
        )
        session.commit()

    with Session(engine) as session:
        artifact = session.get(RegisteredArtifact, "art_1")

    assert artifact is not None
    assert (
        artifact.id,
        artifact.project_id,
        artifact.kind,
        artifact.cdn_url,
    ) == (
        "art_1",
        "prj_1",
        "video",
        "https://cdn.example.test/exports/art_1.mp4",
    )
