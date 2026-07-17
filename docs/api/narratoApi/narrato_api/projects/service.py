from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import TypeVar

from sqlalchemy import select
from sqlalchemy.orm import Session

from narrato_api.artifacts.models import RegisteredArtifact
from narrato_api.artifacts.service import list_registered_artifacts
from narrato_api.projects.models import Project


Artifact = TypeVar("Artifact")


class ProjectStateConflict(ValueError):
    """项目状态不满足当前操作前置条件时抛出。"""

    code = "PROJECT_NOT_TERMINAL"


class ProjectResultLookupError(LookupError):
    """项目结果不存在、非归属或尚不可读取时抛出。"""

    code = "PROJECT_RESULT_NOT_FOUND"


@dataclass(frozen=True)
class CompletedProjectResult:
    """已完成项目的最小结果记录。"""

    project_id: str
    artifacts: tuple[RegisteredArtifact, ...]


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


def lookup_completed_project_result(
    session: Session, *, user_id: str, project_id: str
) -> CompletedProjectResult:
    """读取当前用户的已完成项目及其已登记产物。"""

    statement = select(Project).where(
        Project.id == project_id,
        Project.user_id == user_id,
    )
    project = session.scalar(statement)
    if project is None:
        raise ProjectResultLookupError("project result was not found")
    if project.status != "completed":
        error = ProjectResultLookupError("project result is not completed")
        error.code = "PROJECT_RESULT_NOT_COMPLETED"
        raise error

    return CompletedProjectResult(
        project_id=project.id,
        artifacts=tuple(list_registered_artifacts(session, project=project)),
    )
