from __future__ import annotations

from collections.abc import Iterator

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
        work_root=tmp_path / "work",
    )


@pytest.fixture
def app(settings):
    """创建使用 Fake 就绪检查器的应用。"""

    application = create_app(settings=settings)
    application.dependency_overrides[get_settings] = lambda: settings
    application.dependency_overrides[get_readiness_checker] = (
        lambda: FakeReadinessChecker()
    )
    return application


@pytest.fixture
def client(app) -> Iterator[TestClient]:
    """提供同步 HTTP 测试客户端。"""

    with TestClient(app) as test_client:
        yield test_client
