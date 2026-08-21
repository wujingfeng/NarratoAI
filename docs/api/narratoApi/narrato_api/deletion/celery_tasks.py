from __future__ import annotations

from celery import Celery
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from narrato_api.config import Settings
from narrato_api.database import create_database_engine
from narrato_api.deletion.tasks import ProjectDeletionWorker
from narrato_api.integrations.oss_client import HttpOssClient
from narrato_api.projects.models import DeletionJob


def _services(
    settings: Settings,
) -> tuple[Engine, sessionmaker[Session], HttpOssClient]:
    engine = create_database_engine(
        settings.database_url,
        settings.database_connect_timeout_seconds,
        settings.database_read_timeout_seconds,
    )
    return (
        engine,
        sessionmaker(bind=engine, expire_on_commit=False),
        HttpOssClient(
            endpoint=settings.oss_endpoint,
            access_key_id=settings.oss_access_key_id,
            access_key_secret=settings.oss_access_key_secret,
        ),
    )


def register_deletion_tasks(app: Celery, settings: Settings) -> None:
    """注册周期扫描删除 Job 的 Worker 入口；HTTP 路由不执行 OSS I/O。"""

    @app.task(name="narrato.deletion.sweep")  # type: ignore[untyped-decorator]
    def sweep_project_deletions(*, limit: int = 25) -> int:
        engine, sessions, oss_client = _services(settings)
        try:
            with sessions() as session:
                job_ids = list(
                    session.scalars(
                        select(DeletionJob.id)
                        .where(DeletionJob.status.in_({"pending", "retryable_failed"}))
                        .order_by(DeletionJob.created_at, DeletionJob.id)
                        .limit(limit)
                    )
                )
            worker = ProjectDeletionWorker(sessions, oss_client)
            return sum(worker.run_pending_job(job_id) for job_id in job_ids)
        finally:
            engine.dispose()

    setattr(sweep_project_deletions, "__narrato_registered__", True)
