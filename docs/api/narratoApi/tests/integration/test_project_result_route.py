from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from narrato_api.artifacts.models import RegisteredArtifact
from narrato_api.auth.models import User
from narrato_api.auth.router import get_auth_service
from narrato_api.config import Settings
from narrato_api.database import Base
from narrato_api.main import create_app
from narrato_api.projects.models import DeletionJob, Project


class FakeAuthService:
    def resolve_user(self, token: str) -> User:
        if token == "owner-token":
            return User(
                id="usr_owner", email="owner@example.test", password_hash="hash"
            )
        if token == "other-token":
            return User(
                id="usr_other", email="other@example.test", password_hash="hash"
            )
        raise RuntimeError("unexpected token")


@pytest.fixture
def project_result_fixture(tmp_path) -> Iterator[TestClient]:
    database_path = tmp_path / "project-results.db"
    engine = create_engine(f"sqlite:///{database_path}")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    with sessions.begin() as session:
        session.add_all(
            [
                User(id="usr_owner", email="owner@example.test", password_hash="hash"),
                User(id="usr_other", email="other@example.test", password_hash="hash"),
                Project(
                    id="prj_completed",
                    user_id="usr_owner",
                    product="short_drama",
                    status="completed",
                    current_stage="export",
                ),
                Project(
                    id="prj_created",
                    user_id="usr_owner",
                    product="short_drama",
                    status="draft",
                    current_stage="created",
                ),
                Project(
                    id="prj_failed",
                    user_id="usr_owner",
                    product="short_drama",
                    status="failed",
                    current_stage="analysis",
                ),
                Project(
                    id="prj_settings",
                    user_id="usr_owner",
                    product="short_drama",
                    status="ready",
                    current_stage="settings",
                ),
                Project(
                    id="prj_analyzing",
                    user_id="usr_owner",
                    product="short_drama",
                    status="analyzing",
                    current_stage="analysis",
                ),
                Project(
                    id="prj_rendering",
                    user_id="usr_owner",
                    product="short_drama",
                    status="rendering",
                    current_stage="generate",
                ),
                Project(
                    id="prj_deleting",
                    user_id="usr_owner",
                    product="short_drama",
                    status="deleting",
                    current_stage="created",
                ),
                Project(
                    id="prj_deleted",
                    user_id="usr_owner",
                    product="short_drama",
                    status="deleted",
                    current_stage="settings",
                ),
                *[
                    RegisteredArtifact(
                        id=f"art_{kind}",
                        project_id="prj_completed",
                        kind=kind,
                        cdn_url=f"https://cdn.example.test/exports/{kind}.{extension}",
                        created_at=datetime(2026, 7, 17, tzinfo=timezone.utc),
                    )
                    for kind, extension in (
                        ("video", "mp4"),
                        ("subtitle", "srt"),
                        ("voice", "wav"),
                        ("timeline", "json"),
                    )
                ],
            ]
        )

    app = create_app(
        Settings(
            database_url=f"sqlite:///{database_path}",
            core_base_url="https://core.example.test",
            core_request_token="core-token",
        )
    )
    app.dependency_overrides[get_auth_service] = FakeAuthService
    with TestClient(app) as client:
        yield client
    engine.dispose()


def test_get_project_result_returns_completed_owner_artifacts(
    project_result_fixture: TestClient,
) -> None:
    response = project_result_fixture.get(
        "/api/v1/projects/prj_completed/result",
        headers={"Authorization": "Bearer owner-token"},
    )

    assert response.status_code == 200
    assert response.json()["code"] == "PROJECT_RESULT"
    assert response.json()["data"] == {
        "project_id": "prj_completed",
        "artifacts": [
            {
                "id": f"art_{kind}",
                "kind": kind,
                "cdn_url": f"https://cdn.example.test/exports/{kind}.{extension}",
            }
            for kind, extension in (
                ("subtitle", "srt"),
                ("timeline", "json"),
                ("video", "mp4"),
                ("voice", "wav"),
            )
        ],
    }


