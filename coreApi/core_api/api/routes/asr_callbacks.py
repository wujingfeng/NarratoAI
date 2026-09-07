from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path
from sqlalchemy.orm import Session

from core_api.api.dependencies import get_database_session, get_request_id
from core_api.api.errors import ApiError
from core_api.api.responses import envelope
from core_api.tasks.asr_jobs import AsrProviderJobStore

router = APIRouter()


@router.post("/callbacks/{callback_key}")
def receive_volcengine_asr_callback(
    payload: dict[str, Any],
    callback_key: Annotated[str, Path(min_length=32, max_length=128)],
    session: Annotated[Session, Depends(get_database_session)],
    request_id: Annotated[str, Depends(get_request_id)],
) -> dict[str, object]:
    """幂等保存火山结果；Worker 同步轮询会消费同一持久化结果。"""

    response = payload.get("resp")
    provider_task_id = response.get("id") if isinstance(response, dict) else None
    if not isinstance(provider_task_id, str) or not provider_task_id:
        raise ApiError("ASR_CALLBACK_INVALID", "ASR 回调缺少任务标识", 422)
    bind = session.get_bind()
    store = AsrProviderJobStore(lambda: Session(bind, expire_on_commit=False))
    row = store.record_callback(
        callback_key, payload=payload, provider_task_id=provider_task_id
    )
    if row is None:
        raise ApiError("ASR_CALLBACK_NOT_FOUND", "ASR 回调任务不存在", 404)
    return envelope(
        request_id=request_id,
        code="ASR_CALLBACK_ACCEPTED",
        message="ASR callback accepted",
        data={"status": row.status},
    )
