from __future__ import annotations

import ast
import asyncio
from concurrent.futures import ThreadPoolExecutor
import io
import json
import logging
import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from narrato_api.celery_app import create_celery_app
from narrato_api.config import Settings, load_settings
from narrato_api.main import create_app
from narrato_api.logging import (
    JsonFormatter,
    acquire_logging_redactions,
    active_redaction_value_count,
    configure_logging,
    contains_configured_secret,
    release_logging_redactions,
)


def _managed_log_handler() -> logging.StreamHandler:
    """返回 narratoApi 唯一受管日志 Handler。"""

    return next(
        handler
        for handler in logging.getLogger("narrato_api").handlers
        if getattr(handler, "_narrato_managed", False)
        and isinstance(handler, logging.StreamHandler)
    )


def _settings(tmp_path) -> Settings:
    return Settings(
        database_url=f"sqlite:///{tmp_path / 'business.db'}",
        redis_url="redis://127.0.0.1:6379/15",
        redis_key_prefix="narrato:business:test:",
        celery_broker_url="redis://127.0.0.1:6379/14",
        celery_queue_prefix="narrato.business.test",
        core_base_url="https://core.example.test",
        core_request_token="request-secret",
        core_callback_token="callback-secret",
        verification_code_hmac_secret="test-hmac-secret-with-at-least-32-bytes",
        smtp_host="smtp.example.test",
        smtp_username="smtp-user",
        smtp_password="smtp-password",
        smtp_sender="noreply@example.test",
    )


def test_request_id_is_validated_and_matches_body(tmp_path) -> None:
    app = create_app(_settings(tmp_path))
    with TestClient(app) as client:
        accepted = client.get(
            "/api/v1/health/live", headers={"X-Request-ID": "trace.abc-123"}
        )
        rejected = client.get(
            "/api/v1/health/live", headers={"X-Request-ID": "evil\nheader"}
        )
        oversized = client.get(
            "/api/v1/health/live", headers={"X-Request-ID": "x" * 129}
        )

    assert accepted.json()["request_id"] == "trace.abc-123"
    for response in (rejected, oversized):
        request_id = response.json()["request_id"]
        assert request_id.startswith("req_")
        assert response.headers["X-Request-ID"] == request_id
        assert "evil" not in request_id


def test_404_405_and_422_use_stable_envelopes(tmp_path) -> None:
    app = create_app(_settings(tmp_path))
    with TestClient(app) as client:
        missing = client.get("/api/v1/missing")
        wrong_method = client.put("/api/v1/health/live")
        invalid = client.get("/api/v1/health/ready?details=not-a-boolean")

    assert (missing.status_code, missing.json()["code"]) == (404, "NOT_FOUND")
    assert (wrong_method.status_code, wrong_method.json()["code"]) == (
        405,
        "METHOD_NOT_ALLOWED",
    )
    assert (invalid.status_code, invalid.json()["code"]) == (422, "VALIDATION_ERROR")
    for response in (missing, wrong_method, invalid):
        assert set(response.json()) == {"code", "message", "data", "request_id"}
        assert response.headers["X-Request-ID"] == response.json()["request_id"]


def test_openapi_only_exposes_get_post_and_typed_responses(tmp_path) -> None:
    schema = create_app(_settings(tmp_path)).openapi()
    paths = schema["paths"]
    assert set(paths) == {
        "/api/v1/health/live",
        "/api/v1/health/ready",
        "/api/v1/auth/register-code/send",
        "/api/v1/auth/register",
        "/api/v1/auth/login",
        "/api/v1/auth/logout",
        "/api/v1/auth/password-code/send",
        "/api/v1/auth/password/reset",
        "/api/v1/users/me",
        "/api/v1/products/short-drama-narration/config",
        "/api/v1/projects",
        "/api/v1/projects/{project_id}/cost-estimate",
        "/api/v1/projects/{project_id}/start",
        "/api/v1/projects/{project_id}/narration/settings",
        "/api/v1/projects/{project_id}/narration/settings/start-analysis",
        "/api/v1/projects/{project_id}/stage",
        "/api/v1/projects/{project_id}/stage/advance",
        "/api/v1/projects/{project_id}/uploads/policy",
        "/api/v1/projects/{project_id}/uploads/complete",
        "/api/v1/projects/{project_id}/assets/{asset_id}/remove",
        "/api/v1/projects/{project_id}/assets/order",
        "/api/v1/projects/{project_id}/editor",
        "/api/v1/projects/{project_id}/editor/save",
        "/api/v1/projects/{project_id}/render/submit",
        "/api/v1/projects/{project_id}/deletion-requests",
        "/api/v1/projects/{project_id}/result",
        "/api/v1/projects/{project_id}/exports/jianying-manifest",
        "/api/v1/assets/{asset_id}",
        "/api/v1/internal/core/callbacks",
    }
    assert {
        method for path in paths.values() for method in path if method != "parameters"
    } <= {"get", "post", "patch"}
    for path in paths.values():
        for method, operation in path.items():
            if method == "parameters":
                continue
            success_status = next(
                code for code in ("200", "201", "202") if code in operation["responses"]
            )
            response_schema = operation["responses"][success_status]["content"][
                "application/json"
            ]["schema"]
            assert "$ref" in response_schema
            model_name = response_schema["$ref"].rsplit("/", 1)[-1]
            model = schema["components"]["schemas"][model_name]
            assert model.get("additionalProperties") is False
            assert set(model["properties"]) == {"code", "message", "data", "request_id"}


def test_settings_reject_unknown_toml_and_hide_secrets(tmp_path) -> None:
    config = tmp_path / "narrato.toml"
    config.write_text(
        'database_url = "sqlite:///ok.db"\nunknown = "bad"\n', encoding="utf-8"
    )
    with pytest.raises(ValidationError):
        load_settings(config)

    settings = _settings(tmp_path)
    rendered = repr(settings)
    assert "request-secret" not in rendered
    assert "callback-secret" not in rendered
    assert "test-hmac-secret-with-at-least-32-bytes" not in rendered
    assert "smtp-password" not in rendered
    assert str(tmp_path / "business.db") not in rendered

    with pytest.raises(ValidationError):
        Settings(core_base_url="http://127.0.0.1:8002")

    local_core = Settings(
        core_base_url="http://127.0.0.1:8002",
        allow_insecure_core_loopback=True,
    )
    assert str(local_core.core_base_url) == "http://127.0.0.1:8002/"

    with pytest.raises(ValidationError):
        Settings(
            core_base_url="http://core.example.test",
            allow_insecure_core_loopback=True,
        )

    assert Settings(oss_endpoint="oss-cn-shanghai.aliyuncs.com").oss_endpoint == (
        "oss-cn-shanghai.aliyuncs.com"
    )

    with pytest.raises(ValidationError):
        Settings(oss_endpoint="https://oss-cn-shanghai.aliyuncs.com")

    with pytest.raises(ValidationError):
        Settings(oss_url="narrato.oss-cn-shanghai.aliyuncs.com")

    with pytest.raises(ValidationError):
        Settings(
            oss_url="https://narrato.oss-cn-shanghai.aliyuncs.com",
            cdn_public_base_url="http://cdn.example.test",
        )

    settings = Settings(
        oss_url="https://narrato.oss-cn-shanghai.aliyuncs.com/",
        cdn_public_base_url="https://cdn.example.test/",
    )
    assert settings.cdn_public_base_url == "https://cdn.example.test"


def test_celery_has_independent_prefix_and_no_result_backend(tmp_path) -> None:
    settings = _settings(tmp_path)
    celery = create_celery_app(settings)
    assert celery.conf.result_backend is None
    assert celery.conf.task_default_queue == "narrato.business.test.default"
    assert (
        celery.conf.broker_transport_options["global_keyprefix"]
        == "narrato:business:test:celery:"
    )
    assert "narrato.deletion.sweep" in celery.tasks
    assert celery.conf.beat_schedule["project-deletion-sweep"] == {
        "task": "narrato.deletion.sweep",
        "schedule": settings.project_deletion_sweep_interval_seconds,
    }


def test_clean_celery_worker_registers_auth_tasks(tmp_path) -> None:
    config_path = Path(__file__).resolve().parents[2] / "config.example.toml"
    probe = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from narrato_api.celery_app import celery_app; "
                "names=set(celery_app.tasks); "
                "assert 'narrato.auth.send_verification_email' in names; "
                "assert 'narrato.deletion.sweep' in names; "
                "assert not any('cover' in name for name in names)"
            ),
        ],
        cwd=tmp_path,
        env={**os.environ, "NARRATO_API_CONFIG": str(config_path)},
        check=False,
        capture_output=True,
        text=True,
    )
    assert probe.returncode == 0, probe.stderr


