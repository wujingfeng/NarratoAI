from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from narrato_api.assets.models import Asset
from narrato_api.projects.models import DeletionJob, Project


class OssDeletionClient(Protocol):
    """删除已登记对象所需的最小 OSS 能力。"""

    def delete_object(self, bucket: str, object_key: str) -> None: ...


class ProjectDeletionWorker:
    """仅执行已登记 pending Job 的项目对象删除。"""

    def __init__(
        self, session_factory: Callable[[], Session], oss_client: OssDeletionClient
    ) -> None:
        self._session_factory = session_factory
        self._oss_client = oss_client

    def run_pending_job(self, job_id: str) -> bool:
        """删除项目已登记 OSS 对象并写入可恢复的审计终态。"""

        with self._session_factory() as session:
            job = session.scalar(
                select(DeletionJob).where(DeletionJob.id == job_id).with_for_update()
            )
            if job is None or job.status != "pending":
                return False
            project = session.scalar(
                select(Project)
                .where(Project.id == job.project_id, Project.user_id == job.user_id)
                .with_for_update()
            )
            if project is None or project.status != "deleting":
                return False
            assets = list(
                session.scalars(
                    select(Asset)
                    .where(Asset.project_id == project.id, Asset.user_id == job.user_id)
                    .order_by(Asset.id)
                )
            )
            try:
                for asset in assets:
                    self._oss_client.delete_object(asset.bucket, asset.object_key)
            except Exception as error:
                job.attempt_count += 1
                job.last_error = type(error).__name__[:128]
                job.status = "retryable_failed"
                session.commit()
                return False
            job.attempt_count += 1
            job.last_error = None
            job.status = "completed"
            project.status = "deleted"
            session.commit()
            return True
