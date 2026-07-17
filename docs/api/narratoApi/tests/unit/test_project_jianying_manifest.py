from __future__ import annotations

import inspect

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from narrato_api.artifacts.models import RegisteredArtifact
from narrato_api.auth.models import User
from narrato_api.database import Base
from narrato_api.projects.models import Project


def _add_project(session: Session, *, project_id: str, user_id: str, status: str) -> None:
    session.add(User(id=user_id, email=f"{user_id}@example.com", password_hash="hash"))
    session.add(
        Project(
            id=project_id,
            user_id=user_id,
            product="short_drama",
            status=status,
        )
    )


def _add_artifact(session: Session, *, artifact_id: str, project_id: str) -> None:
    session.add(
        RegisteredArtifact(
            id=artifact_id,
            project_id=project_id,
            kind="video",
            cdn_url=f"https://cdn.example.test/exports/{artifact_id}.mp4",
        )
    )


def test_build_owned_completed_project_jianying_manifest_returns_the_pure_manifest() -> None:
    from narrato_api.exports.service import build_owned_completed_project_jianying_manifest

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        _add_project(
            session,
            project_id="prj_completed",
            user_id="usr_owner",
            status="completed",
        )
        _add_artifact(session, artifact_id="art_video", project_id="prj_completed")
        session.commit()

        manifest = build_owned_completed_project_jianying_manifest(
            session, user_id="usr_owner", project_id="prj_completed"
        )

    assert manifest == {
        "package_name": "jianying-export.zip",
        "resources": [
            {
                "artifact_id": "art_video",
                "cdn_url": "https://cdn.example.test/exports/art_video.mp4",
                "zip_path": "video/397b6c2889bd2f42259dda019f36c8cd.mp4",
            }
        ],
    }


@pytest.mark.parametrize(
    ("user_id", "project_id", "status", "expected_code"),
    [
        ("usr_other", "prj_private", "completed", "PROJECT_RESULT_NOT_FOUND"),
        ("usr_owner", "prj_missing", None, "PROJECT_RESULT_NOT_FOUND"),
        ("usr_owner", "prj_draft", "draft", "PROJECT_RESULT_NOT_COMPLETED"),
    ],
)
def test_build_owned_completed_project_jianying_manifest_rejects_ineligible_projects(
    user_id: str, project_id: str, status: str | None, expected_code: str
) -> None:
    from narrato_api.exports.service import build_owned_completed_project_jianying_manifest
    from narrato_api.projects.service import ProjectResultLookupError

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        if status is not None:
            _add_project(
                session,
                project_id=project_id,
                user_id="usr_owner",
                status=status,
            )
            session.commit()

        with pytest.raises(ProjectResultLookupError) as error:
            build_owned_completed_project_jianying_manifest(
                session, user_id=user_id, project_id=project_id
            )

    assert error.value.code == expected_code


def test_build_owned_completed_project_jianying_manifest_has_no_external_dependencies() -> None:
    from narrato_api.exports import service

    source = inspect.getsource(service.build_owned_completed_project_jianying_manifest)
    for forbidden_dependency in (
        "zipfile",
        "httpx",
        "requests",
        "urllib",
        "open(",
        "oss",
        "core",
    ):
        assert forbidden_dependency not in source
