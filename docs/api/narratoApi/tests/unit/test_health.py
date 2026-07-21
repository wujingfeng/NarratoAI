from __future__ import annotations

import asyncio
import threading
import time

import pytest

from fastapi.testclient import TestClient

from narrato_api.api.dependencies import (
    BoundedReadinessExecutor,
    get_readiness_checker,
)
from narrato_api.config import Settings
from narrato_api.database import create_database_engine, get_engine
from narrato_api.main import create_app


def _settings(tmp_path) -> Settings:
    return Settings(
        database_url=f"sqlite:///{tmp_path / 'business.db'}",
        redis_url="redis://127.0.0.1:6379/15",
        core_base_url="https://core.example.test",
        core_request_token="request-secret",
        core_callback_token="callback-secret",
        verification_code_hmac_secret="test-hmac-secret-with-at-least-32-bytes",
        smtp_host="smtp.example.test",
        smtp_username="smtp-user",
        smtp_password="smtp-password",
        smtp_sender="noreply@example.test",
    )


def test_live_returns_typed_envelope_without_dependency_access(tmp_path) -> None:
    app = create_app(_settings(tmp_path))

    async def must_not_run() -> None:
        raise AssertionError("live probe accessed dependencies")

    app.dependency_overrides[get_readiness_checker] = lambda: must_not_run
    with TestClient(app) as client:
        response = client.get(
            "/api/v1/health/live", headers={"X-Request-ID": "req_live-1"}
        )

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "req_live-1"
    assert response.json() == {
        "code": "OK",
        "message": "Service is live",
        "data": {"status": "live"},
        "request_id": "req_live-1",
    }


def test_ready_returns_503_when_database_fails(tmp_path) -> None:
    app = create_app(_settings(tmp_path))

    async def failed() -> None:
        raise RuntimeError("postgresql://user:secret@local/private")

    app.dependency_overrides[get_readiness_checker] = lambda: failed
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/api/v1/health/ready")

    assert response.status_code == 503
    assert response.json()["code"] == "SERVICE_UNAVAILABLE"
    assert "secret" not in response.text
    assert "/private" not in response.text


def test_ready_returns_503_when_redis_fails(tmp_path) -> None:
    app = create_app(_settings(tmp_path))

    async def failed() -> None:
        raise ConnectionError("redis password leaked")

    app.dependency_overrides[get_readiness_checker] = lambda: failed
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/api/v1/health/ready")

    assert response.status_code == 503
    assert response.json()["message"] == "Service dependencies are unavailable"
    assert "password" not in response.text


@pytest.mark.parametrize(
    "updates",
    [
        {"verification_code_hmac_secret": ""},
        {"verification_code_hmac_secret": "short"},
        {"smtp_host": ""},
        {"smtp_sender": ""},
        {"smtp_use_starttls": False},
        {"smtp_username": ""},
        {"smtp_password": ""},
        {"verification_code_send_lease_seconds": 10, "smtp_timeout_seconds": 10},
        {"verification_code_send_lease_seconds": 600},
    ],
)
def test_readiness_rejects_incomplete_auth_and_mail_configuration(
    tmp_path, updates
) -> None:
    from narrato_api.api.dependencies import required_configuration_is_present

    assert (
        required_configuration_is_present(
            _settings(tmp_path).model_copy(update=updates)
        )
        is False
    )


def test_ready_endpoint_fails_closed_for_missing_auth_secret(tmp_path) -> None:
    settings = _settings(tmp_path).model_copy(
        update={"verification_code_hmac_secret": ""}
    )
    app = create_app(settings)
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/api/v1/health/ready")
    assert response.status_code == 503
    assert response.json()["code"] == "SERVICE_UNAVAILABLE"


def test_readiness_fails_when_independent_celery_broker_is_down(
    tmp_path, monkeypatch
) -> None:
    import narrato_api.api.dependencies as dependencies_module

    class FakeRedis:
        async def ping(self) -> bool:
            return True

        async def aclose(self) -> None:
            return None

    monkeypatch.setattr(
        dependencies_module, "create_redis_client", lambda _settings: FakeRedis()
    )
    monkeypatch.setattr(dependencies_module, "check_database", lambda _settings: None)

    def broker_down(_settings) -> None:
        raise ConnectionError("broker unavailable")

    monkeypatch.setattr(dependencies_module, "check_celery_broker", broker_down)
    app = create_app(_settings(tmp_path))
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/api/v1/health/ready")
    assert response.status_code == 503
    assert response.json()["code"] == "SERVICE_UNAVAILABLE"


