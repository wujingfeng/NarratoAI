from __future__ import annotations

import concurrent.futures
import os
import threading
import time
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select
from sqlalchemy.dialects import postgresql
from redis import Redis
from celery.exceptions import Retry

from narrato_api.auth.models import User
from narrato_api.auth.redis_store import RedisEmailCodeStore, RedisSessionStore
from narrato_api.auth.router import get_auth_service
from narrato_api.auth.service import (
    AuthService,
    EmailCodeManager,
    InMemoryEmailCodeStore,
    InMemorySessionStore,
    PasswordHasher,
    SingleSessionTokens,
    authentication_required,
)
from narrato_api.api.errors import ApiError
from narrato_api.config import Settings
from narrato_api.database import Base
from narrato_api.integrations.mail_client import FakeMailDispatcher
from narrato_api.integrations.mail_client import seal_verification_code
from narrato_api.celery_app import create_celery_app
from narrato_api.main import create_app


def test_postgresql_account_query_compiles_with_row_lock() -> None:
    statement = select(User).where(User.email == "user@example.com").with_for_update()
    sql = str(statement.compile(dialect=postgresql.dialect()))
    assert "FOR UPDATE" in sql


@pytest.fixture
def auth_fixture(tmp_path) -> Iterator[tuple[TestClient, AuthService, FakeMailDispatcher]]:
    database_path = tmp_path / "auth.db"
    engine = create_engine(
        f"sqlite:///{database_path}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    code_store = InMemoryEmailCodeStore()
    session_store = InMemorySessionStore()
    mail = FakeMailDispatcher()
    service = AuthService(
        session_factory=sessions,
        password_hasher=PasswordHasher(time_cost=1, memory_cost_kib=8192, parallelism=1),
        codes=EmailCodeManager(code_store, secret="test-code-hmac", ttl_seconds=600),
        tokens=SingleSessionTokens(session_store, ttl_seconds=2_592_000),
        mail_dispatcher=mail,
    )
    settings = Settings(
        database_url=f"sqlite:///{database_path}",
        redis_url="redis://127.0.0.1:6379/15",
        core_base_url="https://core.example.test",
        core_request_token="request-secret",
        core_callback_token="callback-secret",
        verification_code_hmac_secret="test-code-hmac-secret-32-bytes-minimum",
        smtp_host="smtp.example.test",
        smtp_username="smtp-user",
        smtp_password="smtp-password",
        smtp_sender="noreply@example.test",
    )
    app = create_app(settings)
    app.dependency_overrides[get_auth_service] = lambda: service
    with TestClient(app) as client:
        yield client, service, mail
    engine.dispose()


def _register(client: TestClient, mail: FakeMailDispatcher) -> dict[str, object]:
    sent = client.post(
        "/api/v1/auth/register-code/send", json={"email": " User@Example.com "}
    )
    assert sent.status_code == 202
    code = mail.messages[-1].verification_code
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "user@example.com",
            "password": "Correct-Horse-Battery-42",
            "verification_code": code,
        },
    )
    assert response.status_code == 201
    return response.json()["data"]


def test_register_login_single_session_logout_and_me(auth_fixture) -> None:
    client, _service, mail = auth_fixture
    registered = _register(client, mail)
    assert registered["email"] == "user@example.com"
    assert registered["status"] == "active"

    first = client.post(
        "/api/v1/auth/login",
        json={"email": "USER@example.com", "password": "Correct-Horse-Battery-42"},
    )
    second = client.post(
        "/api/v1/auth/login",
        json={"email": "user@example.com", "password": "Correct-Horse-Battery-42"},
    )
    assert first.status_code == second.status_code == 200
    first_token = first.json()["data"]["token"]
    second_token = second.json()["data"]["token"]
    assert client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {first_token}"}).status_code == 401
    current = client.get(
        "/api/v1/users/me", headers={"Authorization": f"Bearer {second_token}"}
    )
    assert current.status_code == 200
    assert current.json()["data"]["email"] == "user@example.com"
    assert client.post(
        "/api/v1/auth/logout", headers={"Authorization": f"Bearer {second_token}"}
    ).status_code == 200
    assert client.get(
        "/api/v1/users/me", headers={"Authorization": f"Bearer {second_token}"}
    ).status_code == 401


