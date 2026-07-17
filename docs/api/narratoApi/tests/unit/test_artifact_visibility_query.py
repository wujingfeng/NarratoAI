from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from narrato_api.artifacts.models import RegisteredArtifact
from narrato_api.auth.models import User
from narrato_api.database import Base
from narrato_api.projects.models import Project


def _create_project(session: Session, *, project_id: str, status: str):
    user_id = f"usr_{project_id}"
    session.add(User(id=user_id, email=f"{user_id}@example.com", password_hash="hash"))
    project = Project(
        id=project_id,
        user_id=user_id,
        product="short_drama",
        status=status,
    )
    session.add(project)
    return project


def _register_artifact(
    session: Session,
    *,
    artifact_id: str,
    project_id: str,
    created_at: datetime,
) -> None:
    session.add(
        RegisteredArtifact(
            id=artifact_id,
            project_id=project_id,
            kind="video",
            cdn_url=f"https://cdn.example.test/exports/{artifact_id}.mp4",
            created_at=created_at,
        )
    )


def test_list_registered_artifacts_returns_completed_projects_artifacts_in_stable_order() -> None:
    from narrato_api.artifacts.service import list_registered_artifacts

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    created_at = datetime(2026, 7, 17, tzinfo=timezone.utc)

    with Session(engine) as session:
        project = _create_project(session, project_id="prj_completed", status="completed")
        other_project = _create_project(session, project_id="prj_other", status="completed")
        _register_artifact(
            session,
            artifact_id="art_b",
            project_id=project.id,
            created_at=created_at,
        )
        _register_artifact(
            session,
            artifact_id="art_a",
            project_id=project.id,
            created_at=created_at,
        )
        _register_artifact(
            session,
            artifact_id="art_later",
            project_id=project.id,
            created_at=datetime(2026, 7, 18, tzinfo=timezone.utc),
        )
        _register_artifact(
            session,
            artifact_id="art_other",
            project_id=other_project.id,
            created_at=created_at,
        )
        session.commit()

        artifacts = list_registered_artifacts(session, project=project)

    assert [artifact.id for artifact in artifacts] == ["art_a", "art_b", "art_later"]


@pytest.mark.parametrize("status", ["draft", "failed", "deleted"])
def test_list_registered_artifacts_hides_artifacts_unless_project_is_completed(
    status: str,
) -> None:
    from narrato_api.artifacts.service import list_registered_artifacts

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        project = _create_project(session, project_id=f"prj_{status}", status=status)
        _register_artifact(
            session,
            artifact_id=f"art_{status}",
            project_id=project.id,
            created_at=datetime(2026, 7, 17, tzinfo=timezone.utc),
        )
        session.commit()

        assert list_registered_artifacts(session, project=project) == []