def test_broker_probe_cleanup_closes_app_when_connection_close_fails(
    tmp_path, monkeypatch
) -> None:
    import narrato_api.api.dependencies as dependencies_module

    events: list[str] = []
    close_error = RuntimeError("connection close failed")

    class Channel:
        def close(self) -> None:
            events.append("channel.close")

    class Connection:
        def ensure_connection(self, **kwargs) -> None:
            del kwargs

        def channel(self):
            return Channel()

        def close(self) -> None:
            events.append("connection.close")
            raise close_error

    class App:
        def connection_for_write(self):
            return Connection()

        def close(self) -> None:
            events.append("app.close")

    monkeypatch.setattr(
        dependencies_module, "create_celery_app", lambda _settings: App()
    )
    with pytest.raises(RuntimeError) as caught:
        dependencies_module.check_celery_broker(_settings(tmp_path))
    assert caught.value is close_error
    assert events == ["channel.close", "connection.close", "app.close"]


def test_broker_probe_preserves_original_error_while_all_cleanup_runs(
    tmp_path, monkeypatch
) -> None:
    import narrato_api.api.dependencies as dependencies_module

    events: list[str] = []
    original = KeyboardInterrupt()

    class Connection:
        def ensure_connection(self, **kwargs) -> None:
            del kwargs
            raise original

        def close(self) -> None:
            events.append("connection.close")
            raise RuntimeError("secondary connection cleanup")

    class App:
        def connection_for_write(self):
            return Connection()

        def close(self) -> None:
            events.append("app.close")
            raise RuntimeError("secondary app cleanup")

    monkeypatch.setattr(
        dependencies_module, "create_celery_app", lambda _settings: App()
    )
    with pytest.raises(KeyboardInterrupt) as caught:
        dependencies_module.check_celery_broker(_settings(tmp_path))
    assert caught.value is original
    assert events == ["connection.close", "app.close"]


def test_bounded_executor_times_out_without_unbounded_submission() -> None:
    executor = BoundedReadinessExecutor(max_workers=1)
    release = threading.Event()

    def blocked() -> None:
        release.wait(1)

    async def exercise() -> None:
        try:
            await executor.run(blocked, timeout=0.01)
        except TimeoutError:
            pass
        else:
            raise AssertionError("expected timeout")
        try:
            await executor.run(blocked, timeout=0.01)
        except RuntimeError as error:
            assert str(error) == "READINESS_BUSY"
        else:
            raise AssertionError("capacity must reject queued work")

    asyncio.run(exercise())
    assert executor.submitted == 1
    release.set()
    deadline = time.monotonic() + 0.5
    while time.monotonic() < deadline:
        try:
            asyncio.run(executor.run(lambda: None, timeout=0.1))
        except RuntimeError:
            time.sleep(0.01)
        else:
            break
    else:
        raise AssertionError("worker capacity was not released after actual completion")
    executor.close()


def test_shutdown_rejects_new_readiness_work() -> None:
    executor = BoundedReadinessExecutor(max_workers=1)
    executor.close()

    async def exercise() -> None:
        try:
            await executor.run(lambda: None, timeout=0.01)
        except RuntimeError as error:
            assert str(error) == "READINESS_CLOSED"
        else:
            raise AssertionError("closed executor accepted work")

    asyncio.run(exercise())


def test_default_readiness_timeout_is_bounded(tmp_path, monkeypatch) -> None:
    settings = _settings(tmp_path).model_copy(
        update={"readiness_timeout_seconds": 0.02}
    )
    app = create_app(settings)

    def slow_database() -> None:
        time.sleep(0.15)

    monkeypatch.setattr(
        "narrato_api.api.dependencies.check_database", lambda _settings: slow_database()
    )
    started = time.monotonic()
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/api/v1/health/ready")
    elapsed = time.monotonic() - started

    assert response.status_code == 503
    assert elapsed < 0.12


def test_database_engine_applies_connect_and_statement_deadlines(monkeypatch) -> None:
    import narrato_api.database as database_module

    captured: dict[str, object] = {}
    real_create_engine = database_module.create_engine

    def capture(_url: str, **kwargs: object):
        captured.update(kwargs)
        return real_create_engine("sqlite://")

    monkeypatch.setattr(database_module, "create_engine", capture)
    create_database_engine("postgresql+psycopg://business@db/narrato", 2.1, 0.075)

    connect_args = captured["connect_args"]
    assert isinstance(connect_args, dict)
    assert connect_args["connect_timeout"] == 2
    assert "statement_timeout=75" in str(connect_args["options"])
    assert captured["pool_timeout"] == 0.075