@pytest.mark.parametrize(
    ("path", "payload"),
    [
        ("/api/v1/auth/register-code/send", {"email": ".foo@example.com"}),
        (
            "/api/v1/auth/login",
            {"email": "foo..bar@example.com", "password": "Bounded-Password-42"},
        ),
        ("/api/v1/auth/password-code/send", {"email": "foo.@example.com"}),
    ],
)
def test_auth_http_rejects_invalid_dot_atom_emails(
    auth_fixture, path: str, payload: dict[str, str]
) -> None:
    client, _service, _mail = auth_fixture
    response = client.post(path, json=payload)
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"


def test_password_reset_is_non_enumerating_and_revokes_session(auth_fixture) -> None:
    client, _service, mail = auth_fixture
    _register(client, mail)
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "user@example.com", "password": "Correct-Horse-Battery-42"},
    )
    token = login.json()["data"]["token"]
    unknown = client.post(
        "/api/v1/auth/password-code/send", json={"email": "missing@example.com"}
    )
    known = client.post(
        "/api/v1/auth/password-code/send", json={"email": "user@example.com"}
    )
    assert unknown.status_code == known.status_code == 202
    code = mail.messages[-1].verification_code
    reset = client.post(
        "/api/v1/auth/password/reset",
        json={
            "email": "user@example.com",
            "verification_code": code,
            "new_password": "Different-Correct-Password-43",
        },
    )
    assert reset.status_code == 200
    assert client.get(
        "/api/v1/users/me", headers={"Authorization": f"Bearer {token}"}
    ).status_code == 401
    assert client.post(
        "/api/v1/auth/login",
        json={"email": "user@example.com", "password": "Correct-Horse-Battery-42"},
    ).status_code == 401
    assert client.post(
        "/api/v1/auth/login",
        json={"email": "user@example.com", "password": "Correct-Horse-Battery-42"},
    ).status_code == 401


def test_invalid_credentials_and_bearer_use_same_public_401(auth_fixture) -> None:
    client, _service, _mail = auth_fixture
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "missing@example.com", "password": "Some-Plausible-Password-42"},
    )
    bearer = client.get(
        "/api/v1/users/me", headers={"Authorization": "Bearer invalid-token"}
    )
    for response in (login, bearer):
        assert response.status_code == 401
        assert response.json()["code"] == "AUTHENTICATION_REQUIRED"
        assert response.json()["message"] == "Authentication required"


def test_auth_dtos_forbid_extra_and_openapi_has_no_refresh_route(auth_fixture) -> None:
    client, _service, _mail = auth_fixture
    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": "user@example.com",
            "password": "Some-Plausible-Password-42",
            "refresh_token": "forbidden",
        },
    )
    assert response.status_code == 422
    schema = client.get("/openapi.json").json()
    assert all("refresh" not in path for path in schema["paths"])
    assert {method for path in schema["paths"].values() for method in path} <= {
        "get",
        "post",
    }


def test_duplicate_registration_and_concurrent_registration_have_one_user(auth_fixture) -> None:
    _client, service, _mail = auth_fixture
    codes = [service.send_register_code("same@example.com") for _ in range(2)]
    code = next(item for item in reversed(codes) if item is not None)

    def register() -> str:
        try:
            return service.register(
                "same@example.com", "Correct-Horse-Battery-42", code
            ).id
        except Exception as error:
            return type(error).__name__

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: register(), range(2)))
    with service.session_factory() as session:
        assert session.query(User).filter(User.email == "same@example.com").count() == 1
    assert sum(item.startswith("usr_") for item in results) == 1


def test_disabled_user_cannot_login_and_existing_token_is_rejected(auth_fixture) -> None:
    client, service, mail = auth_fixture
    registered = _register(client, mail)
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "user@example.com", "password": "Correct-Horse-Battery-42"},
    )
    token = login.json()["data"]["token"]
    with service.session_factory() as session:
        user = session.get(User, registered["id"])
        assert user is not None
        user.status = "disabled"
        session.commit()
    assert client.get(
        "/api/v1/users/me", headers={"Authorization": f"Bearer {token}"}
    ).status_code == 401


