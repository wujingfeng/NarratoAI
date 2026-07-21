from __future__ import annotations

import math
import json
import os
import secrets
import signal
import subprocess
import sys
import time
from typing import Any

from celery import Celery
from redis import Redis

from narrato_api.auth.redis_store import RedisEmailCodeStore
from narrato_api.auth.service import EmailCodeManager
from narrato_api.api.errors import ApiError
from narrato_api.config import Settings
from narrato_api.integrations.mail_client import (
    MailPurpose,
    unseal_verification_code,
)


def _terminate_process_group(process: subprocess.Popen[bytes]) -> None:
    """终止 SMTP 子进程组，不把 stdin/stdout/stderr 写入日志。"""

    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=1)
    except (ProcessLookupError, subprocess.TimeoutExpired):
        if process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait(timeout=1)


def _run_smtp_subprocess(
    *,
    settings: Settings,
    store: RedisEmailCodeStore,
    purpose: MailPurpose,
    email_hash: str,
    generation: str,
    digest: str,
    claim_id: str,
    email: str,
    verification_code: str,
) -> None:
    """在总 deadline 内运行 SMTP，并以 Redis TIME lease heartbeat 保持 owner。"""

    payload = json.dumps(
        {
            "host": settings.smtp_host,
            "port": settings.smtp_port,
            "username": settings.smtp_username,
            "password": settings.smtp_password,
            "sender": settings.smtp_sender,
            "socket_timeout_seconds": settings.smtp_timeout_seconds,
            "use_starttls": settings.smtp_use_starttls,
            "use_ssl": settings.smtp_use_ssl,
            "email": email,
            "verification_code": verification_code,
            "purpose": purpose,
            "validity_minutes": math.ceil(settings.verification_code_ttl_seconds / 60),
        },
        separators=(",", ":"),
    ).encode()
    process = subprocess.Popen(
        [sys.executable, "-m", "narrato_api.auth.smtp_sender"],
        shell=False,
        start_new_session=True,
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    started = time.monotonic()
    heartbeat = max(1.0, settings.verification_code_send_lease_seconds / 3)
    first_input: bytes | None = payload
    try:
        while True:
            remaining = settings.smtp_total_deadline_seconds - (
                time.monotonic() - started
            )
            if remaining <= 0:
                raise TimeoutError("SMTP delivery deadline exceeded")
            try:
                process.communicate(
                    input=first_input, timeout=min(heartbeat, remaining)
                )
                first_input = None
                break
            except subprocess.TimeoutExpired:
                first_input = None
                if not store.renew(
                    purpose,
                    email_hash,
                    generation,
                    digest,
                    claim_id,
                    settings.verification_code_send_lease_seconds,
                ):
                    raise ApiError(
                        "AUTH_SERVICE_UNAVAILABLE",
                        "Authentication service unavailable",
                        503,
                    )
        if process.returncode != 0:
            raise OSError("SMTP sender failed")
    except BaseException:
        _terminate_process_group(process)
        raise


def register_auth_tasks(app: Celery, settings: Settings) -> None:
    """在显式 Celery app 上注册 Worker 任务，不使用 default/shared app。"""

    @app.task(  # type: ignore[untyped-decorator]
        name="narrato.auth.send_verification_email",
        bind=True,
        autoretry_for=(OSError, TimeoutError, ApiError),
        retry_backoff=True,
        retry_jitter=True,
        max_retries=3,
        soft_time_limit=settings.smtp_total_deadline_seconds + 2,
        time_limit=settings.smtp_total_deadline_seconds + 4,
    )
    def send_verification_email(
        self: Any,
        *,
        email: str,
        sealed_code: str,
        purpose: MailPurpose,
        generation: str,
    ) -> None:
        """只 claim 当前未过期 generation；失败释放给同一 Celery task 重试。"""

        verification_code, deliver = unseal_verification_code(
            sealed_code,
            email=email,
            purpose=purpose,
            secret=settings.verification_code_hmac_secret,
        )
        client = Redis.from_url(
            settings.redis_url,
            socket_connect_timeout=settings.auth_redis_timeout_seconds,
            socket_timeout=settings.auth_redis_timeout_seconds,
            retry_on_timeout=False,
        )
        store = RedisEmailCodeStore(client, prefix=settings.redis_key_prefix)
        manager = EmailCodeManager(
            store,
            secret=settings.verification_code_hmac_secret,
            ttl_seconds=settings.verification_code_ttl_seconds,
        )
        email_hash, digest = manager.coordinates(
            email, verification_code, purpose=purpose
        )
        try:
            claim_id = secrets.token_urlsafe(18)
            claim = store.claim(
                purpose,
                email_hash,
                generation,
                digest,
                claim_id=claim_id,
                lease_seconds=settings.verification_code_send_lease_seconds,
            )
            if claim.busy:
                raise self.retry(countdown=claim.retry_after_seconds)
            if not claim.claimed:
                return
            try:
                if deliver:
                    _run_smtp_subprocess(
                        settings=settings,
                        store=store,
                        purpose=purpose,
                        email_hash=email_hash,
                        generation=generation,
                        digest=digest,
                        claim_id=claim_id,
                        email=email,
                        verification_code=verification_code,
                    )
            except BaseException:
                store.release(purpose, email_hash, generation, digest, claim_id)
                raise
            if not store.mark_sent(purpose, email_hash, generation, digest, claim_id):
                raise ApiError(
                    "AUTH_SERVICE_UNAVAILABLE",
                    "Authentication service unavailable",
                    503,
                )
        finally:
            client.close()

    # Keep a stable importable marker for clean worker registry assertions.
    setattr(send_verification_email, "__narrato_registered__", True)


def task_names(app: Celery) -> set[str]:
    """返回当前 app 上的 Narrato 自有任务名。"""

    return {name for name in app.tasks if name.startswith("narrato.")}
