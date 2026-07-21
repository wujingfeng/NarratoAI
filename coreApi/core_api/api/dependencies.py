from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
import threading
import hmac
import os
from pathlib import Path
import secrets
from collections.abc import Iterator
from typing import Annotated, Protocol

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.orm import Session

from core_api.api.errors import ServiceUnavailableError, UnauthorizedError
from core_api.config import Settings, get_cached_settings
from core_api.database import get_engine, get_session
from core_api.infrastructure.oss_client import CdnUrlPolicy, Oss2Client
from core_api.tasks.callbacks import validate_callback_url

_bearer = HTTPBearer(auto_error=False)


class BoundedReadinessExecutor:
    """拒绝无界排队并可随 FastAPI 生命周期关闭的就绪探针执行器。"""

    def __init__(self, *, max_workers: int = 2) -> None:
        self.max_workers = max_workers
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="core-oss-ready"
        )
        self._capacity = threading.BoundedSemaphore(max_workers)
        self._closed = False
        self.submitted = 0

    async def run(self, checker: OssReadinessChecker, *, timeout: float) -> None:
        """仅在有真实 Worker 槽时 submit，槽在线程实际结束后释放。"""

        if self._closed or not self._capacity.acquire(blocking=False):
            raise RuntimeError("OSS_READINESS_BUSY")
        try:
            concurrent_future = self._executor.submit(checker)
            self.submitted += 1
        except BaseException:
            self._capacity.release()
            raise
        concurrent_future.add_done_callback(lambda _future: self._capacity.release())
        wrapped = asyncio.wrap_future(concurrent_future)
        await asyncio.wait_for(asyncio.shield(wrapped), timeout=timeout)

    def close(self) -> None:
        """停止新提交并取消尚未运行的探针。"""

        self._closed = True
        self._executor.shutdown(wait=False, cancel_futures=True)

    @property
    def closed(self) -> bool:
        """返回执行器是否已拒绝生命周期外提交。"""

        return self._closed


_DEFAULT_OSS_READINESS_EXECUTOR = BoundedReadinessExecutor()


async def run_bounded_oss_readiness_probe(
    checker: OssReadinessChecker,
    *,
    timeout: float,
    executor: BoundedReadinessExecutor | None = None,
) -> None:
    """在专用双线程 executor 中执行 OSS 探针，避免污染全局线程池。"""

    await (executor or _DEFAULT_OSS_READINESS_EXECUTOR).run(checker, timeout=timeout)


class ReadinessChecker(Protocol):
    """抽象数据库、Redis 与必要配置的就绪检查。"""

    async def __call__(self) -> None: ...


class OssReadinessChecker(Protocol):
    """同步最小 OSS bucket 可用性探针。"""

    def __call__(self) -> None: ...