def test_each_web_app_lifespan_owns_configured_synchronous_mail_client(
    tmp_path, monkeypatch
) -> None:
    import narrato_api.main as main_module

    created: list[object] = []

    class Client:
        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs
            created.append(self)

        def send_verification_code(self, *args, **kwargs) -> None:
            del args, kwargs

    monkeypatch.setattr(main_module, "SmtpMailClient", Client)
    first_settings = _settings(tmp_path).model_copy(update={"smtp_host": "smtp.one"})
    second_settings = _settings(tmp_path).model_copy(update={"smtp_host": "smtp.two"})
    with TestClient(create_app(first_settings)) as client:
        assert created[-1].kwargs["host"] == "smtp.one"
        assert client.app.state.mail_dispatcher._client is created[-1]
    with TestClient(create_app(second_settings)) as client:
        assert created[-1].kwargs["host"] == "smtp.two"
        assert client.app.state.mail_dispatcher._client is created[-1]
    assert len(created) == 2


def test_json_logging_redacts_configured_secrets() -> None:
    record = logging.LogRecord(
        "test", logging.INFO, __file__, 1, "token=request-secret", (), None
    )
    payload = json.loads(JsonFormatter(("request-secret",)).format(record))
    assert payload == {
        "timestamp": payload["timestamp"],
        "level": "INFO",
        "service": "narratoApi",
        "request_id": None,
        "message": "token=[REDACTED]",
    }


def test_json_logging_redacts_every_structured_payload_field() -> None:
    record = logging.LogRecord(
        "test", logging.INFO, __file__, 1, "safe-message", (), None
    )
    record.request_id = "req-secret"
    payload = JsonFormatter(("INFO", "narratoApi", "req-secret", "2026")).format(record)
    for secret in ("INFO", "narratoApi", "req-secret", "2026"):
        assert secret not in payload


def test_request_logging_injects_request_id_and_resets_context(tmp_path) -> None:
    app = create_app(_settings(tmp_path))
    stream = io.StringIO()
    _managed_log_handler().setStream(stream)

    @app.get("/api/v1/test-only-log")
    async def log_from_request() -> dict[str, bool]:
        """仅用于验证请求日志上下文。"""

        logging.getLogger("narrato_api.request_probe").info("request-probe")
        return {"ok": True}

    with TestClient(app) as client:
        client.get("/api/v1/test-only-log", headers={"X-Request-ID": "req_log-a"})
        client.get("/api/v1/test-only-log", headers={"X-Request-ID": "req_log-b"})
    logging.getLogger("narrato_api.request_probe").warning("after-request-probe")

    payloads = [json.loads(line) for line in stream.getvalue().splitlines()]
    probes = [item for item in payloads if item["message"].endswith("request-probe")]
    assert [(item["message"], item["request_id"]) for item in probes] == [
        ("request-probe", "req_log-a"),
        ("request-probe", "req_log-b"),
        ("after-request-probe", None),
    ]


def test_secret_request_id_is_replaced_and_never_logged(tmp_path) -> None:
    settings = _settings(tmp_path).model_copy(
        update={"core_request_token": "actual-secret-token"}
    )
    app = create_app(settings)
    stream = io.StringIO()
    _managed_log_handler().setStream(stream)

    @app.get("/api/v1/test-only-secret-request-id")
    async def log_secret_request_id() -> dict[str, bool]:
        """仅用于验证请求 ID 不可绕过密钥脱敏。"""

        logging.getLogger("narrato_api.request_probe").info("secret-id-probe")
        return {"ok": True}

    with TestClient(app) as client:
        response = client.get(
            "/api/v1/test-only-secret-request-id",
            headers={"X-Request-ID": "prefix-actual-secret-token-suffix"},
        )

    assert response.headers["X-Request-ID"].startswith("req_")
    assert response.headers["X-Request-ID"] != "prefix-actual-secret-token-suffix"
    assert "actual-secret-token" not in stream.getvalue()
    payload = next(
        json.loads(line)
        for line in stream.getvalue().splitlines()
        if "secret-id-probe" in line
    )
    assert payload["request_id"] == response.headers["X-Request-ID"]


