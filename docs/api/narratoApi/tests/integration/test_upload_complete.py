from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from narrato_api.assets.models import Asset
from narrato_api.assets.router import get_core_client, get_oss_client
from narrato_api.auth.models import User
from narrato_api.auth.router import get_auth_service
from narrato_api.config import Settings
from narrato_api.database import Base
from narrato_api.integrations.core_client import (
    CoreClientRejectedError,
    MediaProbeResult,
)
from narrato_api.integrations.oss_client import OssObject
from narrato_api.main import create_app
from narrato_api.projects.models import Project


class FakeAuthService:
    def __init__(self, user: User) -> None:
        self.user = user

    def resolve_user(self, token: str) -> User:
        if token != "valid-token":
            raise RuntimeError("unexpected token")
        return self.user


class FakeOssClient:
    def __init__(self, object: OssObject) -> None:
        self.object = object
        self.head_calls: list[tuple[str, str]] = []
        self.delete_calls: list[tuple[str, str]] = []

    def head_object(self, bucket: str, object_key: str) -> OssObject:
        self.head_calls.append((bucket, object_key))
        return self.object

    def public_url(self, bucket: str, object_key: str) -> str:
        return f"https://cdn.example.test/{bucket}/{object_key}"

    def delete_object(self, bucket: str, object_key: str) -> None:
        self.delete_calls.append((bucket, object_key))


class FakeCoreClient:
    def __init__(self, result: MediaProbeResult) -> None:
        self.result = result
        self.calls: list[dict[str, str]] = []
        self.poll_result = MediaProbeResult(valid=None, core_task_id="core_1")
        self.poll_calls: list[str] = []

    def probe_media(self, **kwargs: str) -> MediaProbeResult:
        self.calls.append(kwargs)
        return self.result

    def get_probe_result(self, core_task_id: str) -> MediaProbeResult:
        self.poll_calls.append(core_task_id)
        return self.poll_result


@pytest.fixture
def upload_fixture(
    tmp_path,
) -> Iterator[tuple[TestClient, sessionmaker, FakeOssClient, FakeCoreClient]]:
    database_path = tmp_path / "uploads.db"
    engine = create_engine(f"sqlite:///{database_path}")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    with sessions.begin() as session:
        session.add(User(id="usr_1", email="owner@example.test", password_hash="hash"))
        session.add(Project(id="prj_1", user_id="usr_1", product="short_drama"))

    oss = FakeOssClient(OssObject(size_bytes=100, content_type="video/mp4"))
    core = FakeCoreClient(MediaProbeResult(valid=True, duration_seconds=120.5))
    app = create_app(
        Settings(
            database_url=f"sqlite:///{database_path}",
            oss_endpoint="oss-cn-shanghai.aliyuncs.com",
            oss_url="https://narrato.oss-cn-shanghai.aliyuncs.com",
            cdn_public_base_url="https://cdn.example.test",
            oss_bucket="narrato",
            oss_access_key_id="key",
            oss_access_key_secret="secret",
            core_base_url="https://core.example.test",
            core_request_token="core-token",
        )
    )
    app.dependency_overrides[get_auth_service] = lambda: FakeAuthService(
        User(id="usr_1", email="owner@example.test", password_hash="hash")
    )
    app.dependency_overrides[get_oss_client] = lambda: oss
    app.dependency_overrides[get_core_client] = lambda: core
    with TestClient(app) as client:
        yield client, sessions, oss, core
    engine.dispose()


def _payload() -> dict[str, object]:
    return {
        "asset_type": "video",
        "filename": "episode.mp4",
        "size_bytes": 100,
        "content_type": "video/mp4",
        "object_key": "narrato/api/2026/07/17/object.mp4",
    }


def _issued_payload(client: TestClient) -> dict[str, object]:
    payload = _payload()
    response = client.post(
        "/api/v1/projects/prj_1/uploads/policy",
        headers={"Authorization": "Bearer valid-token"},
        json={
            key: payload[key]
            for key in ("asset_type", "filename", "size_bytes", "content_type")
        },
    )
    assert response.status_code == 200
    assert (
        response.json()["data"]["url"] == "https://narrato.oss-cn-shanghai.aliyuncs.com"
    )
    payload["object_key"] = response.json()["data"]["key"]
    return payload


