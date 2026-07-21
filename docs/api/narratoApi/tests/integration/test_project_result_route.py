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
                ),
                Project(
                    id="prj_draft",
                    user_id="usr_owner",
                    product="short_drama",
                    status="draft",
                ),
                Project(
                    id="prj_failed",
                    user_id="usr_owner",
                    product="short_drama",
                    status="failed",
                ),
                RegisteredArtifact(
                    id="art_render",
                    project_id="prj_completed",
                    kind="video",
                    cdn_url="https://cdn.example.test/exports/render.mp4",
                    created_at=datetime(2026, 7, 17, tzinfo=timezone.utc),
                ),
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
                "id": "art_render",
                "kind": "video",
                "cdn_url": "https://cdn.example.test/exports/render.mp4",
            }
        ],
    }


@pytest.mark.parametrize(
    ("token", "project_id"),
    [
        ("other-token", "prj_completed"),
        ("owner-token", "prj_missing"),
        ("owner-token", "prj_draft"),
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


@pytest.mark.parametrize("project_id", ["prj_completed", "prj_failed"])
def test_terminal_owner_can_request_project_deletion_once(
    project_result_fixture: TestClient, project_id: str
) -> None:
    """终态项目创建审计 Job 并将项目原子切换为 deleting。"""

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


@pytest.mark.parametrize("project_id", ["prj_draft", "prj_missing"])
def test_non_terminal_or_missing_project_cannot_request_deletion(
    project_result_fixture: TestClient, project_id: str
) -> None:
    response = project_result_fixture.post(
        f"/api/v1/projects/{project_id}/deletion-requests",
        headers={"Authorization": "Bearer owner-token"},
    )

    expected_status = 409 if project_id == "prj_draft" else 404
    expected_code = (
        "PROJECT_NOT_TERMINAL" if project_id == "prj_draft" else "PROJECT_NOT_FOUND"
    )
    assert (response.status_code, response.json()["code"]) == (
        expected_status,
        expected_code,
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
