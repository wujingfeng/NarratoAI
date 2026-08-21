from __future__ import annotations

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from narrato_api.admin.models import AdminOperationLog, AdminUser
from narrato_api.admin.service import password_hasher
from narrato_api.artifacts.models import RegisteredArtifact
from narrato_api.assets.models import Asset
from narrato_api.auth.models import User
from narrato_api.config import Settings
from narrato_api.main import create_app
from narrato_api.products.model_generation import (
    ModelTask,
    ModelTaskAsset,
    ModelTaskOutput,
)
from narrato_api.projects.models import Project, ProjectNarrationSettings
from narrato_api.workflows.models import (
    Workflow,
    WorkflowNode,
    WorkflowNodeAttempt,
    WorkflowTemplateSnapshot,
)


def _settings(database_url: str) -> Settings:
    return Settings(
        database_url=database_url,
        verification_code_hmac_secret="v" * 32,
        admin_session_hmac_secret="a" * 32,
        admin_bootstrap_password="AdminPass123",
        admin_cors_origins="https://admin.example.test",
        smtp_timeout_seconds=1,
        smtp_total_deadline_seconds=2,
        verification_code_send_lease_seconds=10,
        verification_code_ttl_seconds=60,
    )


def test_admin_routes_use_migrated_rbac_and_audit(tmp_path, monkeypatch) -> None:
    database_url = f"sqlite:///{tmp_path / 'admin.db'}"
    monkeypatch.setenv("NARRATO_API_DATABASE_URL", database_url)
    command.upgrade(Config("alembic.ini"), "head")
    settings = _settings(database_url)
    engine = create_engine(database_url)

    with TestClient(create_app(settings)) as client:
        preflight = client.options(
            "/api/v1/admin/auth/login",
            headers={
                "Origin": "https://admin.example.test",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Authorization,Content-Type",
            },
        )
        assert preflight.status_code == 200
        assert (
            preflight.headers["access-control-allow-origin"]
            == "https://admin.example.test"
        )
        login = client.post(
            "/api/v1/admin/auth/login",
            json={"username": "Admin", "password": "AdminPass123"},
        )
        assert login.status_code == 200
        admin_token = login.json()["data"]["token"]
        headers = {"Authorization": f"Bearer {admin_token}"}

        with Session(engine) as session:
            session.add(
                User(
                    id="usr_admin_route_test",
                    email="route-test@example.com",
                    password_hash="not-used-by-admin-route",
                )
            )
            session.add(
                AdminUser(
                    id="adm_limited_route_test",
                    username="limited",
                    display_name="Limited",
                    password_hash=password_hasher(settings).hash("LimitedPass123"),
                )
            )
            session.add(
                Project(
                    id="prj_admin_task_detail",
                    user_id="usr_admin_route_test",
                    product="ai_video",
                    status="completed",
                    current_stage="export",
                )
            )
            session.add(
                Asset(
                    id="ast_admin_task_input",
                    user_id="usr_admin_route_test",
                    project_id="prj_admin_task_detail",
                    asset_type="video",
                    status="ready",
                    filename="source.mp4",
                    bucket="test",
                    object_key="input/source.mp4",
                    cdn_url="https://cdn.example.test/input/source.mp4",
                    size_bytes=1024,
                )
            )
            session.add(
                ModelTask(
                    id="mt_admin_task_detail",
                    project_id="prj_admin_task_detail",
                    user_id="usr_admin_route_test",
                    model_id="model_test",
                    play_mode_id="mode_test",
                    provider_id="provider_test",
                    task_type="video",
                    status="succeeded",
                    idempotency_key="admin-route-detail",
                    prompt="生成一段测试视频",
                    audio_enabled=True,
                )
            )
            session.add(
                ModelTaskAsset(
                    id="mta_admin_task_input",
                    task_id="mt_admin_task_detail",
                    asset_id="ast_admin_task_input",
                    input_type="video",
                )
            )
            session.add(
                ModelTaskOutput(
                    id="mto_admin_task_output",
                    task_id="mt_admin_task_detail",
                    output_type="video",
                    cdn_url="https://cdn.example.test/output/final.mp4",
                    duration_seconds=8.5,
                )
            )
            session.add(
                Project(
                    id="prj_admin_workflow_detail",
                    user_id="usr_admin_route_test",
                    product="short_drama_narration",
                    status="completed",
                    current_stage="export",
                )
            )
            session.add(
                ProjectNarrationSettings(
                    project_id="prj_admin_workflow_detail",
                    settings={"video_ratio": "9:16", "voice_id": "voice_test"},
                )
            )
            session.add(
                WorkflowTemplateSnapshot(
                    id="wts_admin_task_detail",
                    template_name="short_drama_narration",
                    version="test",
                    definition={},
                )
            )
            session.add(
                Workflow(
                    id="wf_admin_task_detail",
                    user_id="usr_admin_route_test",
                    project_id="prj_admin_workflow_detail",
                    template_snapshot_id="wts_admin_task_detail",
                    state="completed",
                )
            )
            session.add(
                WorkflowNode(
                    id="wn_admin_task_detail",
                    workflow_id="wf_admin_task_detail",
                    name="video_render",
                    state="completed",
                )
            )
            session.add(
                WorkflowNodeAttempt(
                    id="wna_admin_task_detail",
                    workflow_node_id="wn_admin_task_detail",
                    attempt_number=1,
                    state="completed",
                    core_task_id="core_admin_task_detail",
                )
            )
            session.add(
                RegisteredArtifact(
                    id="art_admin_task_detail",
                    project_id="prj_admin_workflow_detail",
                    kind="video",
                    cdn_url="https://cdn.example.test/result/final.mp4",
                    content_type="video/mp4",
                    duration=12.0,
                )
            )
            session.commit()

        assert client.get("/api/v1/admin/overview", headers=headers).status_code == 200
        menu_tree = client.get("/api/v1/admin/menus/tree", headers=headers)
        assert menu_tree.status_code == 200
        assert any(
            item["code"] == "dashboard" and item["path"] == "/overview"
            for item in menu_tree.json()["data"]["items"]
        )
        for path in (
            "/api/v1/admin/tasks?category=short_drama",
            "/api/v1/admin/models",
            "/api/v1/admin/play-modes",
            "/api/v1/admin/providers",
            "/api/v1/admin/system-configs",
            "/api/v1/admin/admins",
            "/api/v1/admin/roles",
            "/api/v1/admin/permissions",
            "/api/v1/admin/menus",
            "/api/v1/admin/credit-ledger",
            "/api/v1/admin/operation-logs",
        ):
            response = client.get(path, headers=headers)
            assert response.status_code == 200, response.text
            assert {"items", "total", "page", "page_size"} <= set(
                response.json()["data"]
            )
        task_list = client.get("/api/v1/admin/tasks", headers=headers)
        assert task_list.status_code == 200
        assert any(
            item["id"] == "mt_admin_task_detail"
            and item["user_name"] == "route-test@example.com"
            for item in task_list.json()["data"]["items"]
        )
        users = client.get("/api/v1/admin/users", headers=headers)
        assert users.status_code == 200
        assert users.json()["data"]["total"] == 1
        task_detail = client.get(
            "/api/v1/admin/tasks/mt_admin_task_detail", headers=headers
        )
        assert task_detail.status_code == 200, task_detail.text
        detail_data = task_detail.json()["data"]
        assert detail_data["input"]["prompt"] == "生成一段测试视频"
        assert detail_data["input"]["source_assets"][0]["url"].endswith("source.mp4")
        assert detail_data["result"]["outputs"][0]["url"].endswith("final.mp4")
        assert "provider_request" not in detail_data["task"]
        workflow_detail = client.get(
            "/api/v1/admin/tasks/wf_admin_task_detail", headers=headers
        )
        assert workflow_detail.status_code == 200, workflow_detail.text
        workflow_data = workflow_detail.json()["data"]
        assert workflow_data["input"]["settings"]["video_ratio"] == "9:16"
        assert workflow_data["result"]["artifacts"][0]["url"].endswith("final.mp4")
        assert workflow_data["execution"]["nodes"][0]["name"] == "video_render"
        batch = client.patch(
            "/api/v1/admin/users/batch-status",
            headers=headers,
            json={"user_ids": ["usr_admin_route_test"], "status": "disabled"},
        )
        assert batch.status_code == 200

        limited = client.post(
            "/api/v1/admin/auth/login",
            json={"username": "limited", "password": "LimitedPass123"},
        )
        limited_token = limited.json()["data"]["token"]
        denied = client.get(
            "/api/v1/admin/overview",
            headers={"Authorization": f"Bearer {limited_token}"},
        )
        assert (denied.status_code, denied.json()["code"]) == (
            403,
            "ADMIN_PERMISSION_DENIED",
        )

    with Session(engine) as session:
        user = session.get(User, "usr_admin_route_test")
        assert user is not None and user.status == "disabled"
        assert (
            session.scalar(
                select(AdminOperationLog).where(
                    AdminOperationLog.action == "admin.users.batch_status.update"
                )
            )
            is not None
        )