def test_upload_complete_heads_object_dispatches_probe_and_marks_asset_ready(
    upload_fixture,
) -> None:
    client, sessions, oss, core = upload_fixture

    payload = _issued_payload(client)
    response = client.post(
        "/api/v1/projects/prj_1/uploads/complete",
        headers={"Authorization": "Bearer valid-token"},
        json=payload,
    )

    assert response.status_code == 202
    assert response.json()["data"]["status"] == "ready"
    assert oss.head_calls == [("narrato", payload["object_key"])]
    assert core.calls[0]["media_type"] == "video"
    with sessions() as session:
        asset = session.get(Asset, response.json()["data"]["id"])
        assert asset is not None and asset.status == "ready"
        assert asset.cdn_url == f"https://cdn.example.test/{payload['object_key']}"
        assert asset.duration_seconds == 120.5


def test_upload_complete_marks_asset_invalid_when_core_rejects_media(
    upload_fixture,
) -> None:
    client, sessions, _oss, core = upload_fixture
    core.result = MediaProbeResult(valid=False)

    response = client.post(
        "/api/v1/projects/prj_1/uploads/complete",
        headers={"Authorization": "Bearer valid-token"},
        json=_issued_payload(client),
    )

    assert response.status_code == 202
    assert response.json()["data"]["status"] == "invalid"
    with sessions() as session:
        asset = session.get(Asset, response.json()["data"]["id"])
        assert asset is not None and asset.status == "invalid"


def test_upload_complete_exposes_core_request_rejection_as_validation_error(
    upload_fixture,
) -> None:
    client, _sessions, _oss, core = upload_fixture

    def reject_probe(**_kwargs: str) -> MediaProbeResult:
        raise CoreClientRejectedError("invalid declaration")

    core.probe_media = reject_probe  # type: ignore[method-assign]
    response = client.post(
        "/api/v1/projects/prj_1/uploads/complete",
        headers={"Authorization": "Bearer valid-token"},
        json=_issued_payload(client),
    )

    assert (response.status_code, response.json()["code"]) == (
        422,
        "MEDIA_PROBE_REJECTED",
    )


def test_owner_can_remove_pre_start_asset_and_its_oss_object(upload_fixture) -> None:
    client, sessions, oss, _core = upload_fixture
    payload = _issued_payload(client)
    completed = client.post(
        "/api/v1/projects/prj_1/uploads/complete",
        headers={"Authorization": "Bearer valid-token"},
        json=payload,
    )
    asset_id = completed.json()["data"]["id"]

    removed = client.post(
        f"/api/v1/projects/prj_1/assets/{asset_id}/remove",
        headers={"Authorization": "Bearer valid-token"},
    )

    assert removed.status_code == 200
    assert removed.json()["code"] == "ASSET_REMOVED"
    assert oss.delete_calls == [("narrato", payload["object_key"])]
    with sessions() as session:
        assert session.get(Asset, asset_id) is None


def test_owner_can_remove_asset_when_oss_cleanup_is_temporarily_unavailable(
    upload_fixture,
) -> None:
    client, sessions, oss, _core = upload_fixture
    from narrato_api.integrations.oss_client import OssClientError

    completed = client.post(
        "/api/v1/projects/prj_1/uploads/complete",
        headers={"Authorization": "Bearer valid-token"},
        json=_issued_payload(client),
    )
    asset_id = completed.json()["data"]["id"]

    def unavailable(_bucket: str, _object_key: str) -> None:
        raise OssClientError("temporary failure")

    oss.delete_object = unavailable  # type: ignore[method-assign]
    removed = client.post(
        f"/api/v1/projects/prj_1/assets/{asset_id}/remove",
        headers={"Authorization": "Bearer valid-token"},
    )

    assert removed.status_code == 200
    with sessions() as session:
        assert session.get(Asset, asset_id) is None


def test_owner_can_persist_complete_video_order_before_project_starts(
    upload_fixture,
) -> None:
    client, sessions, _oss, _core = upload_fixture
    asset_ids: list[str] = []
    for _ in range(2):
        completed = client.post(
            "/api/v1/projects/prj_1/uploads/complete",
            headers={"Authorization": "Bearer valid-token"},
            json=_issued_payload(client),
        )
        assert completed.status_code == 202
        asset_ids.append(completed.json()["data"]["id"])

    reordered = client.post(
        "/api/v1/projects/prj_1/assets/order",
        headers={"Authorization": "Bearer valid-token"},
        json={"asset_ids": list(reversed(asset_ids))},
    )

    assert reordered.status_code == 200
    assert reordered.json()["data"]["asset_ids"] == list(reversed(asset_ids))
    with sessions() as session:
        persisted = list(
            session.query(Asset)
            .filter(Asset.id.in_(asset_ids))
            .order_by(Asset.sort_order)
        )
    assert [asset.id for asset in persisted] == list(reversed(asset_ids))
    assert [asset.sort_order for asset in persisted] == [0, 1]


