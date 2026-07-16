from __future__ import annotations

from datetime import datetime, timedelta
from enum import StrEnum
import asyncio
import ipaddress
import re
import threading
import time
from collections.abc import Callable
from typing import Protocol
from urllib.parse import urlsplit, urlunsplit

import httpx
from sqlalchemy import case, select, update
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session, sessionmaker

from core_api.ids import new_time_ordered_id
from core_api.tasks.models import CallbackOutbox, CallbackStatus, CoreTask, utc_now


class OutboxEventConflictError(RuntimeError):
    """event_id 已被另一逻辑状态事件占用。"""


class CallbackDeliveryResult(StrEnum):
    """回调 HTTP 响应的稳定投递分类。"""

    SUCCESS = "success"
    RETRY = "retry"


_DNS_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")


def validate_callback_url(value: str) -> str:
    """规范化固定 HTTPS 回调地址并拒绝 IP、私网和歧义语法。"""

    try:
        parsed = urlsplit(str(value or ""))
        port = parsed.port
        raw_host = parsed.hostname or ""
        host = raw_host.rstrip(".").encode("idna").decode("ascii").lower()
    except (UnicodeError, ValueError) as exc:
        raise ValueError("CALLBACK_URL_INVALID") from exc
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise ValueError("CALLBACK_URL_INVALID")
    labels = host.split(".")
    if (
        parsed.scheme.lower() != "https"
        or not host
        or len(host) > 253
        or any(not _DNS_LABEL.fullmatch(label) for label in labels)
        or host == "localhost"
        or host.endswith((".localhost", ".local", ".internal"))
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or port not in (None, 443)
        or not parsed.path.startswith("/")
        or "\\" in parsed.path
        or any(ord(char) < 0x20 for char in parsed.path)
    ):
        raise ValueError("CALLBACK_URL_INVALID")
    return urlunsplit(("https", host, parsed.path or "/", "", ""))


class CallbackClient(Protocol):
    """请求级 Core 状态回调客户端协议。"""

    def deliver(self, event: dict[str, object]) -> CallbackDeliveryResult:
        """投递统一事件并返回稳定分类。"""

        ...


class HttpCallbackClient:
    """使用独立 Bearer 和有界超时的 HTTPS 回调客户端。"""

    def __init__(
        self,
        url: str,
        token: str,
        *,
        connect_timeout: float = 3.0,
        read_timeout: float = 10.0,
        total_timeout: float = 15.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not token:
            raise ValueError("CALLBACK_URL_INVALID")
        if min(connect_timeout, read_timeout, total_timeout) <= 0:
            raise ValueError("CALLBACK_TIMEOUT_INVALID")
        self.url = validate_callback_url(url)
        self.token = token
        self.timeout = httpx.Timeout(
            connect=connect_timeout,
            read=read_timeout,
            write=read_timeout,
            pool=connect_timeout,
        )
        self.total_timeout = total_timeout
        self.transport = transport

    def deliver(self, event: dict[str, object]) -> CallbackDeliveryResult:
        """发送一次回调；不暴露响应正文或私有凭据。"""

        started_at = time.monotonic()
        try:
            status_code = asyncio.run(
                asyncio.wait_for(
                    self._post(event), timeout=self.total_timeout
                )
            )
        except (TimeoutError, httpx.HTTPError):
            return CallbackDeliveryResult.RETRY
        if time.monotonic() - started_at > self.total_timeout:
            return CallbackDeliveryResult.RETRY
        return (
            CallbackDeliveryResult.SUCCESS
            if 200 <= status_code < 300
            else CallbackDeliveryResult.RETRY
        )

    async def _post(self, event: dict[str, object]) -> int:
        """流式读取响应头后立即关闭响应，不等待或保留响应正文。"""

        event_id = event.get("event_id")
        if not isinstance(event_id, str) or not event_id:
            raise ValueError("CALLBACK_EVENT_INVALID")
        async with httpx.AsyncClient(
            transport=self.transport, timeout=self.timeout
        ) as client:
            async with client.stream(
                "POST",
                self.url,
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "X-Idempotency-Key": event_id,
                },
                json=event,
            ) as response:
                return response.status_code


