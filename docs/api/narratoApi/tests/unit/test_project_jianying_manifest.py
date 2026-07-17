from __future__ import annotations

import inspect

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from narrato_api.artifacts.models import RegisteredArtifact
from narrato_api.auth.models import User
from narrato_api.database import Base
from narrato_api.editor.models import EditorRevision
from narrato_api.integrations.core_client import CoreJianyingManifest
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


def _add_artifact(session: Session, *, artifact_id: str, project_id: str) -> None:
    session.add(
        RegisteredArtifact(
            id=artifact_id,
            project_id=project_id,
            kind="video",
            cdn_url=f"https://cdn.example.test/exports/{artifact_id}.mp4",
            size=1024,
            checksum="sha256:" + "a" * 64,
            content_type="video/mp4",
            width=1920,
            height=1080,
            duration=1.0,
        )
    )


class FakeCoreClient:
    def build_jianying_manifest(self, **_kwargs: object) -> CoreJianyingManifest:
        return CoreJianyingManifest(
            template_version="v1", package_name="draft.zip", files=()
        )


def test_build_owned_completed_project_jianying_manifest_returns_the_pure_manifest() -> (
    None
):
    from narrato_api.exports.service import (
        build_owned_completed_project_jianying_manifest,
    )

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
        session.add(
            EditorRevision(
                id="erv_1",
                project_id="prj_completed",
                content={
                    "timeline": [
                        {
                            "source_asset_id": "ast_1",
                            "start": 0,
                            "end": 1,
                            "narration": "Hi",
                        }
                    ]
                },
            )
        )
        session.commit()

        manifest = build_owned_completed_project_jianying_manifest(
            session,
            user_id="usr_owner",
            project_id="prj_completed",
            core_client=FakeCoreClient(),
        )

    assert manifest == CoreJianyingManifest(
        template_version="v1", package_name="draft.zip", files=()
    )


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
    from narrato_api.exports.service import (
        build_owned_completed_project_jianying_manifest,
    )
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
                session,
                user_id=user_id,
                project_id=project_id,
                core_client=FakeCoreClient(),
            )

    assert error.value.code == expected_code


def test_build_owned_completed_project_jianying_manifest_has_no_external_dependencies() -> (
    None
):
    from narrato_api.exports import service

    source = inspect.getsource(service.build_owned_completed_project_jianying_manifest)
    for forbidden_dependency in (
        "zipfile",
        "httpx",
        "requests",
        "urllib",
        "open(",
        "oss",
    ):
        assert forbidden_dependency not in source
