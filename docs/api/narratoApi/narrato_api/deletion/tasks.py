from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Protocol

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from narrato_api.assets.models import Asset
from narrato_api.projects.models import DeletionJob, Project


class OssDeletionClient(Protocol):
    """删除已登记对象所需的最小 OSS 能力。"""

    def delete_object(self, bucket: str, object_key: str) -> None: ...


class ProjectDeletionWorker:
    """幂等执行待处理或可重试 Job 的项目对象删除。"""

    def __init__(
        self,
        session_factory: Callable[[], Session],
        oss_client: OssDeletionClient,
        *,
        now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self._session_factory = session_factory
        self._oss_client = oss_client
        self._now = now

    def run_pending_job(self, job_id: str) -> bool:
        """删除项目已登记 OSS 对象并写入可恢复的审计终态。"""

        with self._session_factory() as session:
            job = session.scalar(
                select(DeletionJob).where(DeletionJob.id == job_id).with_for_update()
            )
            if job is None or job.status not in {"pending", "retryable_failed"}:
                return False
            project = session.scalar(
                select(Project)
                .where(Project.id == job.project_id, Project.user_id == job.user_id)
                .with_for_update()
            )
            if project is None or project.status != "deleting":
                return False
            active_reservation = session.scalar(
                select(Asset.id)
                .where(
                    Asset.project_id == project.id,
                    Asset.user_id == job.user_id,
                    Asset.reservation_expires_at.is_not(None),
                    Asset.reservation_expires_at > self._now(),
                )
                .limit(1)
            )
            if active_reservation is not None:
                # 已签发的 OSS Policy 在过期前仍可能完成直传。保持 pending，
                # 等 Policy 失效后再删除，避免 Worker 清理后出现迟到对象。
                if job.status != "pending" or job.last_error is not None:
                    job.status = "pending"
                    job.last_error = None
                    session.commit()
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
                    shared_count = int(
                        session.scalar(
                            select(func.count())
                            .select_from(Asset)
                            .join(Project, Project.id == Asset.project_id)
                            .where(
                                Asset.bucket == asset.bucket,
                                Asset.object_key == asset.object_key,
                                Asset.project_id != project.id,
                                Project.status != "deleted",
                            )
                        )
                        or 0
                    )
                    if shared_count == 0:
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
