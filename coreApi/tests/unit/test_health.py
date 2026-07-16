from __future__ import annotations

import asyncio
import time

import httpx
from fastapi import APIRouter, Depends
from fastapi.testclient import TestClient

from core_api.api.dependencies import (
    get_readiness_checker,
    require_service_token,
    required_configuration_is_present,
)
from core_api.config import get_cached_settings
from core_api.main import create_app

from tests.conftest import FakeReadinessChecker


def test_health_returns_envelope(client):
    response = client.get("/api/v1/health/live")

    assert response.status_code == 200
    assert response.json()["code"] == "OK"
    assert response.json()["message"] == "服务存活"


def test_ready_returns_ok_when_dependencies_are_ready(client):
    response = client.get("/api/v1/health/ready")

    assert response.status_code == 200
    assert response.json()["code"] == "OK"


def test_ready_returns_safe_503_envelope(app, client):
    app.dependency_overrides[get_readiness_checker] = (
        lambda: FakeReadinessChecker(ready=False)
    )

    response = client.get("/api/v1/health/ready")

    assert response.status_code == 503
    assert response.json()["code"] == "SERVICE_UNAVAILABLE"
    assert response.json()["data"] is None
    assert "redis://" not in response.text
    assert "test-service-token" not in response.text


def test_required_configuration_includes_oss(settings):
    assert required_configuration_is_present(settings) is False

    configured = settings.model_copy(
        update={
            "oss_endpoint": "https://oss.example.invalid",
            "oss_bucket": "narrato-core",
            "oss_access_key_id": "test-key",
            "oss_access_key_secret": "test-secret",
        }
    )

    assert required_configuration_is_present(configured) is True


def test_app_state_settings_do_not_eagerly_reload_config(
    settings, monkeypatch, tmp_path
):
    application = create_app(settings=settings)
    router = APIRouter()

    @router.get("/settings-probe", dependencies=[Depends(require_service_token)])
    async def settings_probe() -> dict[str, bool]:
        return {"ok": True}

    application.include_router(router, prefix="/api/v1/test")
    monkeypatch.setenv("CORE_API_CONFIG", str(tmp_path / "missing.toml"))
    get_cached_settings.cache_clear()

    try:
        with TestClient(application, raise_server_exceptions=False) as test_client:
            response = test_client.get(
                "/api/v1/test/settings-probe",
                headers={"Authorization": "Bearer test-service-token"},
            )
    finally:
        get_cached_settings.cache_clear()

    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_slow_readiness_probe_does_not_block_event_loop(
    settings, monkeypatch
):
    class SlowConnection:
        def __enter__(self):
            time.sleep(0.2)
            return self

        def __exit__(self, *args):
            return None

        def execute(self, statement):
            return None

    class SlowEngine:
        def connect(self):
            return SlowConnection()

    class FakeRedis:
        async def ping(self):
            return True

        async def aclose(self):
            return None

    configured = settings.model_copy(
        update={
            "oss_endpoint": "https://oss.example.invalid",
            "oss_bucket": "narrato-core",
            "oss_access_key_id": "test-key",
            "oss_access_key_secret": "test-secret",
            "readiness_timeout_seconds": 0.05,
        }
    )
    monkeypatch.setattr(
        "core_api.api.dependencies.get_engine", lambda current: SlowEngine()
    )
    monkeypatch.setattr(
        "core_api.api.dependencies.Redis.from_url", lambda *args, **kwargs: FakeRedis()
    )

    async def probe() -> float:
        application = create_app(settings=configured)
        transport = httpx.ASGITransport(
            app=application, raise_app_exceptions=False
        )
        client = httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        )
        task = asyncio.create_task(client.get("/api/v1/health/ready"))
        await asyncio.sleep(0.01)
        live_started = time.monotonic()
        live_response = await client.get("/api/v1/health/live")
        live_duration = time.monotonic() - live_started
        ready_response = await task
        await client.aclose()
        assert live_response.status_code == 200
        assert ready_response.status_code == 503
        assert ready_response.json()["code"] == "SERVICE_UNAVAILABLE"
        return live_duration

    assert asyncio.run(probe()) < 0.08


def test_default_readiness_rejects_missing_required_config(settings):
    application = create_app(settings=settings)

    with TestClient(application, raise_server_exceptions=False) as test_client:
        response = test_client.get("/api/v1/health/ready")

    assert response.status_code == 503
    assert response.json()["code"] == "SERVICE_UNAVAILABLE"
    assert "test-service-token" not in response.text
