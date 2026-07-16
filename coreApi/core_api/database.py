from __future__ import annotations

from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from core_api.config import Settings, get_cached_settings


class Base(DeclarativeBase):
    """Core API 数据表的声明式基类。"""


@lru_cache(maxsize=8)
def create_database_engine(database_url: str) -> Engine:
    """为 Core 独立数据库创建 SQLAlchemy 2 引擎。"""

    engine = create_engine(database_url, pool_pre_ping=True)
    if engine.dialect.name == "sqlite":

        @event.listens_for(engine, "connect")
        def enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
            """为每个 SQLite 连接实际启用外键约束。"""

            autocommit = getattr(dbapi_connection, "autocommit", None)
            if autocommit is not None:
                dbapi_connection.autocommit = True
            cursor = dbapi_connection.cursor()
            try:
                cursor.execute("PRAGMA foreign_keys=ON")
            finally:
                cursor.close()
                if autocommit is not None:
                    dbapi_connection.autocommit = autocommit
    return engine


def get_engine(settings: Settings | None = None) -> Engine:
    """返回当前配置对应的 Core 数据库引擎。"""

    current = settings or get_cached_settings()
    return create_database_engine(current.database_url)


def get_session(settings: Settings | None = None) -> Iterator[Session]:
    """提供请求作用域的 Core 数据库会话。"""

    factory = sessionmaker(bind=get_engine(settings), expire_on_commit=False)
    with factory() as session:
        yield session