def test_code_send_endpoints_do_not_enumerate_accounts(auth_fixture) -> None:
    client, _service, mail = auth_fixture
    _register(client, mail)
    before = len(mail.messages)
    existing = client.post(
        "/api/v1/auth/register-code/send", json={"email": "user@example.com"}
    )
    missing = client.post(
        "/api/v1/auth/register-code/send", json={"email": "missing@example.com"}
    )
    assert existing.status_code == missing.status_code == 202
    assert {
        key: existing.json()[key] for key in ("code", "message", "data")
    } == {key: missing.json()[key] for key in ("code", "message", "data")}
    assert len(mail.messages) == before + 1
    assert mail.messages[-1].email == "missing@example.com"
    assert mail.cover_dispatches >= 1

    before = len(mail.messages)
    known_reset = client.post(
        "/api/v1/auth/password-code/send", json={"email": "user@example.com"}
    )
    unknown_reset = client.post(
        "/api/v1/auth/password-code/send", json={"email": "nobody@example.com"}
    )
    assert known_reset.status_code == unknown_reset.status_code == 202
    assert len(mail.messages) == before + 1
    assert mail.messages[-1].email == "user@example.com"
    assert mail.cover_dispatches >= 2


def test_concurrent_code_sends_leave_only_latest_generation_consumable(auth_fixture) -> None:
    _client, service, mail = auth_fixture
    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as executor:
        results = list(
            executor.map(
                lambda _: service.send_register_code("race@example.com"), range(24)
            )
        )
    actual = [message for message in mail.messages if message.email == "race@example.com"]
    assert len(actual) == 24
    winners = [
        message.verification_code
        for message in actual
        if service.codes.consume(
            "race@example.com", message.verification_code, purpose="register"
        )
    ]
    assert len(winners) == 1
    assert results.count(winners[0]) == 1


def test_broker_failure_rolls_back_only_its_code_generation(auth_fixture) -> None:
    _client, service, mail = auth_fixture

    class FailingDispatcher:
        def enqueue(self, email: str, verification_code: str, **kwargs) -> None:
            del email, verification_code, kwargs
            raise RuntimeError("broker unavailable")

    service.mail_dispatcher = FailingDispatcher()  # type: ignore[assignment]
    with pytest.raises(RuntimeError, match="broker unavailable"):
        service.send_register_code("retry@example.com")
    service.mail_dispatcher = mail
    code = service.send_register_code("retry@example.com")
    assert code is not None
    assert service.codes.consume("retry@example.com", code, purpose="register")


def test_stale_session_version_is_rejected_and_deleted(auth_fixture) -> None:
    _client, service, mail = auth_fixture
    _register(_client, mail)
    result = service.login("user@example.com", "Correct-Horse-Battery-42")
    with service.session_factory() as session:
        user = session.get(User, result.user.id)
        assert user is not None
        user.password_version += 1
        session.commit()
    with pytest.raises(ApiError) as caught:
        service.resolve_user(result.token)
    assert caught.value.code == authentication_required().code
    assert service.tokens.resolve(result.token) is None


def test_revoke_failure_does_not_commit_new_password(auth_fixture) -> None:
    _client, service, mail = auth_fixture
    _register(_client, mail)
    service.send_password_reset_code("user@example.com")
    code = mail.messages[-1].verification_code
    store = service.tokens.store
    original = store.revoke_user

    def fail(_user_id: str) -> None:
        raise ApiError("AUTH_SERVICE_UNAVAILABLE", "Authentication service unavailable", 503)

    store.revoke_user = fail  # type: ignore[method-assign]
    with pytest.raises(ApiError):
        service.reset_password(
            "user@example.com", code, "Different-Correct-Password-43"
        )
    store.revoke_user = original  # type: ignore[method-assign]
    assert service.login("user@example.com", "Correct-Horse-Battery-42").token
    with pytest.raises(ApiError):
        service.login("user@example.com", "Different-Correct-Password-43")


def test_old_password_login_started_before_reset_is_fenced(auth_fixture) -> None:
    _client, service, mail = auth_fixture
    _register(_client, mail)
    service.send_password_reset_code("user@example.com")
    reset_code = mail.messages[-1].verification_code
    delegate = service.password_hasher
    verified = threading.Event()
    release = threading.Event()

    class BlockingHasher:
        def hash(self, password: str) -> str:
            return delegate.hash(password)

        def verify(self, stored_hash: str | None, password: str) -> bool:
            result = delegate.verify(stored_hash, password)
            if password == "Correct-Horse-Battery-42":
                verified.set()
                assert release.wait(2)
            return result

    service.password_hasher = BlockingHasher()  # type: ignore[assignment]
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        login_future = executor.submit(
            service.login, "user@example.com", "Correct-Horse-Battery-42"
        )
        assert verified.wait(2)
        reset_future = executor.submit(
            service.reset_password,
            "user@example.com",
            reset_code,
            "Different-Correct-Password-43",
        )
        time.sleep(0.05)
        release.set()
        old_login = login_future.result(timeout=2)
        reset_future.result(timeout=2)
    with pytest.raises(ApiError):
        service.resolve_user(old_login.token)
    service.password_hasher = delegate
    assert service.login("user@example.com", "Different-Correct-Password-43").token


