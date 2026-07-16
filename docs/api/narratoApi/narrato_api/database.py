from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
import math
import threading
from typing import Any

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from narrato_api.config import Settings, get_cached_settings


class Base(DeclarativeBase):
    """业务数据库模型的声明式基类。"""


EngineKey = tuple[str, float, float]


@dataclass(slots=True)
class _EngineEntry:
    """保存一个配置键对应的 Engine 及应用持有计数。"""

    engine: Engine
    owners: int = 0


_ENGINE_REGISTRY: dict[EngineKey, _EngineEntry] = {}
_ENGINE_REGISTRY_LOCK = threading.Lock()


def create_database_engine(
    database_url: str,
    connect_timeout: float = 3.0,
    read_timeout: float = 3.0,
) -> Engine:
    """创建只连接 narratoApi 业务数据库的引擎。"""

    kwargs: dict[str, object] = {"pool_pre_ping": True}
    if database_url.startswith("postgresql"):
        statement_timeout_ms = max(1, math.ceil(read_timeout * 1000))
        kwargs["pool_timeout"] = read_timeout
        kwargs["connect_args"] = {
            "connect_timeout": max(1, math.floor(connect_timeout)),
            "options": (
                f"-c statement_timeout={statement_timeout_ms} "
                f"-c lock_timeout={statement_timeout_ms}"
            ),
        }
    elif database_url.startswith("sqlite"):
        kwargs["connect_args"] = {"timeout": read_timeout}
    engine = create_engine(database_url, **kwargs)
    if engine.dialect.name == "sqlite":
        busy_timeout_ms = max(1, math.ceil(read_timeout * 1000))

        @event.listens_for(engine, "connect")
        def enable_sqlite_foreign_keys(dbapi_connection: Any, _record: Any) -> None:
            """测试连接开启外键并限制锁等待时间。"""

            cursor = dbapi_connection.cursor()
            try:
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.execute(f"PRAGMA busy_timeout={busy_timeout_ms}")
            finally:
                cursor.close()
    return engine


def _engine_key(settings: Settings) -> EngineKey:
    """构造包含实际 readiness deadline 的稳定 Engine 配置键。"""

    deadline = settings.readiness_timeout_seconds
    return (
        settings.database_url,
        min(settings.database_connect_timeout_seconds, deadline),
        min(settings.database_read_timeout_seconds, deadline),
    )


def _get_or_create_entry(settings: Settings) -> _EngineEntry:
    """在同一临界区复用或创建配置专属 Engine。"""

    key = _engine_key(settings)
    with _ENGINE_REGISTRY_LOCK:
        entry = _ENGINE_REGISTRY.get(key)
        if entry is None:
            entry = _EngineEntry(create_database_engine(*key))
            _ENGINE_REGISTRY[key] = entry
        return entry


def get_engine(settings: Settings | None = None) -> Engine:
    """返回当前配置的独立业务数据库引擎。"""

    current = settings or get_cached_settings()
    return _get_or_create_entry(current).engine


def acquire_database_engine(settings: Settings) -> Engine:
    """为一个运行中应用持有配置对应的共享 Engine。"""

    key = _engine_key(settings)
    with _ENGINE_REGISTRY_LOCK:
        entry = _ENGINE_REGISTRY.get(key)
        if entry is None:
            entry = _EngineEntry(create_database_engine(*key))
            _ENGINE_REGISTRY[key] = entry
        entry.owners += 1
        return entry.engine


def release_database_engine(settings: Settings) -> None:
    """释放一个应用所有权，仅由最后 owner 关闭对应连接池。"""

    key = _engine_key(settings)
    engine: Engine | None = None
    with _ENGINE_REGISTRY_LOCK:
        entry = _ENGINE_REGISTRY.get(key)
        if entry is None or entry.owners <= 0:
            return
        entry.owners -= 1
        if entry.owners == 0:
            engine = entry.engine
            del _ENGINE_REGISTRY[key]
    if engine is not None:
        engine.dispose()


def get_session(settings: Settings | None = None) -> Iterator[Session]:
    """提供请求作用域的业务数据库会话。"""

    factory = sessionmaker(bind=get_engine(settings), expire_on_commit=False)
    with factory() as session:
        yield session
