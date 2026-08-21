from __future__ import annotations

from collections.abc import Iterable, Mapping
from hashlib import sha256
from typing import Any, NotRequired, Protocol, TypedDict, cast

from sqlalchemy import select
from sqlalchemy.orm import Session

from narrato_api.artifacts.models import RegisteredArtifact
from narrato_api.editor.models import EditorRevision
from narrato_api.integrations.core_client import (
    CoreJianyingManifest,
    CoreJianyingResource,
)
from narrato_api.projects.service import lookup_completed_project_result
from narrato_api.workflows.models import Workflow, WorkflowNode, WorkflowNodeAttempt


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


def _result_containers(result: object) -> list[Mapping[str, object]]:
    """兼容 Core 终态在回调和轮询路径中的一层包装差异。"""

    if not isinstance(result, Mapping):
        return []
    containers = [result]
    nested = result.get("result")
    if isinstance(nested, Mapping):
        containers.append(nested)
    return containers


def _load_final_render_snapshot(
    session: Session,
    *,
    project_id: str,
    revision: EditorRevision,
) -> tuple[list[dict[str, Any]], dict[str, object]]:
    """读取与 Revision 对应的最终成片时间轴，而不是原素材裁剪时间。"""

    attempts = session.scalars(
        select(WorkflowNodeAttempt)
        .join(WorkflowNode, WorkflowNode.id == WorkflowNodeAttempt.workflow_node_id)
        .join(Workflow, Workflow.id == WorkflowNode.workflow_id)
        .where(
            Workflow.project_id == project_id,
            WorkflowNode.name == "video_render",
            WorkflowNodeAttempt.state == "completed",
        )
        .order_by(
            WorkflowNodeAttempt.completed_at.desc(),
            WorkflowNodeAttempt.attempt_number.desc(),
        )
    )
    for attempt in attempts:
        for container in _result_containers(attempt.result):
            metadata = container.get("metadata")
            if not isinstance(metadata, Mapping) or metadata.get("snapshot_id") != revision.id:
                continue
            snapshot = metadata.get("jianying_snapshot")
            if not isinstance(snapshot, Mapping):
                continue
            timeline = snapshot.get("timeline")
            video = snapshot.get("video")
            if (
                isinstance(timeline, list)
                and all(isinstance(item, Mapping) for item in timeline)
                and isinstance(video, Mapping)
                and type(video.get("width")) is int
                and type(video.get("height")) is int
                and type(video.get("duration")) in (int, float)
            ):
                return [dict(item) for item in timeline], dict(video)

    # 兼容早期已经把最终时间轴直接冻结到 Revision 顶层的历史数据。
    legacy_timeline = revision.content.get("timeline")
    if isinstance(legacy_timeline, list) and all(
        isinstance(item, Mapping) for item in legacy_timeline
    ):
        return [dict(item) for item in legacy_timeline], {}
    raise JianyingManifestSnapshotNotFoundError(
        "final render snapshot was not found"
    )


def _canonical_content_type(value: object) -> str:
    """资源协议比较 MIME 主类型，忽略合法的 charset 等参数。"""

    if not isinstance(value, str):
        return ""
    return value.partition(";")[0].strip().lower()


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
                cast(dict[str, Any], resource)[field] = value
        for field in ("width", "height", "duration"):
            value = getattr(artifact, field)
            if value is not None:
                cast(dict[str, Any], resource)[field] = value
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
    timeline, video_metadata = _load_final_render_snapshot(
        session,
        project_id=result.project_id,
        revision=revision,
    )
    resources = build_jianying_manifest(result.artifacts)["resources"]
    core_resources: list[CoreJianyingResource] = []
    for resource, artifact in zip(
        resources, sorted(result.artifacts, key=lambda item: item.id)
    ):
        if not all(key in resource for key in ("size", "checksum", "content_type")):
            raise JianyingManifestSnapshotNotFoundError(
                "registered artifact Core metadata is incomplete"
            )
        core_kind = _CORE_KIND_ALIASES.get(artifact.kind, artifact.kind)
        core_directory, core_extension = _CORE_DESTINATIONS.get(
            core_kind, ("resource", ".bin")
        )
        digest = sha256(artifact.id.encode("utf-8")).hexdigest()[:32]
        width = resource.get("width")
        height = resource.get("height")
        duration = resource.get("duration")
        if core_kind == "video":
            width = width if width is not None else video_metadata.get("width")
            height = height if height is not None else video_metadata.get("height")
            duration = duration if duration is not None else video_metadata.get("duration")
            if (
                type(width) is not int
                or type(height) is not int
                or type(duration) not in (int, float)
            ):
                raise JianyingManifestSnapshotNotFoundError(
                    "rendered video metadata is incomplete"
                )
        core_resources.append(
            CoreJianyingResource(
                kind=core_kind,
                zip_path=f"{core_directory}/{digest}{core_extension}",
                url=resource["cdn_url"],
                size=resource["size"],
                checksum=resource["checksum"],
                content_type=_canonical_content_type(resource["content_type"]),
                width=cast(int | None, width),
                height=cast(int | None, height),
                duration=cast(float | None, duration),
            )
        )
    return core_client.build_jianying_manifest(
        snapshot_id=revision.id, timeline=timeline, resources=core_resources
    )