class DefaultReadinessChecker:
    """检查 Core 数据库、Redis 和服务凭据。"""

    def __init__(
        self,
        settings: Settings,
        oss_readiness_checker: OssReadinessChecker,
        readiness_executor: BoundedReadinessExecutor | None = None,
    ) -> None:
        self.settings = settings
        self.oss_readiness_checker = oss_readiness_checker
        self.readiness_executor = readiness_executor

    def _check_database(self) -> None:
        """在线程中执行同步 SQLAlchemy 探针。"""

        with get_engine(self.settings).connect() as connection:
            connection.execute(text("SELECT 1"))

    async def _check_redis(self) -> None:
        """使用显式 socket 超时探测 Core Redis。"""

        timeout = self.settings.readiness_timeout_seconds
        redis = Redis.from_url(
            self.settings.redis_url,
            socket_connect_timeout=timeout,
            socket_timeout=timeout,
            retry_on_timeout=False,
        )
        try:
            await redis.ping()
        finally:
            await redis.aclose()

    def _check_workspace(self) -> None:
        """确认 attempt 根目录可安全创建并写入临时探针。"""

        root = Path(self.settings.work_root)
        root.mkdir(parents=True, exist_ok=True)
        if root.is_symlink() or not root.is_dir():
            raise RuntimeError("WORK_ROOT_INVALID")
        probe = root / f".ready-{secrets.token_hex(8)}"
        descriptor = os.open(probe, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.close(descriptor)
        probe.unlink()

    async def __call__(self) -> None:
        if not required_configuration_is_present(self.settings):
            raise ServiceUnavailableError()
        timeout = self.settings.readiness_timeout_seconds
        try:
            # SQLAlchemy 同步驱动放入受控线程，避免依赖故障阻塞 live。
            await asyncio.wait_for(
                asyncio.to_thread(self._check_database), timeout=timeout
            )
            await asyncio.wait_for(self._check_redis(), timeout=timeout)
            await asyncio.wait_for(
                asyncio.to_thread(self._check_workspace), timeout=timeout
            )
            await run_bounded_oss_readiness_probe(
                self.oss_readiness_checker,
                timeout=timeout,
                executor=self.readiness_executor,
            )
        except Exception as error:
            # 对外只暴露稳定错误，连接地址和驱动异常仅留给内部日志。
            raise ServiceUnavailableError() from error


def required_configuration_is_present(settings: Settings) -> bool:
    """确认服务凭据和 OSS 必要配置均已提供。"""

    if not all(
        (
            settings.service_token,
            settings.callback_token,
            settings.callback_url,
            settings.oss_endpoint,
            settings.oss_bucket,
            settings.oss_access_key_id,
            settings.oss_access_key_secret,
            settings.oss_public_base_url,
            settings.cdn_allowed_hosts,
        )
    ):
        return False
    try:
        validate_callback_url(settings.callback_url)
        CdnUrlPolicy(set(settings.cdn_allowed_hosts))
        Oss2Client(
            endpoint=settings.oss_endpoint,
            bucket=settings.oss_bucket,
            access_key_id=settings.oss_access_key_id,
            access_key_secret=settings.oss_access_key_secret,
            public_base_url=settings.oss_public_base_url,
            connect_timeout=settings.readiness_timeout_seconds,
            read_timeout=settings.readiness_timeout_seconds,
        )
    except ValueError:
        return False
    return Path(settings.work_root).is_absolute()


def get_settings(request: Request) -> Settings:
    """从应用状态返回当前 Core 配置。"""

    if hasattr(request.app.state, "settings"):
        return request.app.state.settings
    return get_cached_settings()


def get_database_session(
    settings: Annotated[Settings, Depends(get_settings)],
) -> Iterator[Session]:
    """提供绑定当前应用配置的请求作用域数据库会话。"""

    yield from get_session(settings)


def get_oss_readiness_checker(
    settings: Annotated[Settings, Depends(get_settings)],
) -> OssReadinessChecker:
    """创建只持有私有配置的最小 OSS bucket 探针。"""

    try:
        client = Oss2Client(
            endpoint=settings.oss_endpoint,
            bucket=settings.oss_bucket,
            access_key_id=settings.oss_access_key_id,
            access_key_secret=settings.oss_access_key_secret,
            public_base_url=settings.oss_public_base_url,
            connect_timeout=settings.readiness_timeout_seconds,
            read_timeout=settings.readiness_timeout_seconds,
        )
    except ValueError:

        def unavailable() -> None:
            """将无效 OSS 配置统一转换为安全未就绪。"""

            raise ServiceUnavailableError()

        return unavailable
    return client.check_ready


def get_readiness_checker(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    oss_checker: Annotated[OssReadinessChecker, Depends(get_oss_readiness_checker)],
) -> ReadinessChecker:
    """创建默认依赖就绪检查器，测试可覆盖此 Dependency。"""

    return DefaultReadinessChecker(
        settings,
        oss_checker,
        getattr(request.app.state, "oss_readiness_executor", None),
    )


def get_request_id(request: Request) -> str:
    """返回请求 ID 中间件写入的关联标识。"""

    return request.state.request_id


def require_service_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    """集中校验 narratoApi 调用 Core 的固定 Bearer Token。"""

    if (
        credentials is None
        or credentials.scheme.lower() != "bearer"
        or not settings.service_token
        or not hmac.compare_digest(credentials.credentials, settings.service_token)
    ):
        raise UnauthorizedError()