class _ClaimHeartbeat:
    """使用独立 Session 延长单个已认领 Outbox 的可见性截止时间。"""

    def __init__(
        self,
        *,
        session_factory: Callable[[], Session],
        row: CallbackOutbox,
        claim_seconds: float,
    ) -> None:
        self.session_factory = session_factory
        self.row_id = row.id
        self.event_id = row.event_id
        self.state_version = row.state_version
        self.claim_seconds = claim_seconds
        self.interval_seconds = max(0.01, claim_seconds / 3)
        self.failed = threading.Event()
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._run,
            name=f"core-callback-claim-{row.id}",
        )

    def start(self) -> None:
        self._thread.start()

    def stop_and_join(self) -> None:
        self._stop.set()
        self._thread.join()

    def _extend_claim(self) -> bool:
        extended_at = utc_now()
        claim_until = extended_at + timedelta(seconds=self.claim_seconds)
        with self.session_factory() as heartbeat_session:
            result = heartbeat_session.execute(
                update(CallbackOutbox)
                .where(
                    CallbackOutbox.id == self.row_id,
                    CallbackOutbox.event_id == self.event_id,
                    CallbackOutbox.state_version == self.state_version,
                    CallbackOutbox.status == CallbackStatus.PENDING,
                )
                .values(
                    next_attempt_at=case(
                        (
                            CallbackOutbox.next_attempt_at < claim_until,
                            claim_until,
                        ),
                        else_=CallbackOutbox.next_attempt_at,
                    ),
                    updated_at=extended_at,
                )
                .execution_options(synchronize_session=False)
            )
            if getattr(result, "rowcount", 0) != 1:
                heartbeat_session.rollback()
                return False
            heartbeat_session.commit()
            return True

    def _run(self) -> None:
        try:
            if not self._extend_claim():
                self.failed.set()
                return
            while not self._stop.wait(self.interval_seconds):
                if not self._extend_claim():
                    self.failed.set()
                    return
        except Exception:
            self.failed.set()


