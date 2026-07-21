from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from narrato_api.artifacts.models import RegisteredArtifact
from narrato_api.projects.models import Project


def register_artifact(
    session: Session,
    *,
    artifact_id: str,
    project_id: str,
    kind: str,
    cdn_url: str,
    size: int | None = None,
    checksum: str | None = None,
    content_type: str | None = None,
    width: int | None = None,
    height: int | None = None,
    duration: float | None = None,
) -> RegisteredArtifact:
    """将项目归属的产物加入调用方已管理的数据库事务。"""

    artifact = RegisteredArtifact(
        id=artifact_id,
        project_id=project_id,
        kind=kind,
        cdn_url=cdn_url,
        size=size,
        checksum=checksum,
        content_type=content_type,
        width=width,
        height=height,
        duration=duration,
    )
    session.add(artifact)
    return artifact


def list_registered_artifacts(
    session: Session, *, project: Project
) -> list[RegisteredArtifact]:
    """返回已完成项目已登记产物的稳定排序结果。"""

    if project.status != "completed":
        return []

    statement = (
        select(RegisteredArtifact)
        .where(RegisteredArtifact.project_id == project.id)
        .order_by(RegisteredArtifact.created_at, RegisteredArtifact.id)
    )
    return list(session.scalars(statement))