def test_logging_configuration_unions_secrets_and_preserves_foreign_handlers(
    tmp_path,
) -> None:
    root = logging.getLogger()
    foreign_stream = io.StringIO()
    foreign = logging.StreamHandler(foreign_stream)
    root.addHandler(foreign)
    first = _settings(tmp_path).model_copy(
        update={"core_request_token": "first-request-secret"}
    )
    second = _settings(tmp_path).model_copy(
        update={"core_request_token": "second-request-secret"}
    )
    app_a = create_app(first)
    app_b = create_app(second)

    managed = [
        handler
        for handler in logging.getLogger("narrato_api").handlers
        if getattr(handler, "_narrato_managed", False)
    ]
    assert foreign in root.handlers
    assert len(managed) == 1
    stream = io.StringIO()
    managed[0].setStream(stream)

    @app_a.get("/api/v1/test-only-log-a")
    async def log_a() -> dict[str, bool]:
        """仅用于交错应用 A 的密钥日志探针。"""

        logging.getLogger("narrato_api.multi_app").info(
            "token=%s", first.core_request_token
        )
        return {"ok": True}

    @app_b.get("/api/v1/test-only-log-b")
    async def log_b() -> dict[str, bool]:
        """仅用于交错应用 B 的密钥日志探针。"""

        logging.getLogger("narrato_api.multi_app").info(
            "token=%s", second.core_request_token
        )
        return {"ok": True}

    with TestClient(app_a) as client_a:
        with TestClient(app_b) as client_b:
            with ThreadPoolExecutor(max_workers=2) as executor:
                responses = (
                    executor.submit(client_a.get, "/api/v1/test-only-log-a"),
                    executor.submit(client_b.get, "/api/v1/test-only-log-b"),
                )
                assert [future.result().status_code for future in responses] == [
                    200,
                    200,
                ]

    rendered = stream.getvalue()
    assert "first-request-secret" not in rendered
    assert "second-request-secret" not in rendered
    assert rendered.count("token=[REDACTED]") == 2
    assert foreign_stream.getvalue() == ""
    root.removeHandler(foreign)


def test_unstarted_apps_do_not_register_redaction_values(tmp_path) -> None:
    before = active_redaction_value_count()
    for index in range(25):
        settings = _settings(tmp_path).model_copy(
            update={
                "database_url": f"sqlite:///{tmp_path / f'unstarted-{index}.db'}",
                "core_request_token": f"unstarted-secret-{index}",
            }
        )
        create_app(settings)
    assert active_redaction_value_count() == before
    assert not contains_configured_secret("unstarted-secret-24")


def test_redaction_values_follow_nested_lifespan_reference_counts(tmp_path) -> None:
    before = active_redaction_value_count()
    first = _settings(tmp_path).model_copy(
        update={"core_request_token": "lifespan-secret-a"}
    )
    second = _settings(tmp_path).model_copy(
        update={"core_request_token": "lifespan-secret-b"}
    )
    app_a = create_app(first)
    app_b = create_app(second)
    assert active_redaction_value_count() == before

    with TestClient(app_a):
        assert contains_configured_secret("lifespan-secret-a")
        assert contains_configured_secret("callback-secret")
        with TestClient(app_b):
            assert contains_configured_secret("lifespan-secret-a")
            assert contains_configured_secret("lifespan-secret-b")
            assert contains_configured_secret("callback-secret")
        assert contains_configured_secret("lifespan-secret-a")
        assert not contains_configured_secret("lifespan-secret-b")
        assert contains_configured_secret("callback-secret")
    assert not contains_configured_secret("lifespan-secret-a")
    assert not contains_configured_secret("lifespan-secret-b")
    assert not contains_configured_secret("callback-secret")
    assert active_redaction_value_count() == before


def test_startup_failure_releases_logging_redactions(tmp_path, monkeypatch) -> None:
    import narrato_api.main as main_module

    settings = _settings(tmp_path).model_copy(
        update={"core_request_token": "failed-startup-secret"}
    )
    app = create_app(settings)
    monkeypatch.setattr(
        main_module,
        "acquire_database_engine",
        lambda _settings: (_ for _ in ()).throw(RuntimeError("startup failed")),
    )

    with pytest.raises(RuntimeError, match="startup failed"):
        with TestClient(app):
            pass
    assert not contains_configured_secret("failed-startup-secret")


