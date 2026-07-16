from __future__ import annotations

from sqlalchemy.orm import Session
from fastapi import Header
from typing import Annotated
from collections.abc import Mapping

from core_api.api.errors import ApiError
from core_api.api.responses import envelope
from core_api.api.routes.tasks import TaskDispatcher
from core_api.tasks.dispatch import DispatchOutboxPublisher
from core_api.tasks.service import IdempotencyConflictError, TaskService


def require_idempotency_key(
    value: Annotated[str, Header(alias="X-Idempotency-Key", max_length=255)],
) -> str:
    """规范化幂等键并拒绝空白或控制字符。"""

    normalized = value.strip()
    if not normalized or any(
        ord(char) < 0x20 or ord(char) == 0x7F for char in normalized
    ):
        raise ApiError("VALIDATION_ERROR", "幂等键格式无效", 422)
    return normalized


def create_atomic_task(
    *,
    session: Session,
    dispatcher: TaskDispatcher,
    request_id: str,
    route: str,
    task_type: str,
    idempotency_key: str,
    input_snapshot: Mapping[str, object],
    caller_task_id: str | None,
    idempotency_payload: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """提交幂等数据库事实后仅为首次创建发送一次唤醒。"""

    try:
        creation = TaskService(session).create_core_task_result(
            caller="narrato-api",
            route=route,
            task_type=task_type,
            idempotency_key=idempotency_key,
            input_snapshot=dict(input_snapshot),
            caller_task_id=caller_task_id,
            idempotency_payload=(dict(idempotency_payload) if idempotency_payload else None),
        )
    except IdempotencyConflictError as exc:
        raise ApiError("IDEMPOTENCY_CONFLICT", "幂等键对应的请求体不同", 409) from exc
    # 首次或幂等重放都尝试发布 pending DB 事实；Broker 故障仍返回 202 并由扫描器恢复。
    DispatchOutboxPublisher(session).publish_task(creation.task.id, dispatcher)
    return envelope(
        request_id=request_id,
        code="TASK_CREATED",
        message="任务已创建",
        data=dict(
            creation.task.initial_response
            or {"core_task_id": creation.task.id, "status": "queued"}
        ),
    )


def replay_atomic_task(
    *,
    session: Session,
    dispatcher: TaskDispatcher,
    request_id: str,
    route: str,
    idempotency_key: str,
    idempotency_payload: Mapping[str, object],
) -> dict[str, object] | None:
    """在可变能力校验前重放同一公开请求的首次 202 快照。"""

    try:
        task = TaskService(session).find_idempotent_task(
            caller="narrato-api",
            route=route,
            idempotency_key=idempotency_key,
            idempotency_payload=dict(idempotency_payload),
        )
    except IdempotencyConflictError as exc:
        raise ApiError("IDEMPOTENCY_CONFLICT", "幂等键对应的请求体不同", 409) from exc
    if task is None:
        return None
    DispatchOutboxPublisher(session).publish_task(task.id, dispatcher)
    return envelope(
        request_id=request_id,
        code="TASK_CREATED",
        message="任务已创建",
        data=dict(task.initial_response),
    )
