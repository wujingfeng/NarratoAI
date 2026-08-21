from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from narrato_api.api.errors import ServiceUnavailableError
from narrato_api.api.responses import ApiResponse, envelope
from narrato_api.config import Settings
from narrato_api.internal.router import (
    get_analysis_core_client,
    get_workflow_orchestrator,
    get_workflow_reconciler,
)
from narrato_api.main import create_app


def test_shared_response_envelope_has_only_protocol_fields() -> None:
    payload = {"project_id": "prj_contract_business"}

    actual = envelope(
        request_id="req_contract_business",
        code="PROJECT_CREATED",
        message="Project created",
        data=payload,
    )

    assert actual == {
        "code": "PROJECT_CREATED",
        "message": "Project created",
        "data": payload,
        "request_id": "req_contract_business",
    }
    with pytest.raises(ValidationError):
        ApiResponse(**actual, unexpected="not part of the public protocol")


def test_stable_service_unavailable_error_code() -> None:
    error = ServiceUnavailableError()

    assert error.code == "SERVICE_UNAVAILABLE"
    assert error.status_code == 503


def _callback_settings(tmp_path) -> Settings:
    return Settings(
        database_url=f"sqlite:///{tmp_path / 'callback-contract.db'}",
        core_base_url="https://core.example.test",
        core_request_token="core-request-secret",
        core_callback_token="core-callback-secret",
    )


def test_core_callback_requires_its_dedicated_bearer_token_and_event_idempotency_key(
    tmp_path,
) -> None:
    app = create_app(_callback_settings(tmp_path))
    seen: dict[str, object] = {}

    class FakeReconciler:
        def reconcile_callback(self, **event: object) -> bool:
            seen.update(event)
            return True

        def workflow_id_for_core_task(self, core_task_id: str) -> str:
            assert core_task_id == "ctask_7"
            return "wfl_callback"

    class FakeOrchestrator:
        def __init__(self) -> None:
            self.calls: list[tuple[str, object]] = []

        def dispatch_ready(self, *, workflow_id: str, core_client: object) -> bool:
            self.calls.append((workflow_id, core_client))
            return True

    core_client = object()
    orchestrator = FakeOrchestrator()

    app.dependency_overrides[get_workflow_reconciler] = FakeReconciler
    app.dependency_overrides[get_analysis_core_client] = lambda: core_client
    app.dependency_overrides[get_workflow_orchestrator] = lambda: orchestrator
    payload = {
        "event_id": "evt_core_task_7",
        "core_task_id": "ctask_7",
        "attempt_no": 2,
        "state_version": 7,
        "status": "succeeded",
        "result": {"artifact_id": "art_7"},
        "error": None,
    }
    with TestClient(app) as client:
        rejected = client.post("/api/v1/internal/core/callbacks", json=payload)
        mismatch = client.post(
            "/api/v1/internal/core/callbacks",
            headers={
                "Authorization": "Bearer core-callback-secret",
                "X-Idempotency-Key": "evt_other",
            },
            json=payload,
        )
        accepted = client.post(
            "/api/v1/internal/core/callbacks",
            headers={
                "Authorization": "Bearer core-callback-secret",
                "X-Idempotency-Key": "evt_core_task_7",
            },
            json=payload,
        )

    assert (rejected.status_code, rejected.json()["code"]) == (401, "UNAUTHORIZED")
    assert (mismatch.status_code, mismatch.json()["code"]) == (
        409,
        "CALLBACK_EVENT_ID_MISMATCH",
    )
    assert accepted.json() == {
        "code": "CORE_CALLBACK_ACCEPTED",
        "message": "Core callback accepted",
        "data": {"event_id": "evt_core_task_7", "accepted": True},
        "request_id": accepted.headers["X-Request-ID"],
    }
    assert seen == {
        "core_task_id": "ctask_7",
        "event_id": "evt_core_task_7",
        "state_version": 7,
        "state": "succeeded",
        "result": {
            "result": {"artifact_id": "art_7"},
            "error": None,
            "attempt_no": 2,
        },
    }
    assert orchestrator.calls == [("wfl_callback", core_client)]
    for response in (rejected, mismatch):
        assert set(response.json()) == {"code", "message", "data", "request_id"}