def test_foreign_nonpropagating_logger_record_is_not_mutated(tmp_path) -> None:
    records: list[logging.LogRecord] = []

    class CaptureHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    foreign = logging.getLogger("isolated.vendor")
    handler = CaptureHandler()
    foreign.handlers = [handler]
    foreign.propagate = False
    settings = _settings(tmp_path).model_copy(
        update={"core_request_token": "foreign-contract-secret"}
    )
    app = create_app(settings)

    with TestClient(app):
        try:
            raise RuntimeError("foreign-contract-secret")
        except RuntimeError:
            foreign.error(
                "token=%s",
                settings.core_request_token,
                exc_info=True,
                stack_info=True,
            )

    assert len(records) == 1
    record = records[0]
    assert record.msg == "token=%s"
    assert record.args == ("foreign-contract-secret",)
    assert record.exc_info is not None
    assert record.stack_info is not None
    foreign.handlers = []
    foreign.propagate = True


def test_owned_namespace_replaces_foreign_handlers_without_mutating_them(
    tmp_path,
) -> None:
    namespace = logging.getLogger("narrato_api")
    foreign_stream = io.StringIO()
    foreign = logging.StreamHandler(foreign_stream)
    foreign.setLevel(logging.DEBUG)
    original_formatter = foreign.formatter
    original_filters = tuple(foreign.filters)
    namespace.addHandler(foreign)
    settings = _settings(tmp_path).model_copy(
        update={"core_request_token": "owned-namespace-secret"}
    )

    app = create_app(settings)
    managed = _managed_log_handler()
    managed_stream = io.StringIO()
    managed.setStream(managed_stream)
    assert namespace.handlers == [managed]
    assert foreign.formatter is original_formatter
    assert tuple(foreign.filters) == original_filters
    assert foreign.level == logging.DEBUG
    assert not foreign._closed

    with TestClient(app):
        logging.getLogger("narrato_api.owned_probe").warning(
            "token=%s", settings.core_request_token
        )

    assert foreign_stream.getvalue() == ""
    assert "owned-namespace-secret" not in managed_stream.getvalue()
    assert "token=[REDACTED]" in managed_stream.getvalue()
    assert not foreign._closed


def test_active_lifespans_reference_count_log_levels(tmp_path) -> None:
    namespace = logging.getLogger("narrato_api")
    namespace.setLevel(logging.DEBUG)
    info_app = create_app(
        _settings(tmp_path).model_copy(
            update={
                "database_url": f"sqlite:///{tmp_path / 'info.db'}",
                "log_level": "INFO",
            }
        )
    )
    error_app = create_app(
        _settings(tmp_path).model_copy(
            update={
                "database_url": f"sqlite:///{tmp_path / 'error.db'}",
                "log_level": "ERROR",
            }
        )
    )
    info_twin = create_app(
        _settings(tmp_path).model_copy(
            update={
                "database_url": f"sqlite:///{tmp_path / 'info-twin.db'}",
                "log_level": "INFO",
            }
        )
    )
    assert namespace.level == logging.DEBUG

    with TestClient(info_app):
        assert namespace.level == logging.INFO
        unstarted = create_app(
            _settings(tmp_path).model_copy(update={"log_level": "CRITICAL"})
        )
        assert unstarted is not None
        assert namespace.level == logging.INFO
        with TestClient(error_app):
            assert namespace.level == logging.INFO
        assert namespace.level == logging.INFO
    assert namespace.level == logging.WARNING

    with TestClient(error_app):
        assert namespace.level == logging.ERROR
        with TestClient(info_app):
            assert namespace.level == logging.INFO
        assert namespace.level == logging.ERROR
    assert namespace.level == logging.WARNING

    with TestClient(info_app):
        with TestClient(info_twin):
            assert namespace.level == logging.INFO
        assert namespace.level == logging.INFO
    assert namespace.level == logging.WARNING


def test_cleanup_failures_do_not_skip_other_releases_or_leak_secrets(
    tmp_path, monkeypatch
) -> None:
    from narrato_api.database import get_engine

    settings = _settings(tmp_path).model_copy(
        update={"core_request_token": "cleanup-failure-secret"}
    )
    app = create_app(settings)
    engine = get_engine(settings)
    stream = io.StringIO()
    _managed_log_handler().setStream(stream)

    async def fail_executor_close(*, timeout: float) -> None:
        del timeout
        raise RuntimeError("cleanup-failure-secret executor")

    def fail_engine_dispose() -> None:
        raise RuntimeError("cleanup-failure-secret engine")

    monkeypatch.setattr(app.state.readiness_executor, "aclose", fail_executor_close)
    monkeypatch.setattr(engine, "dispose", fail_engine_dispose)

    with pytest.raises(RuntimeError, match="application cleanup failed"):
        with TestClient(app):
            assert contains_configured_secret("cleanup-failure-secret")

    assert not contains_configured_secret("cleanup-failure-secret")
    assert get_engine(settings) is not engine
    assert "cleanup-failure-secret" not in stream.getvalue()
    assert stream.getvalue().count("application cleanup failed") == 2


def test_executor_cancellation_still_releases_all_lifespan_owners(
    tmp_path, monkeypatch
) -> None:
    from narrato_api.database import get_engine

    namespace = logging.getLogger("narrato_api")
    settings = _settings(tmp_path).model_copy(
        update={"core_request_token": "cancel-cleanup-secret", "log_level": "INFO"}
    )
    app = create_app(settings)
    owned_engine = get_engine(settings)
    cancellation = asyncio.CancelledError("cancel shutdown")

    async def cancel_executor_close(*, timeout: float) -> None:
        del timeout
        raise cancellation

    monkeypatch.setattr(app.state.readiness_executor, "aclose", cancel_executor_close)

    async def run_lifespan() -> None:
        async with app.router.lifespan_context(app):
            assert contains_configured_secret("cancel-cleanup-secret")
            assert namespace.level == logging.INFO

    with pytest.raises(asyncio.CancelledError) as caught:
        asyncio.run(run_lifespan())

    assert caught.value is cancellation
    assert not contains_configured_secret("cancel-cleanup-secret")
    assert namespace.level == logging.WARNING
    assert get_engine(settings) is not owned_engine


def test_logging_redacts_all_settings_secrets_urls_args_and_metadata(tmp_path) -> None:
    settings = _settings(tmp_path).model_copy(
        update={
            "database_url": "postgresql+psycopg://alice:db-secret@db/narrato",
            "redis_url": "redis://:redis-secret@redis/4",
            "celery_broker_url": "redis://broker-user:broker-secret@redis/5",
        }
    )
    configure_logging(settings)
    logging_values = acquire_logging_redactions(settings)
    assert "db-secret" not in repr(settings)
    assert "redis-secret" not in repr(settings)
    assert "broker-secret" not in repr(settings)
    try:
        formatter = _managed_log_handler().formatter
        assert formatter is not None
        try:
            raise RuntimeError(settings.database_url)
        except RuntimeError:
            record = logging.LogRecord(
                "test",
                logging.ERROR,
                __file__,
                1,
                "urls=%s %s %s token=%s",
                (
                    settings.database_url,
                    settings.redis_url,
                    settings.celery_broker_url,
                    settings.core_request_token,
                ),
                exc_info=__import__("sys").exc_info(),
            )
        record.error_type = settings.redis_url
        rendered = formatter.format(record)
        for secret in (
            "alice",
            "db-secret",
            "redis-secret",
            "broker-user",
            "broker-secret",
            "request-secret",
        ):
            assert secret not in rendered
        assert "[REDACTED]" in rendered
    finally:
        release_logging_redactions(logging_values)


def test_unknown_errors_do_not_leak_internal_details(tmp_path) -> None:
    app = create_app(_settings(tmp_path))
    stream = io.StringIO()
    _managed_log_handler().setStream(stream)

    @app.get("/api/v1/test-only-boom")
    async def boom() -> None:
        """仅用于验证未知异常的公开边界。"""

        raise RuntimeError("postgresql://admin:secret@local/private/path")

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/api/v1/test-only-boom")

    assert response.status_code == 500
    assert response.json()["code"] == "INTERNAL_ERROR"
    assert "secret" not in response.text
    assert "/private" not in response.text
    payloads = [json.loads(line) for line in stream.getvalue().splitlines()]
    failure = next(
        item for item in payloads if item["message"] == "unhandled request failure"
    )
    assert failure["request_id"] == response.json()["request_id"]
    assert failure["error_type"] == "RuntimeError"
    assert failure["error_code"] == "INTERNAL_ERROR"
    assert "secret" not in json.dumps(failure)


def test_business_service_does_not_import_core_or_legacy_services() -> None:
    package_root = Path(__file__).parents[2] / "narrato_api"
    forbidden = ("core_api", "app.services")
    for source_path in package_root.rglob("*.py"):
        tree = ast.parse(
            source_path.read_text(encoding="utf-8"), filename=str(source_path)
        )
        imports: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.append(node.module)
        assert not any(
            name == prefix or name.startswith(f"{prefix}.")
            for name in imports
            for prefix in forbidden
        )
