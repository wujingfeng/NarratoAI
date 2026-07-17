from __future__ import annotations


class ProjectStateConflict(ValueError):
    """项目状态不满足当前操作前置条件时抛出。"""

    code = "PROJECT_NOT_TERMINAL"


_DELETABLE_PROJECT_STATES = frozenset({"completed", "failed"})


def ensure_project_deletable(status: str) -> None:
    """只校验终态项目是否具备删除资格，不执行删除。"""

    if status not in _DELETABLE_PROJECT_STATES:
        raise ProjectStateConflict("project must be completed or failed before deletion")
