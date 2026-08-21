from __future__ import annotations

import concurrent.futures
import subprocess

import pytest

from narrato_api.auth.service import (
    EmailCodeManager,
    InMemoryEmailCodeStore,
    normalize_email,
)
from narrato_api.integrations.mail_client import (
    CeleryMailDispatcher,
    SynchronousMailDispatcher,
    seal_verification_code,
    unseal_verification_code,
)
from narrato_api.config import Settings
from narrato_api.api.errors import ApiError
from narrato_api.integrations import mail_client


def test_codes_are_hashed_scoped_replaced_and_consumed_once() -> None:
    store = InMemoryEmailCodeStore()
    manager = EmailCodeManager(store, secret="unit-test-hmac", ttl_seconds=600)

    first = manager.issue(" User@Example.COM ", purpose="register")
    assert first.created is True
    assert first.code is not None and first.code.isdigit() and len(first.code) == 6
    assert first.code not in repr(store.snapshot())
    assert "user@example.com" not in repr(store.snapshot())
    assert (
        manager.consume("user@example.com", first.code, purpose="password_reset")
        is False
    )

    second = manager.issue("user@example.com", purpose="register")
    assert second.created is True and second.code != first.code
    assert manager.consume("user@example.com", first.code, purpose="register") is False
    assert manager.consume("user@example.com", second.code, purpose="register") is True
    assert manager.consume("user@example.com", first.code, purpose="register") is False


def test_code_ttl_is_fixed_and_resend_resets_it() -> None:
    store = InMemoryEmailCodeStore()
    manager = EmailCodeManager(store, secret="unit-test-hmac", ttl_seconds=600)
    first = manager.issue("user@example.com", purpose="register")
    assert 599 <= store.ttl_for("register", "user@example.com") <= 600
    store.advance(590)
    second = manager.issue("user@example.com", purpose="register")
    assert second.created is True
    assert 599 <= store.ttl_for("register", "user@example.com") <= 600
    assert first.code is not None


def test_concurrent_code_consumption_has_one_winner() -> None:
    store = InMemoryEmailCodeStore()
    manager = EmailCodeManager(store, secret="unit-test-hmac", ttl_seconds=600)
    issue = manager.issue("user@example.com", purpose="register")
    assert issue.code is not None
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        results = list(
            executor.map(
                lambda _: manager.consume(
                    "user@example.com", issue.code, purpose="register"
                ),
                range(16),
            )
        )
    assert results.count(True) == 1


@pytest.mark.parametrize(
    "email",
    [
        ".foo@example.com",
        "foo.@example.com",
        "foo..bar@example.com",
        "foo@ｅxample.com",
    ],
)
def test_email_parser_rejects_ambiguous_dot_and_idna_forms(email: str) -> None:
    with pytest.raises(ValueError, match="invalid email"):
        normalize_email(email)


def test_broker_payload_seals_code_and_binds_email_and_purpose() -> None:
    sealed = seal_verification_code(
        "123456",
        email="user@example.com",
        purpose="register",
        secret="mail-sealing-secret",
    )
    assert "123456" not in sealed
    assert unseal_verification_code(
        sealed,
        email="user@example.com",
        purpose="register",
        secret="mail-sealing-secret",
    ) == ("123456", True)
    with pytest.raises(ValueError):
        unseal_verification_code(
            sealed,
            email="other@example.com",
            purpose="register",
            secret="mail-sealing-secret",
        )


def test_celery_dispatcher_never_puts_plain_code_in_broker_kwargs() -> None:
    captured: dict[str, object] = {}

    class Producer:
        def send_task(self, name, *, kwargs, expires):
            captured.update({"name": name, "kwargs": kwargs, "expires": expires})

        def close(self):
            pass

    CeleryMailDispatcher(
        celery=Producer(),
        sealing_secret="mail-sealing-secret",  # type: ignore[arg-type]
    ).enqueue(
        "user@example.com",
        "654321",
        purpose="password_reset",
        generation="gen-1",
        deliver=False,
        ttl_seconds=600,
    )
    assert "verification_code" not in captured
    assert "654321" not in repr(captured)
    kwargs = captured["kwargs"]
    assert isinstance(kwargs, dict)
    assert unseal_verification_code(
        str(kwargs["sealed_code"]),
        email="user@example.com",
        purpose="password_reset",
        secret="mail-sealing-secret",
    ) == ("654321", False)
    assert captured["name"] == "narrato.auth.send_verification_email"
    assert captured["expires"] == 600


def test_synchronous_dispatcher_sends_before_returning() -> None:
    """Web 请求必须在 SMTP 客户端完成发送后才返回。"""

    calls: list[dict[str, object]] = []

    class Client:
        def send_verification_code(
            self, email, verification_code, *, purpose, validity_minutes
        ):
            calls.append(
                {
                    "email": email,
                    "verification_code": verification_code,
                    "purpose": purpose,
                    "validity_minutes": validity_minutes,
                }
            )

    dispatcher = SynchronousMailDispatcher(client=Client(), ttl_seconds=600)
    dispatcher.enqueue(
        "user@example.com",
        "654321",
        purpose="register",
        generation="gen-1",
        deliver=True,
        ttl_seconds=600,
    )

    assert calls == [
        {
            "email": "user@example.com",
            "verification_code": "654321",
            "purpose": "register",
            "validity_minutes": 10,
        }
    ]


