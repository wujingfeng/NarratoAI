from __future__ import annotations

from core_api.tasks.models import CoreTaskAttempt
from core_api.tasks.service import TaskService


def acquire_lease(
    service: TaskService, task_id: str, *, lease_seconds: float = 60
) -> CoreTaskAttempt:
    """从可领取状态原子创建带版本的 Worker 租约。"""

    return service.acquire_lease(task_id, lease_seconds=lease_seconds)


def heartbeat(
    service: TaskService,
    attempt_id: str,
    lease_token: str,
    lease_version: int,
    *,
    lease_seconds: float = 60,
) -> CoreTaskAttempt:
    """校验 current 租约并延长有效期。"""

    return service.heartbeat(
        attempt_id,
        lease_token,
        lease_version,
        lease_seconds=lease_seconds,
    )
