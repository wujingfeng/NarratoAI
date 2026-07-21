from __future__ import annotations

import logging
import re
import subprocess
import sys

import pytest
from fastapi import APIRouter, Depends
from fastapi.testclient import TestClient

from core_api.api.dependencies import require_service_token
from core_api.logging import JsonFormatter


def _add_protected_route(app) -> None:
    router = APIRouter()

    @router.get("/protected", dependencies=[Depends(require_service_token)])
    async def protected() -> dict[str, bool]:
        return {"ok": True}

    app.include_router(router, prefix="/api/v1/test")


def test_openapi_contains_only_get_and_post(client):
    paths = client.get("/openapi.json").json()["paths"].values()
    methods = {method for path in paths for method in path}

    assert methods <= {"get", "post"}


def test_generated_request_id_matches_header_and_body(client):
    response = client.get("/api/v1/health/live")

    request_id = response.headers["X-Request-ID"]
    assert request_id == response.json()["request_id"]
    assert re.fullmatch(r"req_[A-Za-z0-9_-]+", request_id)


def test_valid_request_id_is_forwarded(client):
    response = client.get(
        "/api/v1/health/live", headers={"X-Request-ID": "req_caller-123"}
    )

    assert response.headers["X-Request-ID"] == "req_caller-123"
    assert response.json()["request_id"] == "req_caller-123"


def test_unknown_route_uses_error_envelope(client):
    response = client.get("/api/v1/not-found")

    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"
    assert set(response.json()) == {"code", "message", "data", "request_id"}
    assert response.headers["X-Request-ID"] == response.json()["request_id"]


def test_service_bearer_dependency_rejects_invalid_token(app, client):
    _add_protected_route(app)

    response = client.get(
        "/api/v1/test/protected", headers={"Authorization": "Bearer wrong"}
    )

    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHORIZED"
    assert response.headers["X-Request-ID"] == response.json()["request_id"]


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Authorization": "Basic dXNlcjpwYXNz"},
        {"Authorization": "Bearer"},
    ],
)
def test_service_bearer_dependency_rejects_missing_or_malformed_token(
    app, client, headers
):
    _add_protected_route(app)

    response = client.get("/api/v1/test/protected", headers=headers)

    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHORIZED"


def test_service_bearer_dependency_accepts_configured_token(app, client):
    _add_protected_route(app)

    response = client.get(
        "/api/v1/test/protected",
        headers={"Authorization": "Bearer test-service-token"},
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True}


@pytest.mark.parametrize("request_id", ["has space", "x" * 129, "<script>"])
def test_invalid_request_id_is_replaced(client, request_id):
    response = client.get("/api/v1/health/live", headers={"X-Request-ID": request_id})

    generated = response.headers["X-Request-ID"]
    assert generated != request_id
    assert generated == response.json()["request_id"]
    assert generated.startswith("req_")


def test_method_not_allowed_uses_error_envelope(client):
    response = client.post("/api/v1/health/live")

    assert response.status_code == 405
    assert response.json()["code"] == "HTTP_ERROR"
    assert response.headers["X-Request-ID"] == response.json()["request_id"]


def test_validation_error_uses_safe_envelope(app, client):
    router = APIRouter()

    @router.get("/validate")
    async def validate(limit: int) -> dict[str, int]:
        return {"limit": limit}

    app.include_router(router, prefix="/api/v1/test")

    response = client.get("/api/v1/test/validate", params={"limit": "wrong"})

    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"
    assert "wrong" not in response.text


def test_unexpected_error_uses_safe_envelope(app):
    router = APIRouter()

    @router.get("/explode")
    async def explode() -> None:
        raise RuntimeError("/internal/path token=server-secret")

    app.include_router(router, prefix="/api/v1/test")

    with TestClient(app, raise_server_exceptions=False) as test_client:
        response = test_client.get("/api/v1/test/explode")

    assert response.status_code == 500
    assert response.json()["code"] == "INTERNAL_ERROR"
    assert "/internal/path" not in response.text
    assert "server-secret" not in response.text


def test_json_logs_redact_configured_secrets_and_bearer_tokens():
    formatter = JsonFormatter(secrets=("configured-secret",))
    record = logging.LogRecord(
        name="core_api.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="configured-secret Authorization: Bearer request-token",
        args=(),
        exc_info=None,
    )

    rendered = formatter.format(record)

    assert "configured-secret" not in rendered
    assert "request-token" not in rendered
    assert rendered.count("***") >= 2


def test_json_logs_redact_uri_userinfo_and_named_secrets():
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="core_api.test",
        level=logging.ERROR,
        pathname=__file__,
        lineno=1,
        msg=(
            "postgresql+psycopg://core:db-super-secret@db/core "
            "redis://:redis-super-secret@redis:6379/2 "
            "password=db-super-secret token=other-token secret=vendor-secret"
        ),
        args=(),
        exc_info=None,
    )

    rendered = formatter.format(record)

    for secret in (
        "core:db-super-secret",
        "redis-super-secret",
        "db-super-secret",
        "other-token",
        "vendor-secret",
    ):
        assert secret not in rendered


def test_json_logs_redact_nested_extra_values():
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="core_api.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="probe failed",
        args=(),
        exc_info=None,
    )
    record.context = {
        "database_url": "postgresql://user:nested-password@db/core",
        "nested": {"api_token": "nested-token", "attempt": 2},
    }

    rendered = formatter.format(record)

    assert "nested-password" not in rendered
    assert "nested-token" not in rendered
    assert '"attempt": 2' in rendered


@pytest.mark.parametrize(
    "key",
    [
        "api_key",
        "api-key",
        "APIKey",
        "access_key_id",
        "ACCESS-KEY-ID",
        "secret_access_key",
        "credential",
        "Credentials",
        "passwd",
        "pwd",
    ],
)
def test_json_logs_redact_sensitive_key_aliases_in_nested_extra(key):
    formatter = JsonFormatter()
    secret = f"value-for-{key}"
    record = logging.LogRecord(
        name="core_api.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="probe failed",
        args=(),
        exc_info=None,
    )
    record.context = {
        "layers": [{key: secret}],
        "request_id": "req_visible",
        "project_id": "prj_visible",
    }

    rendered = formatter.format(record)

    assert secret not in rendered
    assert "req_visible" in rendered
    assert "prj_visible" in rendered


@pytest.mark.parametrize(
    "key",
    [
        "api_key",
        "api-key",
        "access_key_id",
        "secret_access_key",
        "credential",
        "passwd",
        "pwd",
    ],
)
def test_json_logs_redact_sensitive_key_aliases_in_message(key):
    formatter = JsonFormatter()
    secret = f"message-value-for-{key}"
    record = logging.LogRecord(
        name="core_api.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=f"{key}={secret} request_id=req_visible project_id=prj_visible",
        args=(),
        exc_info=None,
    )

    rendered = formatter.format(record)

    assert secret not in rendered
    assert "req_visible" in rendered
    assert "prj_visible" in rendered


def test_importing_package_does_not_initialize_fastapi_app():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import core_api; assert 'core_api.main' not in sys.modules",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
