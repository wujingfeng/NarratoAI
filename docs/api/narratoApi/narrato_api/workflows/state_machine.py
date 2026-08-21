from __future__ import annotations


class StateTransitionError(ValueError):
    """表示调用方请求了不允许的工作流状态操作。"""


_TERMINAL_STATES = frozenset({"completed", "failed", "cancelled"})
_ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    "draft": frozenset({"queued"}),
    "queued": frozenset({"running", "failed", "cancelled"}),
    "running": frozenset({"waiting_for_edit", "completed", "failed", "cancelled"}),
    "waiting_for_edit": frozenset({"waiting_for_edit", "render_queued"}),
    "render_queued": frozenset({"running", "failed", "cancelled"}),
    "completed": frozenset(),
    "failed": frozenset(),
}


def transition_workflow_state(current: str, target: str, *, actor: str) -> bool:
    """判断工作流是否可由指定调用方转换至目标状态。"""
    if actor == "user" and target == "cancelled":
        raise StateTransitionError("用户不支持 cancel 工作流")
    if actor == "user" and current == "failed" and target == "running":
        raise StateTransitionError("用户不支持手动 retry 工作流")
    if current in _TERMINAL_STATES:
        return False
    return target in _ALLOWED_TRANSITIONS.get(current, frozenset())


def is_automatic_retry_candidate(
    *, node_state: str, retryable: bool, attempt_count: int, max_attempts: int
) -> bool:
    """仅判断失败节点是否具备自动重试候选资格，不执行调度。"""
    return (
        node_state == "failed"
        and retryable
        and attempt_count >= 0
        and max_attempts > attempt_count
    )