def test_sqlite_readiness_uses_busy_timeout(tmp_path) -> None:
    engine = create_database_engine(f"sqlite:///{tmp_path / 'busy.db'}", 1.0, 0.075)
    with engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA busy_timeout").scalar_one() == 75
    engine.dispose()


def test_lifespan_disposes_database_pool_and_checker_rejects_after_shutdown(
    tmp_path, monkeypatch
) -> None:
    import narrato_api.api.dependencies as dependencies_module

    settings = _settings(tmp_path)
    engine = get_engine(settings)
    redis_closed = 0

    class FakeRedis:
        async def ping(self) -> bool:
            return True

        async def aclose(self) -> None:
            nonlocal redis_closed
            redis_closed += 1

    monkeypatch.setattr(
        dependencies_module, "create_redis_client", lambda _settings: FakeRedis()
    )
    monkeypatch.setattr(
        dependencies_module, "check_celery_broker", lambda _settings: None
    )
    app = create_app(settings)
    with TestClient(app) as client:
        assert client.get("/api/v1/health/ready").status_code == 200
        checker = dependencies_module.DefaultReadinessChecker(
            settings, app.state.readiness_executor
        )
        assert engine.pool.checkedin() >= 1

    assert engine.pool.checkedin() == 0
    assert redis_closed == 1
    assert app.state.readiness_executor.closed is True
    with pytest.raises(dependencies_module.ServiceUnavailableError):
        asyncio.run(checker())
    assert get_engine(settings) is not engine


def test_nested_apps_only_release_their_owned_database_engine(
    tmp_path, monkeypatch
) -> None:
    import narrato_api.api.dependencies as dependencies_module

    class FakeRedis:
        async def ping(self) -> bool:
            return True

        async def aclose(self) -> None:
            return None

    monkeypatch.setattr(
        dependencies_module, "create_redis_client", lambda _settings: FakeRedis()
    )
    monkeypatch.setattr(
        dependencies_module, "check_celery_broker", lambda _settings: None
    )
    settings_a = _settings(tmp_path).model_copy(
        update={"database_url": f"sqlite:///{tmp_path / 'a.db'}"}
    )
    settings_b = _settings(tmp_path).model_copy(
        update={"database_url": f"sqlite:///{tmp_path / 'b.db'}"}
    )
    app_a = create_app(settings_a)
    app_b = create_app(settings_b)

    with TestClient(app_a) as client_a:
        assert client_a.get("/api/v1/health/ready").status_code == 200
        engine_a = get_engine(settings_a)
        with TestClient(app_b) as client_b:
            assert client_b.get("/api/v1/health/ready").status_code == 200
            engine_b = get_engine(settings_b)
            assert engine_b is not engine_a
        assert get_engine(settings_a) is engine_a
        with engine_a.connect() as connection:
            assert connection.exec_driver_sql("SELECT 1").scalar_one() == 1
    assert engine_a.pool.checkedin() == 0


def test_nested_apps_with_same_settings_reference_count_shared_engine(
    tmp_path, monkeypatch
) -> None:
    import narrato_api.api.dependencies as dependencies_module

    class FakeRedis:
        async def ping(self) -> bool:
            return True

        async def aclose(self) -> None:
            return None

    monkeypatch.setattr(
        dependencies_module, "create_redis_client", lambda _settings: FakeRedis()
    )
    monkeypatch.setattr(
        dependencies_module, "check_celery_broker", lambda _settings: None
    )
    settings = _settings(tmp_path).model_copy(
        update={"database_url": f"sqlite:///{tmp_path / 'shared.db'}"}
    )
    app_a = create_app(settings)
    app_b = create_app(settings)

    with TestClient(app_a) as client_a:
        assert client_a.get("/api/v1/health/ready").status_code == 200
        engine = get_engine(settings)
        with TestClient(app_b) as client_b:
            assert client_b.get("/api/v1/health/ready").status_code == 200
            assert get_engine(settings) is engine
        assert get_engine(settings) is engine
        with engine.connect() as connection:
            assert connection.exec_driver_sql("SELECT 1").scalar_one() == 1
    assert engine.pool.checkedin() == 0