def test_reset_started_before_old_login_holds_fence_until_commit(auth_fixture) -> None:
    _client, service, mail = auth_fixture
    _register(_client, mail)
    service.send_password_reset_code("user@example.com")
    reset_code = mail.messages[-1].verification_code
    delegate = service.password_hasher
    hashing = threading.Event()
    release = threading.Event()

    class BlockingHasher:
        def hash(self, password: str) -> str:
            if password == "Different-Correct-Password-43":
                hashing.set()
                assert release.wait(2)
            return delegate.hash(password)

        def verify(self, stored_hash: str | None, password: str) -> bool:
            return delegate.verify(stored_hash, password)

    service.password_hasher = BlockingHasher()  # type: ignore[assignment]
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        reset_future = executor.submit(
            service.reset_password,
            "user@example.com",
            reset_code,
            "Different-Correct-Password-43",
        )
        assert hashing.wait(2)
        login_future = executor.submit(
            service.login, "user@example.com", "Correct-Horse-Battery-42"
        )
        time.sleep(0.05)
        assert not login_future.done()
        release.set()
        reset_future.result(timeout=2)
        with pytest.raises(ApiError):
            login_future.result(timeout=2)
    service.password_hasher = delegate
    assert service.login("user@example.com", "Different-Correct-Password-43").token


def _real_redis() -> Redis:
    """返回显式测试 Redis；普通 CI 未提供时跳过。"""

    url = os.getenv("NARRATO_AUTH_TEST_REDIS_URL")
    if not url:
        pytest.skip("NARRATO_AUTH_TEST_REDIS_URL is not configured")
    client = Redis.from_url(url)
    client.ping()
    return client


def test_ready_is_503_when_auth_redis_is_live_but_celery_broker_is_closed(
    tmp_path,
) -> None:
    redis_url = os.getenv("NARRATO_AUTH_TEST_REDIS_URL")
    if not redis_url:
        pytest.skip("NARRATO_AUTH_TEST_REDIS_URL is not configured")
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'ready.db'}",
        redis_url=redis_url,
        celery_broker_url="redis://127.0.0.1:1/15",
        core_request_token="request-secret",
        core_callback_token="callback-secret",
        verification_code_hmac_secret="test-code-hmac-secret-32-bytes-minimum",
        smtp_host="smtp.example.test",
        smtp_username="smtp-user",
        smtp_password="smtp-password",
        smtp_sender="noreply@example.test",
        readiness_timeout_seconds=1,
        auth_redis_timeout_seconds=1,
    )
    app = create_app(settings)
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/api/v1/health/ready")
    assert response.status_code == 503


def test_real_redis_code_lua_is_atomic_and_keeps_only_digests() -> None:
    client = _real_redis()
    prefix = f"narrato:test:{os.getpid()}:code:"
    store = RedisEmailCodeStore(client, prefix=prefix)
    manager = EmailCodeManager(store, secret="real-redis-hmac", ttl_seconds=600)
    try:
        issue = manager.issue("redis-user@example.com", purpose="register")
        assert issue.code is not None
        keys = list(client.scan_iter(f"{store.prefix}*"))
        assert len(keys) == 1
        assert issue.code.encode() not in keys[0]
        assert b"redis-user@example.com" not in keys[0]
        assert issue.code.encode() not in (client.get(keys[0]) or b"")
        assert 590 <= client.ttl(keys[0]) <= 600
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            results = list(
                executor.map(
                    lambda _: manager.consume(
                        "redis-user@example.com", issue.code, purpose="register"
                    ),
                    range(16),
                )
            )
        assert results.count(True) == 1
    finally:
        for key in client.scan_iter(f"{store.prefix}*"):
            client.delete(key)
        client.close()