@pytest.mark.parametrize(
    ("token", "project_id"),
    [
        ("other-token", "prj_completed"),
        ("owner-token", "prj_missing"),
        ("owner-token", "prj_created"),
    ],
)
def test_get_project_result_never_returns_unavailable_project_result(
    project_result_fixture: TestClient, token: str, project_id: str
) -> None:
    response = project_result_fixture.get(
        f"/api/v1/projects/{project_id}/result",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 404
    assert response.json()["data"] is None


def test_get_project_result_requires_authentication(
    project_result_fixture: TestClient,
) -> None:
    response = project_result_fixture.get("/api/v1/projects/prj_completed/result")

    assert response.status_code == 401
    assert response.json()["code"] == "AUTHENTICATION_REQUIRED"


@pytest.mark.parametrize(
    "project_id", ["prj_completed", "prj_failed", "prj_created", "prj_settings"]
)
def test_eligible_owner_can_request_project_deletion_idempotently(
    project_result_fixture: TestClient, project_id: str
) -> None:
    """终态或分析前项目创建一个审计 Job，并原子切换为 deleting。"""

    first = project_result_fixture.post(
        f"/api/v1/projects/{project_id}/deletion-requests",
        headers={"Authorization": "Bearer owner-token"},
    )
    second = project_result_fixture.post(
        f"/api/v1/projects/{project_id}/deletion-requests",
        headers={"Authorization": "Bearer owner-token"},
    )

    assert first.status_code == second.status_code == 202
    assert first.json()["code"] == second.json()["code"] == "PROJECT_DELETION_REQUESTED"
    assert first.json()["data"]["project_id"] == project_id
    assert first.json()["data"]["status"] == "pending"
    assert second.json()["data"] == first.json()["data"]
    with Session(project_result_fixture.app.state.database_engine) as session:
        jobs = list(
            session.query(DeletionJob).filter(DeletionJob.project_id == project_id)
        )
        project = session.get(Project, project_id)
    assert len(jobs) == 1
    assert jobs[0].user_id == "usr_owner"
    assert jobs[0].status == "pending"
    assert jobs[0].created_at is not None and jobs[0].updated_at is not None
    assert project is not None and project.status == "deleting"
    listed = project_result_fixture.get(
        f"/api/v1/projects?query={project_id}",
        headers={"Authorization": "Bearer owner-token"},
    )
    assert listed.json()["data"] == {
        "items": [],
        "page": 1,
        "page_size": 10,
        "total": 0,
    }


@pytest.mark.parametrize(
    "project_id",
    [
        "prj_analyzing",
        "prj_rendering",
        "prj_deleting",
        "prj_deleted",
        "prj_missing",
    ],
)
def test_processing_deletion_state_or_missing_project_cannot_request_deletion(
    project_result_fixture: TestClient, project_id: str
) -> None:
    response = project_result_fixture.post(
        f"/api/v1/projects/{project_id}/deletion-requests",
        headers={"Authorization": "Bearer owner-token"},
    )

    expected_status = 404 if project_id == "prj_missing" else 409
    expected_code = (
        "PROJECT_NOT_FOUND" if project_id == "prj_missing" else "PROJECT_NOT_TERMINAL"
    )
    assert (response.status_code, response.json()["code"]) == (
        expected_status,
        expected_code,
    )
    if expected_status == 409:
        assert response.json()["message"] == (
            "Project cannot be deleted in its current state"
        )


def test_foreign_project_cannot_request_deletion(
    project_result_fixture: TestClient,
) -> None:
    response = project_result_fixture.post(
        "/api/v1/projects/prj_completed/deletion-requests",
        headers={"Authorization": "Bearer other-token"},
    )

    assert (response.status_code, response.json()["code"], response.json()["data"]) == (
        404,
        "PROJECT_NOT_FOUND",
        None,
    )
