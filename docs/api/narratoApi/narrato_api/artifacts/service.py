from __future__ import annotations

from sqlalchemy.orm import Session

from narrato_api.artifacts.models import RegisteredArtifact


def register_artifact(
    session: Session,
    *,
    artifact_id: str,
    project_id: str,
    kind: str,
    cdn_url: str,
) -> RegisteredArtifact:
    """将项目归属的产物加入调用方已管理的数据库事务。"""

    artifact = RegisteredArtifact(
        id=artifact_id,
        project_id=project_id,
        kind=kind,
        cdn_url=cdn_url,
    )
    session.add(artifact)
    return artifact
