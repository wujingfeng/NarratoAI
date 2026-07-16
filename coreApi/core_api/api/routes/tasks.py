from __future__ import annotations

from typing import Annotated
from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from core_api.api.dependencies import (
    get_database_session,
    get_request_id,
    require_service_token,
)
from core_api.api.errors import ApiError
from core_api.api.responses import envelope
from core_api.tasks.celery_tasks import wake_core_task
from core_api.tasks.dispatch import TaskDispatcher
from core_api.tasks.models import CoreArtifact
from core_api.tasks.service import TaskNotFoundError, TaskService


class CeleryTaskDispatcher:
    """默认通过无 Result Backend 的 Celery 任务唤醒数据库任务。"""

    def dispatch(
        self,
        task_id: str,
        *,
        expected_state_version: int,
        not_before: datetime,
        dispatch_id: str,
    ) -> None:
        """发送可安全重复的数据库事实源唤醒。"""

        wake_core_task.delay(
            task_id,
            expected_state_version,
            not_before.isoformat(),
            dispatch_id,
        )


def get_task_dispatcher() -> TaskDispatcher:
    """返回默认 Celery dispatcher，测试可注入 Fake。"""

    return CeleryTaskDispatcher()


router = APIRouter(dependencies=[Depends(require_service_token)])


@router.get("/{core_task_id}")
def get_core_task(
    core_task_id: str,
    session: Annotated[Session, Depends(get_database_session)],
    request_id: Annotated[str, Depends(get_request_id)],
) -> dict[str, object]:
    """统一查询 Core Task 状态、进度、错误与产物。"""

    try:
        task = TaskService(session).get_task(core_task_id)
    except TaskNotFoundError as exc:
        raise ApiError("CORE_TASK_NOT_FOUND", "Core 任务不存在", 404) from exc
    artifacts = session.scalars(
        select(CoreArtifact)
        .where(CoreArtifact.core_task_id == task.id)
        .order_by(CoreArtifact.created_at, CoreArtifact.id)
    ).all()
    data = {
        "core_task_id": task.id,
        "status": task.status.value,
        "phase": task.phase,
        "progress": task.progress,
        "error": task.error,
        "artifacts": [
            {
                "artifact_id": item.id,
                "kind": item.kind,
                "bucket": item.bucket,
                "object_key": item.object_key,
                "url": item.url,
                "content_type": item.content_type,
                "size": item.size,
                "checksum": item.checksum,
            }
            for item in artifacts
        ],
    }
    return envelope(
        request_id=request_id,
        code="TASK_STATUS",
        message="任务状态已获取",
        data=data,
    )
