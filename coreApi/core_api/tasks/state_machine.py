from __future__ import annotations

from core_api.tasks.models import CoreTaskStatus

_ALLOWED_TRANSITIONS: dict[CoreTaskStatus, frozenset[CoreTaskStatus]] = {
    CoreTaskStatus.QUEUED: frozenset(
        {CoreTaskStatus.RUNNING, CoreTaskStatus.SUCCEEDED, CoreTaskStatus.FAILED}
    ),
    CoreTaskStatus.RUNNING: frozenset(
        {
            CoreTaskStatus.RETRY_WAIT,
            CoreTaskStatus.SUCCEEDED,
            CoreTaskStatus.FAILED,
        }
    ),
    CoreTaskStatus.RETRY_WAIT: frozenset(
        {CoreTaskStatus.RUNNING, CoreTaskStatus.FAILED}
    ),
    CoreTaskStatus.SUCCEEDED: frozenset(),
    CoreTaskStatus.FAILED: frozenset(),
}


def can_transition(current: CoreTaskStatus, target: CoreTaskStatus) -> bool:
    """判断 Core Task 状态迁移是否合法。"""

    return target in _ALLOWED_TRANSITIONS[current]


def is_terminal(status: CoreTaskStatus) -> bool:
    """判断状态是否为不可逆终态。"""

    return status in {CoreTaskStatus.SUCCEEDED, CoreTaskStatus.FAILED}
