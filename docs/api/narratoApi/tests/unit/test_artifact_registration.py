from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from narrato_api.database import Base


def test_register_artifact_is_committed_by_its_caller() -> None:
    from narrato_api.artifacts.models import RegisteredArtifact
    from narrato_api.artifacts.service import register_artifact
    from narrato_api.auth.models import User
    from narrato_api.projects.models import Project

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        session.add(User(id="usr_1", email="owner@example.com", password_hash="hash"))
        session.add(
            Project(
                id="prj_1", user_id="usr_1", product="short_drama", status="completed"
            )
        )
        session.commit()

        artifact = register_artifact(
            session,
            artifact_id="art_1",
            project_id="prj_1",
            kind="video",
            cdn_url="https://cdn.example.test/exports/art_1.mp4",
        )

        assert artifact in session.new
        assert artifact.id == "art_1"
        assert artifact.project_id == "prj_1"
        assert artifact.kind == "video"
        assert artifact.cdn_url == "https://cdn.example.test/exports/art_1.mp4"

        session.commit()

    with Session(engine) as session:
        persisted = session.get(RegisteredArtifact, "art_1")

    assert persisted is not None
    assert persisted.project_id == "prj_1"
