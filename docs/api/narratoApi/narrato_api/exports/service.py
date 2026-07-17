from __future__ import annotations

from collections.abc import Iterable
from hashlib import sha256
from typing import TypedDict

from narrato_api.artifacts.models import RegisteredArtifact


class JianyingResource(TypedDict):
    """前端流式 ZIP 所需的单个远程资源描述。"""

    artifact_id: str
    cdn_url: str
    zip_path: str


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
        directory, extension = _KIND_DESTINATIONS.get(artifact.kind, _DEFAULT_DESTINATION)
        digest = sha256(artifact.id.encode("utf-8")).hexdigest()[:32]
        resources.append(
            {
                "artifact_id": artifact.id,
                "cdn_url": artifact.cdn_url,
                "zip_path": f"{directory}/{digest}{extension}",
            }
        )

    return {"package_name": "jianying-export.zip", "resources": resources}
