from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from narrato_api.artifacts.models import RegisteredArtifact
from narrato_api.auth.models import User
from narrato_api.database import Base
from narrato_api.projects.models import Project


def _add_project(
    session: Session, *, project_id: str, user_id: str, status: str
) -> None:
    session.add(User(id=user_id, email=f"{user_id}@example.com", password_hash="hash"))
    session.add(
        Project(
            id=project_id,
            user_id=user_id,
            product="short_drama",
            status=status,
        )
    )


def _add_artifact(
    session: Session,
    *,
    artifact_id: str,
    project_id: str,
    kind: str,
    created_at: datetime,
) -> None:
    session.add(
        RegisteredArtifact(
            id=artifact_id,
            project_id=project_id,
            kind=kind,
            cdn_url=f"https://cdn.example.test/exports/{artifact_id}",
            created_at=created_at,
        )
    )


def test_lookup_completed_project_result_returns_its_registered_artifacts_in_order() -> (
    None
):
    from narrato_api.projects.service import lookup_completed_project_result

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    timestamp = datetime(2026, 7, 17, tzinfo=timezone.utc)

    with Session(engine) as session:
        _add_project(
            session,
            project_id="prj_completed",
            user_id="usr_owner",
            status="completed",
        )
        _add_artifact(
            session,
            artifact_id="art_video",
            project_id="prj_completed",
            kind="video",
            created_at=timestamp,
        )
        _add_artifact(
            session,
            artifact_id="art_subtitle",
            project_id="prj_completed",
            kind="subtitle",
            created_at=timestamp,
        )
        _add_artifact(
            session,
            artifact_id="art_voice",
            project_id="prj_completed",
            kind="voice",
            created_at=datetime(2026, 7, 18, tzinfo=timezone.utc),
        )
        _add_artifact(
            session,
            artifact_id="art_timeline",
            project_id="prj_completed",
            kind="timeline",
            created_at=timestamp,
        )
        session.commit()

        result = lookup_completed_project_result(
            session, user_id="usr_owner", project_id="prj_completed"
        )

    assert result.project_id == "prj_completed"
    assert [artifact.id for artifact in result.artifacts] == [
        "art_subtitle",
        "art_timeline",
        "art_video",
        "art_voice",
    ]


def test_lookup_completed_project_result_rejects_incomplete_artifact_set() -> None:
    from narrato_api.projects.service import (
        ProjectResultLookupError,
        lookup_completed_project_result,
    )

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        _add_project(
            session,
            project_id="prj_incomplete",
            user_id="usr_owner",
            status="completed",
        )
        _add_artifact(
            session,
            artifact_id="art_video_only",
            project_id="prj_incomplete",
            kind="video",
            created_at=datetime(2026, 7, 17, tzinfo=timezone.utc),
        )
        session.commit()

        with pytest.raises(ProjectResultLookupError) as error:
            lookup_completed_project_result(
                session, user_id="usr_owner", project_id="prj_incomplete"
            )

    assert error.value.code == "PROJECT_RESULT_ARTIFACTS_INCOMPLETE"


def test_lookup_completed_project_result_rejects_other_users() -> None:
    from narrato_api.projects.service import (
        ProjectResultLookupError,
        lookup_completed_project_result,
    )

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        _add_project(
            session,
            project_id="prj_private",
            user_id="usr_owner",
            status="completed",
        )
        session.commit()

        with pytest.raises(ProjectResultLookupError) as error:
            lookup_completed_project_result(
                session, user_id="usr_other", project_id="prj_private"
            )

    assert error.value.code == "PROJECT_RESULT_NOT_FOUND"


def test_lookup_completed_project_result_rejects_missing_projects() -> None:
    from narrato_api.projects.service import (
        ProjectResultLookupError,
        lookup_completed_project_result,
    )

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        with pytest.raises(ProjectResultLookupError) as error:
            lookup_completed_project_result(
                session, user_id="usr_owner", project_id="prj_missing"
            )

    assert error.value.code == "PROJECT_RESULT_NOT_FOUND"


@pytest.mark.parametrize("status", ["draft", "failed", "deleted"])
def test_lookup_completed_project_result_rejects_every_non_completed_status(
    status: str,
) -> None:
    from narrato_api.projects.service import (
        ProjectResultLookupError,
        lookup_completed_project_result,
    )

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        _add_project(
            session,
            project_id=f"prj_{status}",
            user_id="usr_owner",
            status=status,
        )
        session.commit()

        with pytest.raises(ProjectResultLookupError) as error:
            lookup_completed_project_result(
                session, user_id="usr_owner", project_id=f"prj_{status}"
            )

    assert error.value.code == "PROJECT_RESULT_NOT_COMPLETED"
