from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from narrato_api.assets.models import Asset
from narrato_api.assets.router import get_upload_service
from narrato_api.auth.models import User
from narrato_api.auth.router import get_auth_service
from narrato_api.billing.models import CreditAccount, ProductPrice
from narrato_api.config import Settings
from narrato_api.database import Base
from narrato_api.main import create_app
from narrato_api.projects.models import (
    Project,
    ProjectBackgroundMusic,
    ProjectNarrationSettings,
)
from narrato_api.products.video_translation import VideoTranslationSettings
from narrato_api.workflows.models import (
    Workflow,
    WorkflowNode,
    WorkflowNodeAttempt,
    WorkflowOutbox,
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


@pytest.fixture
def lifecycle_client(tmp_path) -> Iterator[TestClient]:
    engine = create_engine(f"sqlite:///{tmp_path / 'lifecycle.db'}")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    with sessions.begin() as session:
        session.add_all(
            [
                User(id="usr_owner", email="owner@example.test", password_hash="hash"),
                User(id="usr_other", email="other@example.test", password_hash="hash"),
                CreditAccount(user_id="usr_owner", balance=100),
                ProductPrice(
                    product="short_drama_narration", version=1, credits_per_minute=20
                ),
                WorkflowTemplateSnapshot(
                    id="tpl_short_drama_v1",
                    template_name="short_drama_narration",
                    version="v1",
                    definition={"nodes": [{"name": "media_probe", "depends_on": []}]},
                ),
            ]
        )
    app = create_app(
        Settings(
            database_url=f"sqlite:///{tmp_path / 'lifecycle.db'}",
            core_base_url="https://core.example.test",
            core_request_token="core-token",
        )
    )
    app.dependency_overrides[get_auth_service] = FakeAuthService
    with TestClient(app) as client:
        yield client
    engine.dispose()


def _create_project(client: TestClient) -> str:
    response = client.post(
        "/api/v1/projects",
        headers={"Authorization": "Bearer owner-token"},
        json={"product": "short-drama-narration"},
    )
    assert response.status_code == 201
    assert response.json()["code"] == "PROJECT_CREATED"
    return response.json()["data"]["id"]


def _ready_video(
    client: TestClient,
    project_id: str,
    duration_seconds: float | None = 61,
    *,
    asset_id: str = "ast_ready",
    filename: str = "episode.mp4",
    sort_order: int = 0,
) -> None:
    with Session(client.app.state.database_engine) as session:
        session.add(
            Asset(
                id=asset_id,
                user_id="usr_owner",
                project_id=project_id,
                asset_type="video",
                status="ready",
                filename=filename,
                bucket="bucket",
                object_key=f"narrato/api/{project_id}/{filename}",
                cdn_url=f"https://cdn.example.test/{filename}",
                size_bytes=100,
                duration_seconds=duration_seconds,
                sort_order=sort_order,
            )
        )
        session.commit()


def _ready_background_music(client: TestClient, project_id: str) -> None:
    with Session(client.app.state.database_engine) as session:
        session.add(
            Asset(
                id="ast_bgm",
                user_id="usr_owner",
                project_id=project_id,
                asset_type="audio",
                status="ready",
                filename="theme.mp3",
                bucket="bucket",
                object_key=f"narrato/api/{project_id}/theme.mp3",
                cdn_url="https://cdn.example.test/theme.mp3",
                size_bytes=100,
            )
        )
        session.add(
            ProjectBackgroundMusic(project_id=project_id, asset_id="ast_bgm", volume=64)
        )
        session.commit()


def _start_analysis(client: TestClient, project_id: str):
    return client.post(
        f"/api/v1/projects/{project_id}/narration/settings/start-analysis",
        headers={"Authorization": "Bearer owner-token"},
        json={
            "narration_style": "霸总/甜宠",
            "video_ratio": "9:16",
            "voice_id": "BV700_V2_streaming",
            "subtitle_style": "经典白色",
        },
    )


def test_new_project_uses_ninety_percent_narration_subtitle_baseline(
    lifecycle_client: TestClient,
) -> None:
    project_id = _create_project(lifecycle_client)

    response = lifecycle_client.get(
        f"/api/v1/projects/{project_id}/narration/settings",
        headers={"Authorization": "Bearer owner-token"},
    )

    assert response.status_code == 200
    assert response.json()["data"]["narration_subtitle_position"] == {
        "y": 0.82,
        "font_scale": 0.9,
    }


def test_authenticated_owner_can_create_estimate_and_start_ready_project(
    lifecycle_client: TestClient,
) -> None:
    project_id = _create_project(lifecycle_client)
    _ready_video(lifecycle_client, project_id)

    estimate = lifecycle_client.post(
        f"/api/v1/projects/{project_id}/cost-estimate",
        headers={"Authorization": "Bearer owner-token"},
    )
    assert estimate.status_code == 200
    assert estimate.json()["data"] == {
        "credits": 40,
        "total_seconds": 61,
        "estimated_output_seconds": 10,
        "credits_per_minute": 20,
    }

    start = _start_analysis(lifecycle_client, project_id)
    assert start.status_code == 202
    assert start.json()["code"] == "PROJECT_ANALYSIS_STARTED"
    with Session(lifecycle_client.app.state.database_engine) as session:
        project = session.get(Project, project_id)
        workflow = (
            session.query(Workflow).filter(Workflow.project_id == project_id).one()
        )
        account = session.get(CreditAccount, "usr_owner")
    assert project is not None and project.status == "queued"
    assert workflow.state == "queued"
    assert account is not None and account.balance == 60
    settings = lifecycle_client.get(
        f"/api/v1/projects/{project_id}/narration/settings",
        headers={"Authorization": "Bearer owner-token"},
    )
    assert settings.status_code == 200
    assert settings.json()["data"]["original_sound_ratio"] == 30
    with Session(lifecycle_client.app.state.database_engine) as session:
        saved = session.get(ProjectNarrationSettings, project_id)
    assert saved is not None and saved.settings["original_sound_ratio"] == 30


def test_start_rejects_original_sound_ratio_outside_streamlit_options(
    lifecycle_client: TestClient,
) -> None:
    project_id = _create_project(lifecycle_client)
    _ready_video(lifecycle_client, project_id)
    response = lifecycle_client.post(
        f"/api/v1/projects/{project_id}/narration/settings/start-analysis",
        headers={"Authorization": "Bearer owner-token"},
        json={
            "narration_style": "逆袭/复仇",
            "video_ratio": "9:16",
            "voice_id": "BV700_V2_streaming",
            "subtitle_style": "经典白色",
            "original_sound_ratio": 35,
        },
    )
    assert response.status_code == 422


@pytest.mark.parametrize("source_status", ["draft", "analyzing", "completed", "failed"])
def test_any_visible_project_retry_creates_editable_draft_with_reused_video_and_subtitle(
    lifecycle_client: TestClient,
    source_status: str,
) -> None:
    source_project_id = _create_project(lifecycle_client)
    _ready_video(lifecycle_client, source_project_id)
    with Session(lifecycle_client.app.state.database_engine) as session:
        source = session.get(Project, source_project_id)
        assert source is not None
        source.status = source_status
        session.add(
            Asset(
                id="ast_subtitle",
                user_id="usr_owner",
                project_id=source_project_id,
                asset_type="subtitle",
                status="ready",
                filename="episode.srt",
                bucket="bucket",
                object_key=f"narrato/api/{source_project_id}/episode.srt",
                cdn_url="https://cdn.example.test/episode.srt",
                size_bytes=100,
            )
        )
        session.add(
            ProjectNarrationSettings(
                project_id=source_project_id,
                settings={
                    "source_subtitle_layouts": {
                        "ast_ready": {
                            "status": "confirmed",
                            "region": {"x": 0.12, "y": 0.68, "width": 0.72, "height": 0.16},
                            "detected_confidence": 0.91,
                        },
                        "ast_removed": {"status": "none", "region": None},
                    }
                },
            )
        )
        session.commit()

    retried = lifecycle_client.post(
        f"/api/v1/projects/{source_project_id}/retry-draft",
        headers={"Authorization": "Bearer owner-token"},
    )

    assert retried.status_code == 201
    retry_project_id = retried.json()["data"]["project_id"]
    assert retry_project_id != source_project_id
    stage = lifecycle_client.get(
        f"/api/v1/projects/{retry_project_id}/stage",
        headers={"Authorization": "Bearer owner-token"},
    )
    assert stage.status_code == 200
    assert stage.json()["data"]["project_status"] == "draft"
    assert stage.json()["data"]["video_assets"] == [
        {
            "id": stage.json()["data"]["video_assets"][0]["id"],
            "filename": "episode.mp4",
            "cdn_url": "https://cdn.example.test/episode.mp4",
            "duration_seconds": 61.0,
            "subtitle_asset_id": stage.json()["data"]["video_assets"][0][
                "subtitle_asset_id"
            ],
            "subtitle_filename": "episode.srt",
        }
    ]
    draft_video_id = stage.json()["data"]["video_assets"][0]["id"]
    settings_response = lifecycle_client.get(
        f"/api/v1/projects/{retry_project_id}/narration/settings",
        headers={"Authorization": "Bearer owner-token"},
    )
    assert settings_response.status_code == 200
    assert settings_response.json()["data"]["source_subtitle_layouts"] == {
        draft_video_id: {
            "status": "confirmed",
            "region": {"x": 0.12, "y": 0.68, "width": 0.72, "height": 0.16},
            "detected_confidence": 0.91,
        }
    }
    with Session(lifecycle_client.app.state.database_engine) as session:
        copied = list(session.query(Asset).filter(Asset.project_id == retry_project_id))
    assert {asset.asset_type for asset in copied} == {"video", "subtitle"}
    assert {asset.object_key for asset in copied} == {
        f"narrato/api/{source_project_id}/episode.mp4",
        f"narrato/api/{source_project_id}/episode.srt",
    }
    with Session(lifecycle_client.app.state.database_engine) as session:
        source = session.get(Project, source_project_id)
        assert source is not None
        assert source.status == source_status
        draft_settings = session.get(ProjectNarrationSettings, retry_project_id)
        assert draft_settings is not None
        assert draft_settings.settings == {
            "source_subtitle_layouts": {
                draft_video_id: {
                    "status": "confirmed",
                    "region": {"x": 0.12, "y": 0.68, "width": 0.72, "height": 0.16},
                    "detected_confidence": 0.91,
                }
            }
        }


def test_video_translation_retry_keeps_product_and_translation_settings(
    lifecycle_client: TestClient,
) -> None:
    created = lifecycle_client.post(
        "/api/v1/projects",
        headers={"Authorization": "Bearer owner-token"},
        json={"product": "video-translation"},
    )
    assert created.status_code == 201
    source_project_id = created.json()["data"]["id"]
    _ready_video(lifecycle_client, source_project_id)
    source_settings = {
        "target_language": "en",
        "video_ratio": "16:9",
        "execution_mode": "manual",
        "voice_id": "BV700_V2_streaming",
        "original_sound_mode": "translated_voice_only",
        "preserve_source_subtitles": True,
        "source_subtitle_region": {
            "x": 0.1, "y": 0.7, "width": 0.8, "height": 0.15
        },
        "translated_subtitle_region": {
            "x": 0.1, "y": 0.8, "width": 0.8, "height": 0.15
        },
        "background_music_asset_id": None,
        "background_music_volume": 50,
    }
    with Session(lifecycle_client.app.state.database_engine) as session:
        source = session.get(Project, source_project_id)
        assert source is not None
        source.status = "failed"
        session.add(
            VideoTranslationSettings(
                project_id=source_project_id, settings=source_settings
            )
        )
        session.commit()

    retried = lifecycle_client.post(
        f"/api/v1/projects/{source_project_id}/retry-draft",
        headers={"Authorization": "Bearer owner-token"},
    )

    assert retried.status_code == 201
    retry_project_id = retried.json()["data"]["project_id"]
    with Session(lifecycle_client.app.state.database_engine) as session:
        retry_project = session.get(Project, retry_project_id)
        retry_settings = session.get(VideoTranslationSettings, retry_project_id)
    assert retry_project is not None
    assert retry_project.product == "video_translation"
    assert retry_settings is not None
    assert retry_settings.settings == source_settings

    settings = lifecycle_client.get(
        f"/api/v1/projects/{retry_project_id}/video-translation/settings",
        headers={"Authorization": "Bearer owner-token"},
    )
    assert settings.status_code == 200
    assert settings.json()["data"]["target_language"] == "en"
    assert settings.json()["data"]["original_sound_mode"] == "translated_voice_only"


def test_project_without_ready_video_can_retry_as_empty_editable_draft(
    lifecycle_client: TestClient,
) -> None:
    source_project_id = _create_project(lifecycle_client)
    with Session(lifecycle_client.app.state.database_engine) as session:
        session.add(
            Asset(
                id="ast_orphan_subtitle",
                user_id="usr_owner",
                project_id=source_project_id,
                asset_type="subtitle",
                status="ready",
                filename="orphan.srt",
                bucket="bucket",
                object_key=f"narrato/api/{source_project_id}/orphan.srt",
                cdn_url="https://cdn.example.test/orphan.srt",
                size_bytes=100,
            )
        )
        session.commit()

    retried = lifecycle_client.post(
        f"/api/v1/projects/{source_project_id}/retry-draft",
        headers={"Authorization": "Bearer owner-token"},
    )

    assert retried.status_code == 201
    retry_project_id = retried.json()["data"]["project_id"]
    stage = lifecycle_client.get(
        f"/api/v1/projects/{retry_project_id}/stage",
        headers={"Authorization": "Bearer owner-token"},
    )
    assert stage.status_code == 200
    assert stage.json()["data"]["project_status"] == "draft"
    assert stage.json()["data"]["video_assets"] == []
    with Session(lifecycle_client.app.state.database_engine) as session:
        copied = list(session.query(Asset).filter(Asset.project_id == retry_project_id))
    assert copied == []


@pytest.mark.parametrize("source_status", ["deleting", "deleted"])
def test_project_being_deleted_cannot_create_retry_draft(
    lifecycle_client: TestClient,
    source_status: str,
) -> None:
    source_project_id = _create_project(lifecycle_client)
    with Session(lifecycle_client.app.state.database_engine) as session:
        source = session.get(Project, source_project_id)
        assert source is not None
        source.status = source_status
        session.commit()

    retried = lifecycle_client.post(
        f"/api/v1/projects/{source_project_id}/retry-draft",
        headers={"Authorization": "Bearer owner-token"},
    )

    assert (retried.status_code, retried.json()["code"]) == (
        409,
        "PROJECT_RETRY_FORBIDDEN",
    )


def test_start_snapshots_background_music_into_queued_outbox_event(
    lifecycle_client: TestClient,
) -> None:
    project_id = _create_project(lifecycle_client)
    _ready_video(lifecycle_client, project_id)
    _ready_background_music(lifecycle_client, project_id)

    started = _start_analysis(lifecycle_client, project_id)

    assert started.status_code == 202
    with Session(lifecycle_client.app.state.database_engine) as session:
        outbox = (
            session.query(WorkflowOutbox)
            .filter(
                WorkflowOutbox.idempotency_key == f"workflow-state:queued:{project_id}"
            )
            .one()
        )
    assert outbox.payload["background_music"] == {
        "asset_id": "ast_bgm",
        "cdn_url": "https://cdn.example.test/theme.mp3",
        "volume": 64,
    }
    assert outbox.payload["stage"] == "analysis"


def test_estimate_reconciles_legacy_ready_video_missing_duration(
    lifecycle_client: TestClient,
) -> None:
    """历史 ready 视频在报价前补回 Core 已探测到的时长。"""

    project_id = _create_project(lifecycle_client)
    _ready_video(lifecycle_client, project_id, duration_seconds=None)

    class UploadService:
        def reconcile_owned_project_assets(
            self, *, user_id: str, project_id: str
        ) -> None:
            assert user_id == "usr_owner"
            with Session(lifecycle_client.app.state.database_engine) as session:
                asset = session.get(Asset, "ast_ready")
                assert asset is not None and asset.project_id == project_id
                asset.duration_seconds = 60
                session.commit()

    lifecycle_client.app.dependency_overrides[get_upload_service] = UploadService
    try:
        estimate = lifecycle_client.post(
            f"/api/v1/projects/{project_id}/cost-estimate",
            headers={"Authorization": "Bearer owner-token"},
        )
    finally:
        lifecycle_client.app.dependency_overrides.pop(get_upload_service, None)

    assert estimate.status_code == 200
    assert estimate.json()["data"]["total_seconds"] == 60


def test_start_rejects_non_ready_or_foreign_project(
    lifecycle_client: TestClient,
) -> None:
    project_id = _create_project(lifecycle_client)
    not_ready = _start_analysis(lifecycle_client, project_id)
    foreign = lifecycle_client.post(
        f"/api/v1/projects/{project_id}/start",
        headers={"Authorization": "Bearer other-token"},
    )
    assert (not_ready.status_code, not_ready.json()["code"]) == (
        409,
        "PROJECT_ASSETS_NOT_READY",
    )
    assert (foreign.status_code, foreign.json()["code"]) == (404, "PROJECT_NOT_FOUND")


def test_projects_list_is_paginated_filtered_and_owner_scoped(
    lifecycle_client: TestClient,
) -> None:
    first = _create_project(lifecycle_client)
    second = _create_project(lifecycle_client)
    third = _create_project(lifecycle_client)
    _ready_video(lifecycle_client, first, 61)
    _ready_video(
        lifecycle_client,
        first,
        30,
        asset_id="ast_ready_second",
        filename="episode-2.mp4",
        sort_order=1,
    )
    with Session(lifecycle_client.app.state.database_engine) as session:
        session.get(Project, second).status = "completed"
        session.get(Project, third).status = "failed"
        session.add(
            Project(
                id="prj_other_user",
                user_id="usr_other",
                product="short_drama_narration",
                status="draft",
            )
        )
        session.add_all(
            [
                Project(
                    id="prj_deleting",
                    user_id="usr_owner",
                    product="short_drama_narration",
                    status="deleting",
                ),
                Project(
                    id="prj_deleted",
                    user_id="usr_owner",
                    product="short_drama_narration",
                    status="deleted",
                ),
            ]
        )
        session.commit()

    first_page = lifecycle_client.get(
        "/api/v1/projects?page=1&page_size=2",
        headers={"Authorization": "Bearer owner-token"},
    )
    assert first_page.status_code == 200
    body = first_page.json()
    assert body["code"] == "PROJECTS_LISTED"
    assert body["data"]["total"] == 3
    assert len(body["data"]["items"]) == 2
    assert {item["id"] for item in body["data"]["items"]}.isdisjoint(
        {"prj_other_user", "prj_deleting", "prj_deleted"}
    )

    completed = lifecycle_client.get(
        "/api/v1/projects?status=complete",
        headers={"Authorization": "Bearer owner-token"},
    )
    assert completed.json()["data"]["total"] == 1
    assert completed.json()["data"]["items"][0]["id"] == second

    by_id = lifecycle_client.get(
        f"/api/v1/projects?query={first[-8:]}",
        headers={"Authorization": "Bearer owner-token"},
    )
    first_item = by_id.json()["data"]["items"][0]
    assert first_item["id"] == first
    assert first_item["title"] == "episode.mp4"
    assert first_item["video_count"] == 2
    assert first_item["duration_seconds"] == 91


def test_stage_api_persists_settings_and_enforces_forward_only_flow(
    lifecycle_client: TestClient,
) -> None:
    project_id = _create_project(lifecycle_client)
    _ready_video(lifecycle_client, project_id)

    initial = lifecycle_client.get(
        f"/api/v1/projects/{project_id}/stage",
        headers={"Authorization": "Bearer owner-token"},
    )
    assert initial.json()["data"]["current_stage"] == "created"

    started = _start_analysis(lifecycle_client, project_id)
    assert started.status_code == 202
    stage = lifecycle_client.get(
        f"/api/v1/projects/{project_id}/stage",
        headers={"Authorization": "Bearer owner-token"},
    ).json()["data"]
    assert stage["current_stage"] == "analysis"
    assert [task["id"] for task in stage["analysis_tasks"]] == [
        "subtitle_recognition",
        "plot_structure",
        "conflict_highlights",
        "highlight_scoring",
        "script_generation",
    ]
    with Session(lifecycle_client.app.state.database_engine) as session:
        workflow = (
            session.query(Workflow).filter(Workflow.project_id == project_id).one()
        )
        nodes = list(session.query(WorkflowNode).filter_by(workflow_id=workflow.id))
    assert {node.name for node in nodes} == {
        "subtitle_recognition",
        "plot_structure",
        "conflict_highlights",
        "highlight_scoring",
        "script_generation",
        "waiting_for_edit",
        "video_render",
        "publish_artifacts",
    }

    blocked = lifecycle_client.post(
        f"/api/v1/projects/{project_id}/stage/advance",
        headers={"Authorization": "Bearer owner-token"},
        json={"target_stage": "edit"},
    )
    assert (blocked.status_code, blocked.json()["code"]) == (
        409,
        "PROJECT_ANALYSIS_INCOMPLETE",
    )

    with Session(lifecycle_client.app.state.database_engine) as session:
        workflow = (
            session.query(Workflow).filter(Workflow.project_id == project_id).one()
        )
        for node in session.query(WorkflowNode).filter_by(workflow_id=workflow.id):
            node.state = "completed"
            if node.name == "script_generation":
                session.add(
                    WorkflowNodeAttempt(
                        id="wat_script",
                        workflow_node_id=node.id,
                        attempt_number=1,
                        state="completed",
                        state_version=1,
                        result={
                            "result": {
                                "editor_draft": {
                                    "tracks": [
                                        {
                                            "type": "narration",
                                            "items": [
                                                {
                                                    "source_asset_id": "ast_ready",
                                                    "start": 0,
                                                    "end": 10,
                                                    "narration": "测试解说",
                                                },
                                            ],
                                        }
                                    ],
                                },
                            },
                        },
                    )
                )
        session.commit()

    advanced = lifecycle_client.post(
        f"/api/v1/projects/{project_id}/stage/advance",
        headers={"Authorization": "Bearer owner-token"},
        json={"target_stage": "edit"},
    )
    assert advanced.status_code == 200
    assert advanced.json()["data"]["current_stage"] == "edit"
    rewind = lifecycle_client.post(
        f"/api/v1/projects/{project_id}/stage/advance",
        headers={"Authorization": "Bearer owner-token"},
        json={"target_stage": "edit"},
    )
    assert (rewind.status_code, rewind.json()["code"]) == (
        409,
        "PROJECT_STAGE_ADVANCE_FORBIDDEN",
    )
