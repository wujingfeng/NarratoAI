from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from narrato_api.artifacts.models import RegisteredArtifact
from narrato_api.auth.models import User
from narrato_api.auth.router import get_auth_service
from narrato_api.config import Settings
from narrato_api.database import Base
from narrato_api.main import create_app
from narrato_api.projects.models import Project


class FakeAuthService:
    def resolve_user(self, token: str) -> User:
        if token == "owner-token":
            return User(id="usr_owner", email="owner@example.test", password_hash="hash")
        if token == "other-token":
            return User(id="usr_other", email="other@example.test", password_hash="hash")
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
