from __future__ import annotations

from collections.abc import Iterable
from hashlib import sha256
from typing import NotRequired, TypedDict

from sqlalchemy.orm import Session

from narrato_api.artifacts.models import RegisteredArtifact
from narrato_api.projects.service import lookup_completed_project_result


class JianyingResource(TypedDict):
    """前端流式 ZIP 所需的单个远程资源描述。"""

    artifact_id: str
    cdn_url: str
    zip_path: str
    size: NotRequired[int]
    checksum: NotRequired[str]
    content_type: NotRequired[str]
    width: NotRequired[int]
    height: NotRequired[int]
    duration: NotRequired[float]


class JianyingManifest(TypedDict):
    """剪映客户端组包所需的纯数据清单。"""

    package_name: str
    resources: list[JianyingResource]


_KIND_DESTINATIONS: dict[str, tuple[str, str]] = {
    "audio": ("audio", ".mp3"),
    "script": ("script", ".json"),
    "subtitle": ("subtitle", ".srt"),
    "timeline": ("timeline", ".json"),
    "video": ("video", ".mp4"),
}
_DEFAULT_DESTINATION = ("resource", ".bin")


def build_jianying_manifest(
    artifacts: Iterable[RegisteredArtifact],
) -> JianyingManifest:
    """将显式登记的产物映射为稳定、无副作用的剪映资源清单。"""

    resources: list[JianyingResource] = []
    for artifact in sorted(artifacts, key=lambda item: item.id):
        directory, extension = _KIND_DESTINATIONS.get(
            artifact.kind, _DEFAULT_DESTINATION
        )
        digest = sha256(artifact.id.encode("utf-8")).hexdigest()[:32]
        resource: JianyingResource = {
            "artifact_id": artifact.id,
            "cdn_url": artifact.cdn_url,
            "zip_path": f"{directory}/{digest}{extension}",
        }
        for field in ("size", "checksum", "content_type"):
            value = getattr(artifact, field)
            if value is not None:
                resource[field] = value
        for field in ("width", "height", "duration"):
            value = getattr(artifact, field)
            if value is not None:
                resource[field] = value
        resources.append(resource)

    return {"package_name": "jianying-export.zip", "resources": resources}


def build_owned_completed_project_jianying_manifest(
    session: Session, *, user_id: str, project_id: str
) -> JianyingManifest:
    """返回当前用户已完成项目的剪映资源清单。"""

    result = lookup_completed_project_result(
        session, user_id=user_id, project_id=project_id
    )
    return build_jianying_manifest(result.artifacts)
