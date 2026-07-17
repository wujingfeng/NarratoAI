from __future__ import annotations

from collections.abc import Iterable
from hashlib import sha256
from typing import Any, NotRequired, Protocol, TypedDict

from sqlalchemy import select
from sqlalchemy.orm import Session

from narrato_api.artifacts.models import RegisteredArtifact
from narrato_api.editor.models import EditorRevision
from narrato_api.integrations.core_client import (
    CoreJianyingManifest,
    CoreJianyingResource,
)
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


class JianyingManifestSnapshotNotFoundError(LookupError):
    """已完成项目没有可用于剪映导出的不可变编辑快照。"""

    code = "JIANYING_SNAPSHOT_NOT_FOUND"


class JianyingManifestCoreClient(Protocol):
    def build_jianying_manifest(
        self,
        *,
        snapshot_id: str,
        timeline: list[dict[str, Any]],
        resources: list[CoreJianyingResource],
    ) -> CoreJianyingManifest: ...


_KIND_DESTINATIONS: dict[str, tuple[str, str]] = {
    "audio": ("audio", ".mp3"),
    "script": ("script", ".json"),
    "subtitle": ("subtitle", ".srt"),
    "timeline": ("timeline", ".json"),
    "video": ("video", ".mp4"),
}
_DEFAULT_DESTINATION = ("resource", ".bin")
_CORE_KIND_ALIASES = {"audio": "voice", "script": "timeline"}
_CORE_DESTINATIONS = {
    "subtitle": ("assets/subtitle", ".srt"),
    "timeline": ("assets/timeline", ".json"),
    "video": ("assets/video", ".mp4"),
    "voice": ("assets/voice", ".wav"),
}


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
    session: Session,
    *,
    user_id: str,
    project_id: str,
    core_client: JianyingManifestCoreClient,
) -> CoreJianyingManifest:
    """为当前用户完成项目调用 Core 生成无状态剪映 Manifest。"""

    result = lookup_completed_project_result(
        session, user_id=user_id, project_id=project_id
    )
    revision = session.scalar(
        select(EditorRevision)
        .where(EditorRevision.project_id == result.project_id)
        .order_by(EditorRevision.created_at.desc(), EditorRevision.id.desc())
    )
    if revision is None:
        raise JianyingManifestSnapshotNotFoundError("editor revision was not found")
    timeline = revision.content.get("timeline")
    if not isinstance(timeline, list):
        raise JianyingManifestSnapshotNotFoundError(
            "editor revision timeline was not found"
        )
    resources = build_jianying_manifest(result.artifacts)["resources"]
    core_resources: list[CoreJianyingResource] = []
    for resource, artifact in zip(
        resources, sorted(result.artifacts, key=lambda item: item.id)
    ):
        if not all(key in resource for key in ("size", "checksum", "content_type")):
            raise ValueError("registered artifact Core metadata is incomplete")
        core_kind = _CORE_KIND_ALIASES.get(artifact.kind, artifact.kind)
        core_directory, core_extension = _CORE_DESTINATIONS.get(
            core_kind, ("resource", ".bin")
        )
        digest = sha256(artifact.id.encode("utf-8")).hexdigest()[:32]
        core_resources.append(
            CoreJianyingResource(
                kind=core_kind,
                zip_path=f"{core_directory}/{digest}{core_extension}",
                url=resource["cdn_url"],
                size=resource["size"],
                checksum=resource["checksum"],
                content_type=resource["content_type"],
                width=resource.get("width"),
                height=resource.get("height"),
                duration=resource.get("duration"),
            )
        )
    return core_client.build_jianying_manifest(
        snapshot_id=revision.id, timeline=timeline, resources=core_resources
    )