def test_real_redis_resend_rotates_ttl_and_worker_claim_fences_stale_generation() -> None:
    client = _real_redis()
    prefix = f"narrato:test:{os.getpid()}:fsm:"
    store = RedisEmailCodeStore(client, prefix=prefix)
    manager = EmailCodeManager(store, secret="real-redis-hmac", ttl_seconds=600)
    try:
        first = manager.issue("fsm@example.com", purpose="register")
        client.expire(store.key("register", first.email_hash), 10)
        second = manager.issue("fsm@example.com", purpose="register")
        assert second.created and second.code != first.code
        assert 590 <= client.ttl(store.key("register", first.email_hash)) <= 600
        assert not store.claim(
            "register",
            first.email_hash,
            first.generation,
            first.digest,
            claim_id="stale",
            lease_seconds=30,
        ).claimed
        assert store.claim(
            "register",
            second.email_hash,
            second.generation,
            second.digest,
            claim_id="owner-1",
            lease_seconds=30,
        ).claimed
        blocked = manager.issue("fsm@example.com", purpose="register")
        assert blocked.created is False
        assert store.release(
            "register", second.email_hash, second.generation, second.digest, "owner-1"
        )
        third = manager.issue("fsm@example.com", purpose="register")
        assert third.created is True
        assert not store.mark_sent(
            "register", second.email_hash, second.generation, second.digest, "owner-1"
        )
    finally:
        for key in client.scan_iter(f"{store.prefix}*"):
            client.delete(key)
        client.close()


def test_real_redis_lease_ignores_web_and_worker_clock_skew(monkeypatch) -> None:
    client = _real_redis()
    prefix = f"narrato:test:{os.getpid()}:clock:"
    store = RedisEmailCodeStore(client, prefix=prefix)
    manager = EmailCodeManager(store, secret="clock-hmac", ttl_seconds=600)
    try:
        issue = manager.issue("clock@example.com", purpose="register")
        assert store.claim(
            "register",
            issue.email_hash,
            issue.generation,
            issue.digest,
            claim_id="clock-owner",
            lease_seconds=30,
        ).claimed
        monkeypatch.setattr(time, "time", lambda: 10**12)
        assert manager.issue("clock@example.com", purpose="register").created is False
        duplicate = store.claim(
            "register",
            issue.email_hash,
            issue.generation,
            issue.digest,
            claim_id="fast-clock-owner",
            lease_seconds=30,
        )
        assert duplicate.busy and not duplicate.claimed
        assert store.renew(
            "register",
            issue.email_hash,
            issue.generation,
            issue.digest,
            "clock-owner",
            30,
        )
    finally:
        for key in client.scan_iter(f"{store.prefix}*"):
            client.delete(key)
        client.close()


def test_worker_skips_stale_generation_and_sends_only_current(
    tmp_path, monkeypatch
) -> None:
    redis_url = os.getenv("NARRATO_AUTH_TEST_REDIS_URL")
    if not redis_url:
        pytest.skip("NARRATO_AUTH_TEST_REDIS_URL is not configured")
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'worker.db'}",
        redis_url=redis_url,
        redis_key_prefix=f"narrato:test:{os.getpid()}:worker:",
        verification_code_hmac_secret="worker-hmac-secret-with-32-characters",
        verification_code_ttl_seconds=600,
        smtp_host="smtp.example.test",
        smtp_username="smtp-user",
        smtp_password="smtp-password",
        smtp_sender="noreply@example.test",
    )
    client = Redis.from_url(redis_url)
    store = RedisEmailCodeStore(client, prefix=settings.redis_key_prefix)
    manager = EmailCodeManager(
        store, secret=settings.verification_code_hmac_secret, ttl_seconds=600
    )
    first = manager.issue("worker@example.com", purpose="register")
    second = manager.issue("worker@example.com", purpose="register")
    sent: list[tuple[str, str, int]] = []

    import narrato_api.auth.tasks as task_module

    def fake_sender(**kwargs) -> None:
        sent.append((kwargs["email"], kwargs["verification_code"], 10))

    monkeypatch.setattr(task_module, "_run_smtp_subprocess", fake_sender)
    app = create_celery_app(settings)
    task = app.tasks["narrato.auth.send_verification_email"]
    try:
        for issue in (first, second):
            task.run(
                email="worker@example.com",
                sealed_code=seal_verification_code(
                    issue.code,
                    email="worker@example.com",
                    purpose="register",
                    secret=settings.verification_code_hmac_secret,
                    deliver=True,
                ),
                purpose="register",
                generation=issue.generation,
            )
        assert sent == [("worker@example.com", second.code, 10)]
    finally:
        for key in client.scan_iter(f"{store.prefix}*"):
            client.delete(key)
        client.close()
        app.close()


