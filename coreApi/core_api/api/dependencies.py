from __future__ import annotations

import asyncio
import hmac
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

_bearer = HTTPBearer(auto_error=False)


class ReadinessChecker(Protocol):
    """抽象数据库、Redis 与必要配置的就绪检查。"""

    async def __call__(self) -> None: ...


class DefaultReadinessChecker:
    """检查 Core 数据库、Redis 和服务凭据。"""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

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
        except Exception as error:
            # 对外只暴露稳定错误，连接地址和驱动异常仅留给内部日志。
            raise ServiceUnavailableError() from error


def required_configuration_is_present(settings: Settings) -> bool:
    """确认服务凭据和 OSS 必要配置均已提供。"""

    return all(
        (
            settings.service_token,
            settings.callback_token,
            settings.oss_endpoint,
            settings.oss_bucket,
            settings.oss_access_key_id,
            settings.oss_access_key_secret,
        )
    )


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


def get_readiness_checker(
    settings: Annotated[Settings, Depends(get_settings)],
) -> ReadinessChecker:
    """创建默认依赖就绪检查器，测试可覆盖此 Dependency。"""

    return DefaultReadinessChecker(settings)


def get_request_id(request: Request) -> str:
    """返回请求 ID 中间件写入的关联标识。"""

    return request.state.request_id


def require_service_token(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(_bearer)
    ],
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