def test_video_order_rejects_partial_or_locked_project_order(upload_fixture) -> None:
    client, sessions, _oss, _core = upload_fixture
    asset_ids: list[str] = []
    for _ in range(2):
        completed = client.post(
            "/api/v1/projects/prj_1/uploads/complete",
            headers={"Authorization": "Bearer valid-token"},
            json=_issued_payload(client),
        )
        asset_ids.append(completed.json()["data"]["id"])

    partial = client.post(
        "/api/v1/projects/prj_1/assets/order",
        headers={"Authorization": "Bearer valid-token"},
        json={"asset_ids": [asset_ids[0]]},
    )
    assert (partial.status_code, partial.json()["code"]) == (
        422,
        "PROJECT_ASSET_ORDER_INVALID",
    )

    with sessions.begin() as session:
        project = session.get(Project, "prj_1")
        assert project is not None
        project.current_stage = "analysis"
        project.status = "analyzing"

    locked = client.post(
        "/api/v1/projects/prj_1/assets/order",
        headers={"Authorization": "Bearer valid-token"},
        json={"asset_ids": asset_ids},
    )
    assert (locked.status_code, locked.json()["code"]) == (
        409,
        "PROJECT_ASSET_ORDER_LOCKED",
    )


@pytest.mark.parametrize("status", ["deleting", "deleted"])
def test_deletion_state_fences_upload_completion_policy_and_reorder(
    upload_fixture, status: str
) -> None:
    client, sessions, oss, core = upload_fixture
    payload = _issued_payload(client)
    with sessions.begin() as session:
        project = session.get(Project, "prj_1")
        assert project is not None
        project.status = status

    complete = client.post(
        "/api/v1/projects/prj_1/uploads/complete",
        headers={"Authorization": "Bearer valid-token"},
        json=payload,
    )
    policy = client.post(
        "/api/v1/projects/prj_1/uploads/policy",
        headers={"Authorization": "Bearer valid-token"},
        json={
            key: payload[key]
            for key in ("asset_type", "filename", "size_bytes", "content_type")
        },
    )
    with sessions() as session:
        asset_id = session.query(Asset.id).filter(Asset.project_id == "prj_1").one()[0]
    reordered = client.post(
        "/api/v1/projects/prj_1/assets/order",
        headers={"Authorization": "Bearer valid-token"},
        json={"asset_ids": [asset_id]},
    )

    assert (complete.status_code, complete.json()["code"]) == (
        409,
        "PROJECT_ASSET_LOCKED",
    )
    assert (policy.status_code, policy.json()["code"]) == (
        409,
        "PROJECT_ASSET_LOCKED",
    )
    assert (reordered.status_code, reordered.json()["code"]) == (
        409,
        "PROJECT_ASSET_ORDER_LOCKED",
    )
    assert oss.head_calls == []
    assert core.calls == []


def test_upload_complete_rechecks_project_lock_before_core_result_writeback(
    upload_fixture,
) -> None:
    client, sessions, _oss, core = upload_fixture
    payload = _issued_payload(client)

    def finish_after_deletion(**_kwargs: str) -> MediaProbeResult:
        with sessions.begin() as session:
            project = session.get(Project, "prj_1")
            assert project is not None
            project.status = "deleting"
        return MediaProbeResult(valid=True, duration_seconds=120.5)

    core.probe_media = finish_after_deletion  # type: ignore[method-assign]
    response = client.post(
        "/api/v1/projects/prj_1/uploads/complete",
        headers={"Authorization": "Bearer valid-token"},
        json=payload,
    )

    assert (response.status_code, response.json()["code"]) == (
        409,
        "PROJECT_ASSET_LOCKED",
    )
    with sessions() as session:
        asset = session.query(Asset).filter(Asset.project_id == "prj_1").one()
        assert asset.status == "validating"
        assert asset.duration_seconds is None
        assert asset.reservation_expires_at is None


def test_upload_policy_requires_authenticated_user(upload_fixture) -> None:
    client, _sessions, _oss, _core = upload_fixture

    response = client.post(
        "/api/v1/projects/prj_1/uploads/policy",
        json={
            "asset_type": "video",
            "filename": "episode.mp4",
            "size_bytes": 100,
            "content_type": "video/mp4",
        },
    )

    assert response.status_code == 401
    assert response.json()["code"] == "AUTHENTICATION_REQUIRED"


def test_upload_policy_accepts_supported_audio_declaration(upload_fixture) -> None:
    client, _sessions, _oss, _core = upload_fixture

    response = client.post(
        "/api/v1/projects/prj_1/uploads/policy",
        headers={"Authorization": "Bearer valid-token"},
        json={
            "asset_type": "audio",
            "filename": "theme.mp3",
            "size_bytes": 100,
            "content_type": "audio/mpeg",
        },
    )

    assert response.status_code == 200
    assert response.json()["data"]["fields"]["Content-Type"] == "audio/mpeg"


