from __future__ import annotations

from typing import Annotated, Any, Literal
from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from core_api.api.dependencies import (
    get_database_session,
    get_request_id,
    require_service_token,
)
from core_api.api.errors import ApiError
from core_api.api.responses import ApiResponse, envelope
from core_api.tasks.celery_tasks import wake_core_task
from core_api.tasks.dispatch import TaskDispatcher
from core_api.tasks.models import CallbackOutbox, CoreArtifact
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


class CoreTaskErrorDTO(BaseModel):
    """可公开的稳定 Core Task 错误摘要。"""

    model_config = ConfigDict(extra="forbid")
    code: str
    retryable: bool | None = None


class CoreTaskArtifactDTO(BaseModel):
    """不含 bucket、object key 和本地路径的公开产物摘要。"""

    model_config = ConfigDict(extra="forbid")
    artifact_id: str
    kind: str
    url: str
    content_type: str
    size: int
    checksum: str | None = None


class CoreTaskDTO(BaseModel):
    """Core Task 查询的版本化公开 DTO。"""

    model_config = ConfigDict(extra="forbid")
    core_task_id: str
    status: str
    phase: str | None
    progress: int
    result: list[dict[str, Any]] | dict[str, Any] | None
    error: CoreTaskErrorDTO | None
    artifacts: list[CoreTaskArtifactDTO]


class CoreTaskEventDTO(BaseModel):
    """单个持久 Core Task 状态事件 DTO。"""

    model_config = ConfigDict(extra="forbid")
    event_id: str
    sequence: int
    event_type: Literal["core_task.state_changed"]
    time: datetime
    status: str
    phase: str | None
    progress: int
    attempt: int
    error: CoreTaskErrorDTO | None
    artifacts: list[CoreTaskArtifactDTO]


class CoreTaskEventsDTO(BaseModel):
    """Core Task 持久事件列表 DTO。"""

    model_config = ConfigDict(extra="forbid")
    events: list[CoreTaskEventDTO]


router = APIRouter(dependencies=[Depends(require_service_token)])


@router.get("/{core_task_id}", response_model=ApiResponse[CoreTaskDTO])
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
        "result": task.result,
        "error": _safe_event_error(task.error),
        "artifacts": [
            {
                "artifact_id": item.id,
                "kind": item.kind,
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


def _safe_event_error(value: object) -> dict[str, object] | None:
    """只公开稳定错误码与 retryable 标记。"""

    if not isinstance(value, dict):
        return None
    code = value.get("code")
    if not isinstance(code, str) or not code:
        return None
    safe: dict[str, object] = {"code": code}
    retryable = value.get("retryable")
    if isinstance(retryable, bool):
        safe["retryable"] = retryable
    return safe


@router.get(
    "/{core_task_id}/events",
    response_model=ApiResponse[CoreTaskEventsDTO],
)
def get_core_task_events(
    core_task_id: str,
    session: Annotated[Session, Depends(get_database_session)],
    request_id: Annotated[str, Depends(get_request_id)],
) -> dict[str, object]:
    """按单调状态版本返回持久且脱敏的 Core Task 事件。"""

    try:
        TaskService(session).get_task(core_task_id)
    except TaskNotFoundError as exc:
        raise ApiError("CORE_TASK_NOT_FOUND", "Core 任务不存在", 404) from exc
    rows = session.scalars(
        select(CallbackOutbox)
        .where(CallbackOutbox.core_task_id == core_task_id)
        .order_by(
            CallbackOutbox.state_version,
            CallbackOutbox.created_at,
            CallbackOutbox.id,
        )
    ).all()
    artifact_rows = session.scalars(
        select(CoreArtifact)
        .where(CoreArtifact.core_task_id == core_task_id)
        .order_by(CoreArtifact.created_at, CoreArtifact.id)
    ).all()
    artifacts_by_attempt: dict[int, list[dict[str, object]]] = {}
    for artifact in artifact_rows:
        artifacts_by_attempt.setdefault(artifact.attempt_no, []).append(
            {
                "artifact_id": artifact.id,
                "kind": artifact.kind,
                "url": artifact.url,
                "content_type": artifact.content_type,
                "size": artifact.size,
                "checksum": artifact.checksum,
            }
        )
    events: list[dict[str, object]] = []
    for row in rows:
        payload = row.payload
        events.append(
            {
                "event_id": row.event_id,
                "sequence": row.state_version,
                "event_type": "core_task.state_changed",
                "time": row.created_at.isoformat(),
                "status": payload.get("status"),
                "phase": payload.get("phase"),
                "progress": payload.get("progress"),
                "attempt": row.attempt_no,
                "error": _safe_event_error(payload.get("error")),
                "artifacts": (
                    artifacts_by_attempt.get(row.attempt_no, [])
                    if payload.get("status") == "succeeded"
                    else []
                ),
            }
        )
    return envelope(
        request_id=request_id,
        code="TASK_EVENTS",
        message="任务事件已获取",
        data={"events": events},
    )
