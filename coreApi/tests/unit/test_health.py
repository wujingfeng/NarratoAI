from __future__ import annotations

import asyncio
import threading
import pytest
import time

import httpx
from fastapi import APIRouter, Depends
from fastapi.testclient import TestClient

from core_api.api.dependencies import (
    BoundedReadinessExecutor,
    DefaultReadinessChecker,
    get_oss_readiness_checker,
    get_readiness_checker,
    require_service_token,
    required_configuration_is_present,
    run_bounded_oss_readiness_probe,
)
from core_api.infrastructure.oss_client import Oss2Client
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
    app.dependency_overrides[get_readiness_checker] = lambda: FakeReadinessChecker(
        ready=False
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


def test_required_configuration_rejects_invalid_task7_security_semantics(settings):
    base = settings.model_copy(
        update={
            "oss_endpoint": "https://oss.example.invalid",
            "oss_bucket": "narrato-core",
            "oss_access_key_id": "test-key",
            "oss_access_key_secret": "test-secret",
        }
    )
    assert (
        required_configuration_is_present(
            base.model_copy(update={"oss_endpoint": "http://oss.example.invalid"})
        )
        is False
    )
    assert (
        required_configuration_is_present(
            base.model_copy(update={"oss_public_base_url": "http://cdn.example.test"})
        )
        is False
    )
    assert (
        required_configuration_is_present(
            base.model_copy(update={"cdn_allowed_hosts": []})
        )
        is False
    )
    assert (
        required_configuration_is_present(
            base.model_copy(update={"work_root": "relative/work"})
        )
        is False
    )
    assert (
        required_configuration_is_present(base.model_copy(update={"callback_url": ""}))
        is False
    )
    assert (
        required_configuration_is_present(
            base.model_copy(
                update={"callback_url": "http://narrato.example.test/callback"}
            )
        )
        is False
    )
    assert (
        required_configuration_is_present(
            base.model_copy(
                update={"callback_url": "https://example.test:bad/callback"}
            )
        )
        is False
    )
    assert (
        required_configuration_is_present(
            base.model_copy(update={"callback_url": "https://127.0.0.1/callback"})
        )
        is False
    )


def test_ready_probes_oss_with_timeout_and_safe_error(settings, monkeypatch):
    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def execute(self, statement):
            return None

    class FakeEngine:
        def connect(self):
            return FakeConnection()

    class FakeRedis:
        async def ping(self):
            return True

        async def aclose(self):
            return None

    class SlowOssProbe:
        def __call__(self):
            time.sleep(0.2)
            raise RuntimeError("403 secret-provider-body")

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
        "core_api.api.dependencies.get_engine", lambda current: FakeEngine()
    )
    monkeypatch.setattr(
        "core_api.api.dependencies.Redis.from_url", lambda *args, **kwargs: FakeRedis()
    )
    application = create_app(configured)
    application.dependency_overrides[get_oss_readiness_checker] = lambda: SlowOssProbe()
    with TestClient(application, raise_server_exceptions=False) as client:
        response = client.get("/api/v1/health/ready")
    assert response.status_code == 503
    assert "secret-provider-body" not in response.text


def test_default_readiness_accepts_successful_fake_oss_probe(settings, monkeypatch):
    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def execute(self, statement):
            return None

    class FakeEngine:
        def connect(self):
            return FakeConnection()

    class FakeRedis:
        async def ping(self):
            return True

        async def aclose(self):
            return None

    calls: list[bool] = []

    def fake_oss_probe():
        calls.append(True)

    configured = settings.model_copy(
        update={
            "oss_endpoint": "https://oss.example.invalid",
            "oss_bucket": "narrato-core",
            "oss_access_key_id": "test-key",
            "oss_access_key_secret": "test-secret",
        }
    )
    monkeypatch.setattr(
        "core_api.api.dependencies.get_engine", lambda current: FakeEngine()
    )
    monkeypatch.setattr(
        "core_api.api.dependencies.Redis.from_url", lambda *args, **kwargs: FakeRedis()
    )
    asyncio.run(DefaultReadinessChecker(configured, fake_oss_probe)())
    assert calls == [True]


def test_oss2_readiness_passes_real_transport_timeout(monkeypatch):
    captured: list[object] = []

    class FakeAuth:
        def __init__(self, *_args):
            pass

    class FakeBucket:
        def __init__(self, *_args, connect_timeout=None, **_kwargs):
            captured.append(connect_timeout)

        def get_bucket_info(self):
            return None

    fake = type("FakeOss", (), {"Auth": FakeAuth, "Bucket": FakeBucket})
    monkeypatch.setitem(__import__("sys").modules, "oss2", fake)
    client = Oss2Client(
        endpoint="https://oss.example.invalid",
        bucket="core",
        access_key_id="key",
        access_key_secret="secret",
        public_base_url="https://cdn.example.test",
        connect_timeout=0.2,
        read_timeout=0.4,
    )
    client.check_ready()
    assert captured == [(0.2, 0.4)]


def test_repeated_oss_readiness_timeouts_have_bounded_concurrency():
    lock = threading.Lock()
    active = 0
    maximum = 0
    release = threading.Event()

    def blocked_probe() -> None:
        nonlocal active, maximum
        with lock:
            active += 1
            maximum = max(maximum, active)
        release.wait(0.2)
        with lock:
            active -= 1

    executor = BoundedReadinessExecutor(max_workers=2)

    async def exercise() -> None:
        calls = [
            asyncio.create_task(
                run_bounded_oss_readiness_probe(
                    blocked_probe, timeout=0.01, executor=executor
                )
            )
            for _ in range(102)
        ]
        await asyncio.gather(*calls, return_exceptions=True)

    asyncio.run(exercise())
    release.set()
    assert maximum <= 2
    assert executor.submitted <= 2
    executor.close()


def test_app_shutdown_closes_private_readiness_executor(settings):
    application = create_app(settings)
    executor = application.state.oss_readiness_executor
    with TestClient(application):
        assert executor.closed is False
    assert executor.closed is True
    with pytest.raises(RuntimeError, match="OSS_READINESS_BUSY"):
        asyncio.run(executor.run(lambda: None, timeout=0.01))


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


def test_slow_readiness_probe_does_not_block_event_loop(settings, monkeypatch):
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
        transport = httpx.ASGITransport(app=application, raise_app_exceptions=False)
        client = httpx.AsyncClient(transport=transport, base_url="http://testserver")
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