def test_complete_rejects_unissued_or_other_project_object_key(upload_fixture) -> None:
    client, _sessions, _oss, _core = upload_fixture

    response = client.post(
        "/api/v1/projects/prj_1/uploads/complete",
        headers={"Authorization": "Bearer valid-token"},
        json=_payload(),
    )

    assert response.status_code == 422
    assert response.json()["code"] == "UPLOAD_OBJECT_REJECTED"


def test_asset_read_reconciles_later_succeeded_core_probe_for_owner(
    upload_fixture,
) -> None:
    client, sessions, _oss, core = upload_fixture
    core.result = MediaProbeResult(valid=None, core_task_id="core_1")

    complete = client.post(
        "/api/v1/projects/prj_1/uploads/complete",
        headers={"Authorization": "Bearer valid-token"},
        json=_issued_payload(client),
    )

    assert complete.status_code == 202
    assert complete.json()["data"]["status"] == "validating"
    assert core.poll_calls == []
    asset_id = complete.json()["data"]["id"]
    with sessions() as session:
        asset = session.get(Asset, asset_id)
        assert asset is not None and asset.core_task_id == "core_1"

    core.poll_result = MediaProbeResult(
        valid=True, core_task_id="core_1", duration_seconds=90.0
    )
    fetched = client.get(
        f"/api/v1/assets/{asset_id}", headers={"Authorization": "Bearer valid-token"}
    )

    assert fetched.status_code == 200
    assert fetched.json()["data"]["status"] == "ready"
    assert core.poll_calls == ["core_1"]
    with sessions() as session:
        asset = session.get(Asset, asset_id)
        assert asset is not None and asset.status == "ready"
        assert asset.duration_seconds == 90.0


def test_asset_read_rejects_core_probe_writeback_after_deletion_starts(
    upload_fixture,
) -> None:
    client, sessions, _oss, core = upload_fixture
    core.result = MediaProbeResult(valid=None, core_task_id="core_1")
    complete = client.post(
        "/api/v1/projects/prj_1/uploads/complete",
        headers={"Authorization": "Bearer valid-token"},
        json=_issued_payload(client),
    )
    asset_id = complete.json()["data"]["id"]
    with sessions.begin() as session:
        project = session.get(Project, "prj_1")
        assert project is not None
        project.status = "deleting"
    core.poll_result = MediaProbeResult(
        valid=True, core_task_id="core_1", duration_seconds=90.0
    )

    fetched = client.get(
        f"/api/v1/assets/{asset_id}", headers={"Authorization": "Bearer valid-token"}
    )

    assert (fetched.status_code, fetched.json()["code"]) == (
        409,
        "PROJECT_ASSET_LOCKED",
    )
    with sessions() as session:
        asset = session.get(Asset, asset_id)
        assert asset is not None and asset.status == "validating"
        assert asset.duration_seconds is None


def test_upload_complete_maps_oss_head_failure_to_service_unavailable(
    upload_fixture,
) -> None:
    client, _sessions, oss, _core = upload_fixture

    from narrato_api.integrations.oss_client import OssClientError

    def unavailable(_bucket: str, _object_key: str) -> OssObject:
        raise OssClientError("temporary failure")

    oss.head_object = unavailable  # type: ignore[method-assign]
    response = client.post(
        "/api/v1/projects/prj_1/uploads/complete",
        headers={"Authorization": "Bearer valid-token"},
        json=_issued_payload(client),
    )

    assert response.status_code == 503
    assert response.json()["code"] == "OSS_UNAVAILABLE"


def test_expired_upload_reservations_do_not_permanently_consume_video_quota(
    upload_fixture,
) -> None:
    client, sessions, _oss, _core = upload_fixture
    request = {
        "asset_type": "video",
        "filename": "episode.mp4",
        "size_bytes": 100,
        "content_type": "video/mp4",
    }
    for _ in range(5):
        assert (
            client.post(
                "/api/v1/projects/prj_1/uploads/policy",
                headers={"Authorization": "Bearer valid-token"},
                json=request,
            ).status_code
            == 200
        )
    with sessions.begin() as session:
        for asset in session.query(Asset).all():
            asset.reservation_expires_at = datetime.now(timezone.utc) - timedelta(
                seconds=1
            )

    response = client.post(
        "/api/v1/projects/prj_1/uploads/policy",
        headers={"Authorization": "Bearer valid-token"},
        json=request,
    )

    assert response.status_code == 200
