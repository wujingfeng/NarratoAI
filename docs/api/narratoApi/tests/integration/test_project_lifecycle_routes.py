from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from narrato_api.assets.models import Asset
from narrato_api.auth.models import User
from narrato_api.auth.router import get_auth_service
from narrato_api.billing.models import CreditAccount, ProductPrice
from narrato_api.config import Settings
from narrato_api.database import Base
from narrato_api.main import create_app
from narrato_api.projects.models import Project
from narrato_api.workflows.models import Workflow, WorkflowTemplateSnapshot


class FakeAuthService:
    def resolve_user(self, token: str) -> User:
        if token == "owner-token":
            return User(id="usr_owner", email="owner@example.test", password_hash="hash")
        if token == "other-token":
            return User(id="usr_other", email="other@example.test", password_hash="hash")
        raise RuntimeError("unexpected token")


@pytest.fixture
def lifecycle_client(tmp_path) -> Iterator[TestClient]:
    engine = create_engine(f"sqlite:///{tmp_path / 'lifecycle.db'}")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    with sessions.begin() as session:
        session.add_all([
            User(id="usr_owner", email="owner@example.test", password_hash="hash"),
            User(id="usr_other", email="other@example.test", password_hash="hash"),
            CreditAccount(user_id="usr_owner", balance=100),
            ProductPrice(product="short_drama_narration", version=1, credits_per_minute=20),
            WorkflowTemplateSnapshot(
                id="tpl_short_drama_v1", template_name="short_drama_narration", version="v1",
                definition={"nodes": [{"name": "media_probe", "depends_on": []}]},
            ),
        ])
    app = create_app(Settings(database_url=f"sqlite:///{tmp_path / 'lifecycle.db'}", core_base_url="https://core.example.test", core_request_token="core-token"))
    app.dependency_overrides[get_auth_service] = FakeAuthService
    with TestClient(app) as client:
        yield client
    engine.dispose()


def _create_project(client: TestClient) -> str:
    response = client.post("/api/v1/projects", headers={"Authorization": "Bearer owner-token"}, json={"product": "short-drama-narration"})
    assert response.status_code == 201
    assert response.json()["code"] == "PROJECT_CREATED"
    return response.json()["data"]["id"]


def _ready_video(client: TestClient, project_id: str, duration_seconds: int = 61) -> None:
    with Session(client.app.state.database_engine) as session:
        session.add(Asset(id="ast_ready", user_id="usr_owner", project_id=project_id, asset_type="video", status="ready", filename="episode.mp4", bucket="bucket", object_key=f"narrato/api/{project_id}/episode.mp4", cdn_url="https://cdn.example.test/episode.mp4", size_bytes=100, duration_seconds=duration_seconds))
        session.commit()


def test_authenticated_owner_can_create_estimate_and_start_ready_project(lifecycle_client: TestClient) -> None:
    project_id = _create_project(lifecycle_client)
    _ready_video(lifecycle_client, project_id)

    estimate = lifecycle_client.post(f"/api/v1/projects/{project_id}/cost-estimate", headers={"Authorization": "Bearer owner-token"})
    assert estimate.status_code == 200
    assert estimate.json()["data"] == {"credits": 40, "total_seconds": 61, "credits_per_minute": 20}

    start = lifecycle_client.post(f"/api/v1/projects/{project_id}/start", headers={"Authorization": "Bearer owner-token"})
    assert start.status_code == 202
    assert start.json()["code"] == "PROJECT_STARTED"
    with Session(lifecycle_client.app.state.database_engine) as session:
        project = session.get(Project, project_id)
        workflow = session.query(Workflow).filter(Workflow.project_id == project_id).one()
        account = session.get(CreditAccount, "usr_owner")
    assert project is not None and project.status == "queued"
    assert workflow.state == "queued"
    assert account is not None and account.balance == 60


def test_start_rejects_non_ready_or_foreign_project(lifecycle_client: TestClient) -> None:
    project_id = _create_project(lifecycle_client)
    not_ready = lifecycle_client.post(f"/api/v1/projects/{project_id}/start", headers={"Authorization": "Bearer owner-token"})
    foreign = lifecycle_client.post(f"/api/v1/projects/{project_id}/start", headers={"Authorization": "Bearer other-token"})
    assert (not_ready.status_code, not_ready.json()["code"]) == (409, "PROJECT_ASSETS_NOT_READY")
    assert (foreign.status_code, foreign.json()["code"]) == (404, "PROJECT_NOT_FOUND")
