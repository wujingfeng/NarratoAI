from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from narrato_api.assets.models import Asset
from narrato_api.auth.models import User
from narrato_api.auth.router import get_auth_service
from narrato_api.config import Settings
from narrato_api.database import Base
from narrato_api.projects.models import Project, ProjectNarrationSettings
from narrato_api.main import create_app
from narrato_api.workflows.models import (
    Workflow,
    WorkflowNode,
    WorkflowTemplateSnapshot,
)


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


def _renderable_draft(text: str) -> dict[str, object]:
    return {
        "clips": [
            {
                "id": "video-1",
                "track_id": "video",
                "start": 0,
                "duration": 5,
                "source_start": 0,
                "asset_id": "ast_video",
                "region_id": "region-1",
            },
            {
                "id": "script-1",
                "track_id": "script",
                "start": 0,
                "duration": 5,
                "text": text,
                "region_id": "region-1",
            },
        ],
        "subtitles": [{"start": 0, "end": 5, "text": text}],
        "settings": {"voice_role": "voice-1"},
    }


@pytest.fixture
def editor_client(tmp_path) -> Iterator[TestClient]:
    path = tmp_path / "editor.db"
    engine = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine)() as session:
        session.add_all(
            [
                User(id="usr_owner", email="owner@example.test", password_hash="hash"),
                User(id="usr_other", email="other@example.test", password_hash="hash"),
                Project(
                    id="prj_1",
                    user_id="usr_owner",
                    product="short_drama",
                    status="waiting_for_edit",
                    current_stage="edit",
                ),
                Asset(
                    id="ast_video",
                    user_id="usr_owner",
                    project_id="prj_1",
                    asset_type="video",
                    status="ready",
                    filename="episode.mp4",
                    bucket="test-bucket",
                    object_key="projects/prj_1/episode.mp4",
                    cdn_url="https://cdn.example.test/projects/prj_1/episode.mp4",
                    size_bytes=1024,
                    duration_seconds=5,
                ),
                ProjectNarrationSettings(
                    project_id="prj_1",
                    settings={
                        "voice_id": "voice-1",
                        "video_ratio": "9:16",
                        "subtitle_style": "classic",
                    },
                ),
                WorkflowTemplateSnapshot(
                    id="tpl_1", template_name="short_drama", version="v1", definition={}
                ),
                Workflow(
                    id="wf_1",
                    user_id="usr_owner",
                    project_id="prj_1",
                    template_snapshot_id="tpl_1",
                    state="waiting_for_edit",
                ),
                WorkflowNode(
                    id="wnd_edit",
                    workflow_id="wf_1",
                    name="waiting_for_edit",
                    state="queued",
                    depends_on=["script_generation"],
                    retryable=False,
                    manual_gate=True,
                    max_attempts=1,
                ),
                WorkflowNode(
                    id="wnd_render",
                    workflow_id="wf_1",
                    name="video_render",
                    state="queued",
                    depends_on=["waiting_for_edit"],
                    retryable=True,
                    manual_gate=False,
                    max_attempts=3,
                ),
            ]
        )
        session.commit()
    app = create_app(
        Settings(
            database_url=f"sqlite:///{path}",
            core_base_url="https://core.example.test",
            core_request_token="token",
        )
    )
    app.dependency_overrides[get_auth_service] = FakeAuthService
    with TestClient(app) as client:
        yield client
    engine.dispose()


def test_editor_routes_authenticate_own_lww_save_and_lock_after_render(
    editor_client: TestClient,
) -> None:
    headers = {"Authorization": "Bearer owner-token"}
    assert editor_client.get("/api/v1/projects/prj_1/editor").status_code == 401
    assert (
        editor_client.post(
            "/api/v1/projects/prj_1/editor/save",
            headers={"Authorization": "Bearer other-token"},
            json={"content": {"tracks": []}},
        ).status_code
        == 404
    )

    first_draft = _renderable_draft("first")
    last_draft = _renderable_draft("last")
    first = editor_client.post(
        "/api/v1/projects/prj_1/editor/save",
        headers=headers,
        json={"content": first_draft},
    )
    second = editor_client.post(
        "/api/v1/projects/prj_1/editor/save",
        headers=headers,
        json={"content": last_draft},
    )
    assert first.status_code == second.status_code == 200
    draft_id = first.json()["data"]["draft_id"]
    assert second.json()["data"]["draft_id"] == draft_id
    current = editor_client.get("/api/v1/projects/prj_1/editor", headers=headers)
    assert current.status_code == 200
    assert current.json()["data"] == {
        "draft_id": draft_id,
        "content": last_draft,
        "locked": False,
    }

    submitted = editor_client.post(
        "/api/v1/projects/prj_1/render/submit",
        headers={**headers, "X-Idempotency-Key": "submit_1"},
    )
    repeated = editor_client.post(
        "/api/v1/projects/prj_1/render/submit",
        headers={**headers, "X-Idempotency-Key": "submit_1"},
    )
    assert submitted.status_code == repeated.status_code == 202
    assert submitted.json()["data"] == repeated.json()["data"] == {"accepted": True}
    assert (
        editor_client.post(
            "/api/v1/projects/prj_1/editor/save",
            headers=headers,
            json={"content": {"tracks": []}},
        ).status_code
        == 409
    )
    readonly = editor_client.get("/api/v1/projects/prj_1/editor", headers=headers)
    assert readonly.status_code == 200
    assert readonly.json()["data"]["locked"] is True


def test_render_submit_requires_idempotency_key(editor_client: TestClient) -> None:
    response = editor_client.post(
        "/api/v1/projects/prj_1/render/submit",
        headers={"Authorization": "Bearer owner-token"},
    )
    assert response.status_code == 422
