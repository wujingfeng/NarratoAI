from __future__ import annotations

from collections.abc import Iterator

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from narrato_api.assets.models import Asset
from narrato_api.auth.models import User
from narrato_api.auth.router import get_auth_service
from narrato_api.config import Settings
from narrato_api.database import Base
from narrato_api.main import create_app
from narrato_api.projects.models import Project, ProjectNarrationSettings


class FakeAuthService:
    def resolve_user(self, token: str) -> User:
        assert token == "valid-token"
        return User(id="usr_1", email="owner@example.test", password_hash="hash")


def _asset(
    *, asset_id: str, project_id: str = "prj_1", asset_type: str = "audio"
) -> Asset:
    return Asset(
        id=asset_id,
        user_id="usr_1",
        project_id=project_id,
        asset_type=asset_type,
        status="ready",
        filename="theme.mp3",
        bucket="narrato",
        object_key=f"narrato/api/{asset_id}.mp3",
        cdn_url=f"https://cdn.example.test/{asset_id}.mp3",
        size_bytes=100,
    )


def _headers() -> dict[str, str]:
    return {"Authorization": "Bearer valid-token"}


@pytest.fixture
def app_fixture(tmp_path) -> Iterator[tuple[TestClient, sessionmaker]]:
    database_path = tmp_path / "settings.db"
    engine = create_engine(f"sqlite:///{database_path}")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    with sessions.begin() as session:
        session.add(User(id="usr_1", email="owner@example.test", password_hash="hash"))
        session.add(
            Project(id="prj_1", user_id="usr_1", product="short_drama", status="draft")
        )
        session.add(
            Project(
                id="prj_other", user_id="usr_1", product="short_drama", status="draft"
            )
        )
        session.add(_asset(asset_id="ast_audio"))
        session.add(_asset(asset_id="ast_video", asset_type="video"))
        session.add(_asset(asset_id="ast_other", project_id="prj_other"))
    app = create_app(Settings(database_url=f"sqlite:///{database_path}"))
    app.dependency_overrides[get_auth_service] = FakeAuthService
    with TestClient(app) as client:
        yield client, sessions
    engine.dispose()


def test_background_music_setting_can_be_saved_read_and_removed(app_fixture) -> None:
    client, _sessions = app_fixture

    saved = client.patch(
        "/api/v1/projects/prj_1/narration/settings",
        headers=_headers(),
        json={"background_music_asset_id": "ast_audio", "background_music_volume": 72},
    )
    assert saved.status_code == 200
    assert saved.json()["data"]["background_music"] == {
        "asset_id": "ast_audio",
        "filename": "theme.mp3",
        "cdn_url": "https://cdn.example.test/ast_audio.mp3",
        "volume": 72,
    }

    read = client.get("/api/v1/projects/prj_1/narration/settings", headers=_headers())
    assert read.status_code == 200
    assert read.json()["data"] == saved.json()["data"]

    unchanged = client.patch(
        "/api/v1/projects/prj_1/narration/settings", headers=_headers(), json={}
    )
    assert unchanged.status_code == 200
    assert unchanged.json()["data"] == saved.json()["data"]

    volume_only = client.patch(
        "/api/v1/projects/prj_1/narration/settings",
        headers=_headers(),
        json={"background_music_volume": 33},
    )
    assert volume_only.status_code == 200
    assert volume_only.json()["data"]["background_music"]["asset_id"] == "ast_audio"
    assert volume_only.json()["data"]["background_music"]["volume"] == 33

    removed = client.patch(
        "/api/v1/projects/prj_1/narration/settings",
        headers=_headers(),
        json={"background_music_asset_id": None},
    )
    assert removed.status_code == 200
    assert removed.json()["data"]["background_music"] is None


def test_background_music_rejects_non_audio_cross_project_and_invalid_volume(
    app_fixture,
) -> None:
    client, _sessions = app_fixture
    for asset_id in ("ast_video", "ast_other"):
        response = client.patch(
            "/api/v1/projects/prj_1/narration/settings",
            headers=_headers(),
            json={"background_music_asset_id": asset_id, "background_music_volume": 50},
        )
        assert (response.status_code, response.json()["code"]) == (
            409,
            "BACKGROUND_MUSIC_ASSET_INVALID",
        )
    invalid = client.patch(
        "/api/v1/projects/prj_1/narration/settings",
        headers=_headers(),
        json={"background_music_asset_id": "ast_audio", "background_music_volume": 101},
    )
    assert (invalid.status_code, invalid.json()["code"]) == (422, "VALIDATION_ERROR")


def test_background_music_volume_only_requires_an_existing_selection(
    app_fixture,
) -> None:
    client, _sessions = app_fixture

    response = client.patch(
        "/api/v1/projects/prj_1/narration/settings",
        headers=_headers(),
        json={"background_music_volume": 50},
    )

    assert (response.status_code, response.json()["code"]) == (
        422,
        "BACKGROUND_MUSIC_ASSET_REQUIRED",
    )


@pytest.mark.parametrize(
    "status",
    ["queued", "analyzing", "waiting_for_edit", "render_queued", "rendering"],
)
def test_background_music_can_change_before_task_completion(
    app_fixture, status: str
) -> None:
    client, sessions = app_fixture
    with sessions.begin() as session:
        project = session.get(Project, "prj_1")
        assert project is not None
        project.status = status

    response = client.patch(
        "/api/v1/projects/prj_1/narration/settings",
        headers=_headers(),
        json={"background_music_asset_id": "ast_audio", "background_music_volume": 68},
    )

    assert response.status_code == 200
    assert response.json()["data"]["background_music"]["volume"] == 68


@pytest.mark.parametrize("status", ["completed", "failed", "deleting", "deleted"])
def test_background_music_remains_locked_after_task_completion(
    app_fixture, status: str
) -> None:
    client, sessions = app_fixture
    with sessions.begin() as session:
        project = session.get(Project, "prj_1")
        assert project is not None
        project.status = status

    response = client.patch(
        "/api/v1/projects/prj_1/narration/settings",
        headers=_headers(),
        json={"background_music_asset_id": "ast_audio", "background_music_volume": 68},
    )

    assert (response.status_code, response.json()["code"]) == (
        409,
        "PROJECT_SETTINGS_LOCKED",
    )


@pytest.mark.parametrize("status", ["deleting", "deleted"])
def test_narration_fields_cannot_change_after_deletion_starts(
    app_fixture, status: str
) -> None:
    client, sessions = app_fixture
    with sessions.begin() as session:
        project = session.get(Project, "prj_1")
        assert project is not None
        project.status = status

    response = client.patch(
        "/api/v1/projects/prj_1/narration/settings",
        headers=_headers(),
        json={"requirements": "late write"},
    )

    assert (response.status_code, response.json()["code"]) == (
        409,
        "PROJECT_SETTINGS_LOCKED",
    )
    with sessions() as session:
        assert session.get(ProjectNarrationSettings, "prj_1") is None