class CallbackOutboxPublisher:
    """并发安全认领并可靠发送持久 callback Outbox。"""

    def __init__(
        self,
        session: Session,
        *,
        base_backoff_seconds: float = 5.0,
        max_backoff_seconds: float = 3600.0,
        minimum_claim_seconds: float = 30.0,
        heartbeat_session_factory: Callable[[], Session] | None = None,
    ) -> None:
        self.session = session
        self.base_backoff_seconds = base_backoff_seconds
        self.max_backoff_seconds = max_backoff_seconds
        self.minimum_claim_seconds = minimum_claim_seconds
        bind = session.get_bind()
        engine = bind.engine if isinstance(bind, Connection) else bind
        self.heartbeat_session_factory = heartbeat_session_factory or sessionmaker(
            bind=engine, expire_on_commit=False
        )

    def _heartbeat(self, row: CallbackOutbox) -> _ClaimHeartbeat | None:
        if self.minimum_claim_seconds <= 0:
            return None
        return _ClaimHeartbeat(
            session_factory=self.heartbeat_session_factory,
            row=row,
            claim_seconds=self.minimum_claim_seconds,
        )

    def _claim(
        self, row_id: str, *, observed_at: datetime
    ) -> CallbackOutbox | None:
        """在网络调用前原子增加次数并持久化下一投递时间。"""

        candidate = self.session.get(CallbackOutbox, row_id)
        if candidate is None:
            return None
        delay = max(
            self.minimum_claim_seconds,
            min(
                self.max_backoff_seconds,
                self.base_backoff_seconds * (2 ** min(candidate.attempt_count, 16)),
            ),
        )
        result = self.session.execute(
            update(CallbackOutbox)
            .where(
                CallbackOutbox.id == row_id,
                CallbackOutbox.status == CallbackStatus.PENDING,
                CallbackOutbox.next_attempt_at <= observed_at,
            )
            .values(
                attempt_count=CallbackOutbox.attempt_count + 1,
                next_attempt_at=observed_at + timedelta(seconds=delay),
                updated_at=observed_at,
            )
            .execution_options(synchronize_session=False)
        )
        claimed = getattr(result, "rowcount", 0) == 1
        self.session.commit()
        if not claimed:
            return None
        self.session.expire_all()
        return self.session.get(CallbackOutbox, row_id)

    def publish_pending(
        self,
        client: CallbackClient,
        *,
        now: datetime | None = None,
        limit: int = 100,
    ) -> int:
        """公平扫描 due pending；成功或确定性拒绝后原子结束。"""

        observed_at = now or utc_now()
        ids = self.session.scalars(
            select(CallbackOutbox.id)
            .where(
                CallbackOutbox.status == CallbackStatus.PENDING,
                CallbackOutbox.next_attempt_at <= observed_at,
            )
            .order_by(
                CallbackOutbox.next_attempt_at,
                CallbackOutbox.created_at,
                CallbackOutbox.id,
            )
            .limit(min(1000, max(0, limit)))
        ).all()
        completed = 0
        for row_id in ids:
            row = self._claim(row_id, observed_at=observed_at)
            if row is None:
                continue
            heartbeat = self._heartbeat(row)
            if heartbeat is not None:
                heartbeat.start()
            try:
                outcome = client.deliver(dict(row.payload))
            except Exception:
                outcome = CallbackDeliveryResult.RETRY
            finally:
                if heartbeat is not None:
                    heartbeat.stop_and_join()
            if heartbeat is not None and heartbeat.failed.is_set():
                outcome = CallbackDeliveryResult.RETRY
            if outcome != CallbackDeliveryResult.SUCCESS:
                continue
            completed_at = utc_now()
            self.session.execute(
                update(CallbackOutbox)
                .where(
                    CallbackOutbox.id == row.id,
                    CallbackOutbox.event_id == row.event_id,
                    CallbackOutbox.state_version == row.state_version,
                    CallbackOutbox.status == CallbackStatus.PENDING,
                )
                .values(
                    status=CallbackStatus.SENT,
                    sent_at=completed_at,
                    updated_at=completed_at,
                )
                .execution_options(synchronize_session=False)
            )
            self.session.commit()
            completed += 1
        return completed


def enqueue_state_callback(
    session: Session, task: CoreTask, *, event_id: str
) -> CallbackOutbox:
    """为任务当前状态版本幂等写入回调 Outbox。"""

    event_row = session.scalar(
        select(CallbackOutbox).where(CallbackOutbox.event_id == event_id)
    )
    if event_row is not None:
        if (
            event_row.core_task_id == task.id
            and event_row.state_version == task.state_version
        ):
            return event_row
        raise OutboxEventConflictError("OUTBOX_EVENT_CONFLICT")

    state_row = session.scalar(
        select(CallbackOutbox).where(
            CallbackOutbox.core_task_id == task.id,
            CallbackOutbox.state_version == task.state_version,
        )
    )
    if state_row is not None:
        return state_row
    row = CallbackOutbox(
        id=new_time_ordered_id("cb_"),
        event_id=event_id,
        core_task_id=task.id,
        attempt_no=task.current_attempt_no,
        state_version=task.state_version,
        payload={
            "event_id": event_id,
            "core_task_id": task.id,
            "attempt_no": task.current_attempt_no,
            "state_version": task.state_version,
            "status": task.status.value,
            "phase": task.phase,
            "progress": task.progress,
            "result": task.result,
            "error": task.error,
        },
    )
    session.add(row)
    return row