def test_smtp_ssl_uses_implicit_tls_without_starttls(monkeypatch) -> None:
    """465 隐式 TLS 必须使用 SMTP_SSL，不能再协商 STARTTLS。"""

    calls: list[str] = []
    subjects: list[str] = []

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def ehlo(self):
            calls.append("ehlo")

        def starttls(self):
            calls.append("starttls")

        def login(self, username, password):
            del username, password
            calls.append("login")

        def send_message(self, message):
            subjects.append(str(message["Subject"]))
            calls.append("send")

    def smtp_ssl(host, port, *, timeout):
        assert (host, port, timeout) == ("smtp.163.com", 465, 10.0)
        calls.append("ssl")
        return Connection()

    monkeypatch.setattr(mail_client.smtplib, "SMTP_SSL", smtp_ssl)
    client = mail_client.SmtpMailClient(
        host="smtp.163.com",
        port=465,
        username="user",
        password="authorization-code",
        sender="user@163.com",
        timeout_seconds=10.0,
        use_starttls=False,
        use_ssl=True,
    )

    client.send_verification_code(
        "recipient@example.com", "123456", purpose="register", validity_minutes=10
    )

    assert calls == ["ssl", "ehlo", "login", "send"]
    assert subjects == ["影创工坊 注册验证码"]


def test_smtp_tls_modes_are_mutually_exclusive() -> None:
    """配置不得同时启用隐式 TLS 与 STARTTLS。"""

    with pytest.raises(ValueError, match="smtp_use_ssl and smtp_use_starttls"):
        Settings(smtp_use_ssl=True, smtp_use_starttls=True)


def test_smtp_subprocess_heartbeats_and_keeps_secrets_out_of_argv(monkeypatch) -> None:
    import narrato_api.auth.tasks as task_module

    captured: dict[str, object] = {}

    class Process:
        pid = 123
        returncode: int | None = None
        calls = 0

        def communicate(self, *, input, timeout):
            captured.setdefault("stdin", input)
            self.calls += 1
            if self.calls == 1:
                raise subprocess.TimeoutExpired("smtp", timeout)
            self.returncode = 0

        def poll(self):
            return self.returncode

    process = Process()

    def popen(argv, **kwargs):
        captured["argv"] = argv
        captured["popen"] = kwargs
        return process

    class Store:
        renewals = 0

        def renew(self, *args, **kwargs):
            del args, kwargs
            self.renewals += 1
            return True

    store = Store()
    monkeypatch.setattr(task_module.subprocess, "Popen", popen)
    settings = Settings(
        smtp_host="smtp.example.test",
        smtp_username="smtp-user",
        smtp_password="smtp-secret-password",
        smtp_sender="noreply@example.test",
    )
    task_module._run_smtp_subprocess(
        settings=settings,
        store=store,  # type: ignore[arg-type]
        purpose="register",
        email_hash="hash",
        generation="generation",
        digest="digest",
        claim_id="claim",
        email="user@example.com",
        verification_code="123456",
    )
    assert store.renewals == 1
    assert "smtp-secret-password" not in repr(captured["argv"])
    assert "123456" not in repr(captured["argv"])
    assert captured["argv"][-2:] == ["-m", "narrato_api.auth.smtp_sender"]
    options = captured["popen"]
    assert isinstance(options, dict)
    assert options["shell"] is False and options["start_new_session"] is True
    assert options["stdout"] == subprocess.DEVNULL
    assert options["stderr"] == subprocess.DEVNULL
    assert b"smtp-secret-password" in captured["stdin"]  # type: ignore[operator]


def test_smtp_subprocess_stops_when_lease_renewal_loses_owner(monkeypatch) -> None:
    import narrato_api.auth.tasks as task_module

    terminated: list[object] = []

    class Process:
        pid = 123
        returncode: int | None = None

        def communicate(self, *, input, timeout):
            del input
            raise subprocess.TimeoutExpired("smtp", timeout)

        def poll(self):
            return self.returncode

    process = Process()
    monkeypatch.setattr(task_module.subprocess, "Popen", lambda *a, **k: process)
    monkeypatch.setattr(
        task_module,
        "_terminate_process_group",
        lambda child: terminated.append(child),
    )

    class Store:
        def renew(self, *args, **kwargs):
            del args, kwargs
            return False

    with pytest.raises(ApiError):
        task_module._run_smtp_subprocess(
            settings=Settings(
                smtp_host="smtp.example.test",
                smtp_username="u",
                smtp_password="p",
                smtp_sender="noreply@example.test",
            ),
            store=Store(),  # type: ignore[arg-type]
            purpose="register",
            email_hash="hash",
            generation="generation",
            digest="digest",
            claim_id="claim",
            email="user@example.com",
            verification_code="123456",
        )
    assert terminated == [process]
