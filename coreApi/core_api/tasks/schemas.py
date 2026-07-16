from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from core_api.tasks.models import CoreTaskStatus


class CoreTaskCreate(BaseModel):
    """创建 Core 原子任务所需的不可变输入。"""

    caller: str = Field(min_length=1, max_length=120)
    route: str = Field(min_length=1, max_length=255)
    task_type: str = Field(min_length=1, max_length=80)
    idempotency_key: str = Field(min_length=1, max_length=255)
    input_snapshot: dict[str, Any]
    caller_task_id: str | None = None
    max_retries: int = Field(default=3, ge=0, le=20)


class CoreTaskView(BaseModel):
    """跨服务返回的 Core Task 状态快照。"""

    model_config = ConfigDict(from_attributes=True)

    id: str
    task_type: str
    caller_task_id: str | None
    status: CoreTaskStatus
    phase: str | None
    progress: int
    state_version: int
    current_attempt_no: int
    result: list[dict[str, Any]] | dict[str, Any] | None
    error: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime
