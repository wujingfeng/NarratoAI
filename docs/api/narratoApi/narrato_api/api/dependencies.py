from __future__ import annotations

import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import Future
from typing import Protocol, cast

from fastapi import Request
from sqlalchemy import text

from narrato_api.api.errors import ServiceUnavailableError
from narrato_api.config import Settings, get_cached_settings
from narrato_api.database import get_engine
from narrato_api.redis_client import create_redis_client


class SyncProbe(Protocol):
    """可在线程池执行的同步依赖探针。"""

    def __call__(self) -> None: ...


class ReadinessChecker(Protocol):
    """数据库和 Redis 就绪检查的异步协议。"""

    async def __call__(self) -> None: ...


class BoundedReadinessExecutor:
    """拒绝无界排队并可由应用生命周期关闭的探针执行器。"""

    def __init__(self, *, max_workers: int = 2) -> None:
        """创建固定线程和等量容量槽。"""

        self._executor = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="narrato-ready"
        )
        self._capacity = threading.BoundedSemaphore(max_workers)
        self._lock = threading.Lock()
        self._futures: set[Future[None]] = set()
        self._closed = False
        self.submitted = 0

    async def run(self, probe: SyncProbe, *, timeout: float) -> None:
        """仅在有真实容量时提交同步探针并施加总超时。"""

        with self._lock:
            if self._closed:
                raise RuntimeError("READINESS_CLOSED")
            if not self._capacity.acquire(blocking=False):
                raise RuntimeError("READINESS_BUSY")
            try:
                future = self._executor.submit(probe)
                self._futures.add(future)
                self.submitted += 1
            except BaseException:
                self._capacity.release()
                raise
        future.add_done_callback(self._finish_future)
        await asyncio.wait_for(asyncio.shield(asyncio.wrap_future(future)), timeout)

    def _finish_future(self, future: Future[None]) -> None:
        """仅在线程真实结束后归还容量并移除追踪。"""

        with self._lock:
            self._futures.discard(future)
        self._capacity.release()

    def close(self) -> None:
        """拒绝新任务并取消尚未运行的探针。"""

        with self._lock:
            self._closed = True
            futures = tuple(self._futures)
        for future in futures:
            future.cancel()
        self._executor.shutdown(wait=False, cancel_futures=True)

    async def aclose(self, *, timeout: float) -> None:
        """停止提交并在有界时间内等待真实探针退出。"""

        with self._lock:
            self._closed = True
            futures = tuple(self._futures)
        for future in futures:
            future.cancel()
        if futures:
            wrapped = [asyncio.wrap_future(future) for future in futures]
            await asyncio.wait(wrapped, timeout=timeout)
        self._executor.shutdown(wait=False, cancel_futures=True)

    @property
    def closed(self) -> bool:
        """返回执行器是否已进入关闭状态。"""

        with self._lock:
            return self._closed


def check_database(settings: Settings) -> None:
    """执行最小业务数据库读探针。"""

    with get_engine(settings).connect() as connection:
        connection.execute(text("SELECT 1"))


class DefaultReadinessChecker:
    """使用独立超时并行检查 PostgreSQL 与 Redis。"""

    def __init__(self, settings: Settings, executor: BoundedReadinessExecutor) -> None:
        """绑定当前应用私有配置和有界执行器。"""

        self.settings = settings
        self.executor = executor

    async def _check_redis(self) -> None:
        """创建短生命周期 Redis 客户端并确保关闭。"""

        client = create_redis_client(self.settings)
        try:
            await client.ping()
        finally:
            await client.aclose()

    async def __call__(self) -> None:
        """并发检查两个依赖，任一异常统一转为安全 503。"""

        timeout = self.settings.readiness_timeout_seconds
        try:
            if not required_configuration_is_present(self.settings):
                raise RuntimeError("REQUIRED_CONFIGURATION_MISSING")
            async with asyncio.timeout(timeout):
                async with asyncio.TaskGroup() as group:
                    group.create_task(
                        self.executor.run(
                            lambda: check_database(self.settings), timeout=timeout
                        )
                    )
                    group.create_task(self._check_redis())
        except ExceptionGroup as error:
            raise ServiceUnavailableError() from error
        except Exception as error:
            raise ServiceUnavailableError() from error


def required_configuration_is_present(settings: Settings) -> bool:
    """确认 Core 双向凭据和业务命名空间均独立且非空。"""

    return bool(
        settings.core_request_token
        and settings.core_callback_token
        and settings.core_request_token != settings.core_callback_token
        and settings.redis_key_prefix
        and settings.celery_queue_prefix
    )


def get_settings(request: Request) -> Settings:
    """返回当前应用绑定的独立配置。"""

    if hasattr(request.app.state, "settings"):
        return cast(Settings, request.app.state.settings)
    return get_cached_settings()


def get_readiness_checker(request: Request) -> ReadinessChecker:
    """创建绑定当前应用资源的默认就绪检查器。"""

    return DefaultReadinessChecker(
        get_settings(request), request.app.state.readiness_executor
    )


def get_request_id(request: Request) -> str:
    """返回请求 ID 中间件写入的关联标识。"""

    return cast(str, request.state.request_id)