def test_worker_loss_lease_allows_redelivery_without_active_duplicate_send(
    tmp_path, monkeypatch
) -> None:
    redis_url = os.getenv("NARRATO_AUTH_TEST_REDIS_URL")
    if not redis_url:
        pytest.skip("NARRATO_AUTH_TEST_REDIS_URL is not configured")
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'lease-worker.db'}",
        redis_url=redis_url,
        redis_key_prefix=f"narrato:test:{os.getpid()}:lease-worker:",
        verification_code_hmac_secret="lease-worker-hmac-secret-32-characters",
        verification_code_ttl_seconds=600,
        verification_code_send_lease_seconds=30,
        smtp_host="smtp.example.test",
        smtp_username="smtp-user",
        smtp_password="smtp-password",
        smtp_sender="noreply@example.test",
    )
    client = Redis.from_url(redis_url)
    store = RedisEmailCodeStore(client, prefix=settings.redis_key_prefix)
    manager = EmailCodeManager(
        store, secret=settings.verification_code_hmac_secret, ttl_seconds=600
    )
    sent: list[str] = []

    import narrato_api.auth.tasks as task_module

    def fake_sender(**kwargs) -> None:
        sent.append(kwargs["verification_code"])

    monkeypatch.setattr(task_module, "_run_smtp_subprocess", fake_sender)
    app = create_celery_app(settings)
    task = app.tasks["narrato.auth.send_verification_email"]
    try:
        issue = manager.issue("lease@example.com", purpose="register")
        dead_claim = store.claim(
            "register",
            issue.email_hash,
            issue.generation,
            issue.digest,
            claim_id="dead-worker",
            lease_seconds=30,
        )
        assert dead_claim.claimed
        client.eval(
            "local v=cjson.decode(redis.call('GET',KEYS[1])); "
            "v['lease_until_ms']=0; redis.call('SET',KEYS[1],cjson.encode(v),'KEEPTTL')",
            1,
            store.key("register", issue.email_hash),
        )
        task.run(
            email="lease@example.com",
            sealed_code=seal_verification_code(
                issue.code,
                email="lease@example.com",
                purpose="register",
                secret=settings.verification_code_hmac_secret,
            ),
            purpose="register",
            generation=issue.generation,
        )
        assert sent == [issue.code]

        active = manager.issue("lease@example.com", purpose="register")
        assert store.claim(
            "register",
            active.email_hash,
            active.generation,
            active.digest,
            claim_id="active-worker",
            lease_seconds=30,
        ).claimed
        with pytest.raises(Retry):
            task.run(
                email="lease@example.com",
                sealed_code=seal_verification_code(
                    active.code,
                    email="lease@example.com",
                    purpose="register",
                    secret=settings.verification_code_hmac_secret,
                ),
                purpose="register",
                generation=active.generation,
            )
        assert sent == [issue.code]
        assert not store.release(
            "register",
            active.email_hash,
            active.generation,
            active.digest,
            "wrong-owner",
        )
    finally:
        for key in client.scan_iter(f"{store.prefix}*"):
            client.delete(key)
        client.close()
        app.close()


def test_real_redis_session_lua_replaces_without_sliding_ttl() -> None:
    client = _real_redis()
    prefix = f"narrato:test:{os.getpid()}:session:"
    store = RedisSessionStore(client, prefix=prefix)
    tokens = SingleSessionTokens(store, ttl_seconds=2_592_000)
    try:
        old = tokens.issue("usr_real", password_version=1)
        new = tokens.issue("usr_real", password_version=2)
        assert tokens.resolve(old) is None
        identity = tokens.resolve(new)
        assert identity is not None and identity.password_version == 2
        ttl_before = client.ttl(tokens.session_key(new))
        assert 2_591_990 <= ttl_before <= 2_592_000
        assert tokens.resolve(new) is not None
        assert client.ttl(tokens.session_key(new)) <= ttl_before
        tokens.revoke(old)
        assert tokens.resolve(new) is not None
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            issued = list(
                executor.map(
                    lambda version: tokens.issue(
                        "usr_real", password_version=version
                    ),
                    range(3, 23),
                )
            )
        assert sum(tokens.resolve(token) is not None for token in issued) == 1
        keys = list(client.scan_iter(f"{store.prefix}*"))
        assert all(new.encode() not in key for key in keys)
        assert all(new.encode() not in (client.get(key) or b"") for key in keys)
    finally:
        for key in client.scan_iter(f"{store.prefix}*"):
            client.delete(key)
        client.close()
