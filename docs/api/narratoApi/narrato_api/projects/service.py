from __future__ import annotations

from collections.abc import Iterable
from typing import TypeVar


Artifact = TypeVar("Artifact")


class ProjectStateConflict(ValueError):
    """项目状态不满足当前操作前置条件时抛出。"""

    code = "PROJECT_NOT_TERMINAL"


_DELETABLE_PROJECT_STATES = frozenset({"completed", "failed"})
_ARTIFACT_VISIBLE_PROJECT_STATES = frozenset({"completed"})
_EXPORTABLE_PROJECT_STATES = frozenset({"completed"})


def ensure_project_deletable(status: str) -> None:
    """只校验终态项目是否具备删除资格，不执行删除。"""

    if status not in _DELETABLE_PROJECT_STATES:
        raise ProjectStateConflict("project must be completed or failed before deletion")


def ensure_project_exportable(status: str) -> None:
    """只校验项目是否具备导出资格，不执行导出。"""

    if status not in _EXPORTABLE_PROJECT_STATES:
        conflict = ProjectStateConflict("project must be completed before export")
        conflict.code = "PROJECT_NOT_COMPLETED"
        raise conflict


def visible_artifacts(status: str, artifacts: Iterable[Artifact]) -> list[Artifact]:
    """仅让已完成项目展示已登记的可导出产物。"""

    # 失败项目可能遗留中间文件，但不能向用户暴露任何产物。
    if status not in _ARTIFACT_VISIBLE_PROJECT_STATES:
        return []
    return list(artifacts)
