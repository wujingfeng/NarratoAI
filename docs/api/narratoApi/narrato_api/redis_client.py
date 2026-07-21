from __future__ import annotations

from typing import Protocol, cast

from redis.asyncio import Redis

from narrato_api.config import Settings


class RedisClient(Protocol):
    """业务层实际使用的最小异步 Redis 协议。"""

    async def ping(self) -> bool: ...

    async def aclose(self) -> None: ...


def create_redis_client(settings: Settings) -> RedisClient:
    """按请求配置创建不共享全局连接的 Redis 客户端。"""

    timeout = settings.readiness_timeout_seconds
    return cast(
        RedisClient,
        Redis.from_url(
            settings.redis_url,
            socket_connect_timeout=timeout,
            socket_timeout=timeout,
            retry_on_timeout=False,
        ),
    )
