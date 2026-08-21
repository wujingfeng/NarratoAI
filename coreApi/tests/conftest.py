from __future__ import annotations

# ruff: noqa: E402 -- source-checkout path must be fixed before Core imports.

import os
import sys
from pathlib import Path
from collections.abc import Iterator

os.environ.setdefault("NARRATO_CORE_ENABLE_MONOREPO_FALLBACK", "1")
repository_root = str(Path(__file__).resolve().parents[2])
if repository_root in sys.path:
    sys.path.remove(repository_root)
sys.path.insert(0, repository_root)
for module_name in [
    name for name in sys.modules if name == "app" or name.startswith("app.")
]:
    del sys.modules[module_name]

import pytest
from fastapi.testclient import TestClient

from core_api.api.dependencies import get_readiness_checker, get_settings
from core_api.config import Settings
from core_api.main import create_app


class FakeReadinessChecker:
    """为健康检查提供可控的依赖状态。"""

    def __init__(self, *, ready: bool = True) -> None:
        self.ready = ready

    async def __call__(self) -> None:
        if not self.ready:
            from core_api.api.errors import ServiceUnavailableError

            raise ServiceUnavailableError("依赖服务未就绪")


@pytest.fixture
def settings(tmp_path) -> Settings:
    """创建不访问外部服务的测试配置。"""

    return Settings(
        database_url=f"sqlite:///{tmp_path / 'core.db'}",
        redis_url="redis://127.0.0.1:6379/15",
        celery_broker_url="redis://127.0.0.1:6379/14",
        service_token="test-service-token",
        callback_token="test-callback-token",
        callback_url="https://narrato.example.test/api/v1/internal/core/callbacks",
        cdn_public_base_url="https://cdn.example.test",
        cdn_allowed_hosts=["cdn.example.test"],
        work_root=tmp_path / "work",
    )


@pytest.fixture
def app(settings):
    """创建使用 Fake 就绪检查器的应用。"""

    application = create_app(settings=settings)
    application.dependency_overrides[get_settings] = lambda: settings
    application.dependency_overrides[get_readiness_checker] = lambda: (
        FakeReadinessChecker()
    )
    return application


@pytest.fixture
def client(app) -> Iterator[TestClient]:
    """提供同步 HTTP 测试客户端。"""

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def session(tmp_path):
    """提供带完整 Core 元数据且支持独立心跳 Session 的数据库会话。"""

    from sqlalchemy import create_engine, event
    from sqlalchemy.orm import Session

    from core_api.database import Base
    from core_api.tasks import models as task_models  # noqa: F401

    engine = create_engine(
        f"sqlite+pysqlite:///{tmp_path / 'unit.db'}",
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as database_session:
        yield database_session


@pytest.fixture
def task_service(session):
    """提供使用测试数据库的任务服务。"""

    from core_api.tasks.service import TaskService

    return TaskService(session)


@pytest.fixture
def task(task_service):
    """创建一个默认 Core Task。"""

    return task_service.create_core_task(
        caller="narrato-api",
        route="/api/v1/tasks/video-analysis",
        task_type="video_analysis",
        idempotency_key="create-default-task",
        input_snapshot={"video_url": "https://cdn.example.test/video.mp4"},
    )


# 固定 source-checkout 测试使用完整 monorepo app，而非 editable wheel 的 vendor 子集。
__import__("app")
