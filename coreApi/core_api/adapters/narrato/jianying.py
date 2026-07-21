from __future__ import annotations

from core_api.type_coercion import as_float, as_int

import base64
import json
import math
import posixpath
import re
from dataclasses import asdict, dataclass
from typing import Mapping, Sequence
from urllib.parse import urlsplit

from core_api.adapters.narrato.media_probe import AdapterError
from core_api.adapters.narrato.jianying_template import build_jianying_template_files

SHA256_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
JIANYING_TEMPLATE_VERSION = "10.6.0"
INLINE_MAX_BYTES = 5 * 1024 * 1024
RESOURCE_RULES = {
    "video": ("assets/video/", ".mp4", "video/mp4"),
    "subtitle": ("assets/subtitle/", ".srt", "application/x-subrip"),
    "voice": ("assets/voice/", ".wav", "audio/wav"),
    "timeline": ("assets/timeline/", ".json", "application/json"),
}


class JianyingInputError(AdapterError):
    """剪映基础文件或资源映射不符合安全 Manifest 协议。"""

    code = "JIANYING_MANIFEST_INVALID"


@dataclass(frozen=True, slots=True)
class ManifestFile:
    """一个由前端按 zip_path 流式写入的 Manifest 文件。"""

    zip_path: str
    content: str | None = None
    content_base64: str | None = None
    url: str | None = None
    size: int | None = None
    checksum: str | None = None
    content_type: str | None = None


@dataclass(frozen=True, slots=True)
class JianyingManifest:
    """不包含 ZIP bytes 的无状态剪映组包说明。"""

    template_version: str
    package_name: str
    files: tuple[ManifestFile, ...]

    def to_dict(self) -> dict[str, object]:
        """序列化为稳定 HTTP DTO。"""
        return {
            "template_version": self.template_version,
            "package_name": self.package_name,
            "files": [asdict(item) for item in self.files],
        }


def _zip_path(value: str) -> str:
    """返回规范 POSIX ZIP 路径并拒绝任何路径穿越。"""

    if (
        not value
        or "\\" in value
        or value.startswith("/")
        or any(part in ("", ".", "..") for part in value.split("/"))
    ):
        raise JianyingInputError("JIANYING_ZIP_PATH_INVALID")
    normalized = posixpath.normpath(value)
    if normalized != value:
        raise JianyingInputError("JIANYING_ZIP_PATH_INVALID")
    return normalized


def _public_https(value: str) -> str:
    """拒绝带凭据、fragment、IP literal 或非 HTTPS 的资源。"""

    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.fragment
    ):
        raise JianyingInputError("JIANYING_RESOURCE_URL_INVALID")
    try:
        import ipaddress

        ipaddress.ip_address(parsed.hostname)
    except ValueError:
        return value
    raise JianyingInputError("JIANYING_RESOURCE_URL_INVALID")


class JianyingBuilder:
    """只在内存中组合基础内容与公开 CDN 资源映射。"""

    def build(
        self,
        *,
        snapshot_id: str,
        timeline: Sequence[Mapping[str, object]],
        resources: Sequence[Mapping[str, object]],
    ) -> JianyingManifest:
        """从不可变编辑快照生成受保护基础草稿和资源 Manifest。"""
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", snapshot_id):
            raise JianyingInputError("JIANYING_SNAPSHOT_INVALID")
        if not timeline or len(timeline) > 500 or len(resources) > 1_000:
            raise JianyingInputError("JIANYING_MANIFEST_TOO_LARGE")
        normalized_timeline: list[dict[str, object]] = []
        previous_end = 0.0
        for item in timeline:
            source_id, start, end, narration = (
                item.get("source_asset_id"),
                item.get("start"),
                item.get("end"),
                item.get("narration"),
            )
            if (
                not isinstance(source_id, str)
                or type(start) not in (int, float)
                or type(end) not in (int, float)
                or not math.isfinite(as_float(start))
                or not math.isfinite(as_float(end))
                or as_float(start) < 0
                or as_float(start) < previous_end
                or as_float(end) <= as_float(start)
                or not isinstance(narration, str)
                or not narration.strip()
            ):
                raise JianyingInputError("JIANYING_TIMELINE_INVALID")
            previous_end = as_float(end)
            normalized_timeline.append(
                {
                    "source_asset_id": source_id,
                    "start": as_float(start),
                    "end": as_float(end),
                    "narration": narration.strip(),
                }
            )
        resource_entries: list[dict[str, object]] = []
        files: list[ManifestFile] = []
        seen: set[str] = set()
        for item in resources:
            path = _zip_path(str(item.get("zip_path", "")))
            kind = item.get("kind")
            if (
                path in seen
                or type(item.get("size")) is not int
                or as_int(item["size"]) <= 0
                or kind not in {"video", "subtitle", "voice", "timeline"}
            ):
                raise JianyingInputError("JIANYING_MANIFEST_INVALID")
            checksum, content_type = item.get("checksum"), item.get("content_type")
            rule = RESOURCE_RULES.get(str(kind))
            if (
                rule is None
                or not isinstance(checksum, str)
                or SHA256_PATTERN.fullmatch(checksum) is None
                or not isinstance(content_type, str)
                or not content_type
                or "/" not in content_type
                or any(char.isspace() for char in content_type)
                or not path.startswith(rule[0])
                or not path.endswith(rule[1])
                or content_type != rule[2]
            ):
                raise JianyingInputError("JIANYING_MANIFEST_INVALID")
            seen.add(path)
            resource_entry: dict[str, object] = {"kind": kind, "zip_path": path}
            if kind == "video":
                width, height, duration = (
                    item.get("width"),
                    item.get("height"),
                    item.get("duration"),
                )
                if (
                    type(width) is not int
                    or type(height) is not int
                    or not 1 <= as_int(width) <= 16_384
                    or not 1 <= as_int(height) <= 16_384
                    or type(duration) not in (int, float)
                    or not math.isfinite(as_float(duration))
                    or as_float(duration) <= 0
                    or as_float(duration) + 0.02 < previous_end
                ):
                    raise JianyingInputError("JIANYING_VIDEO_METADATA_INVALID")
                resource_entry.update(
                    width=as_int(width),
                    height=as_int(height),
                    duration=as_float(duration),
                )
            elif any(
                item.get(key) is not None for key in ("width", "height", "duration")
            ):
                raise JianyingInputError("JIANYING_MANIFEST_INVALID")
            resource_entries.append(resource_entry)
            files.append(
                ManifestFile(
                    path,
                    url=_public_https(str(item.get("url", ""))),
                    size=as_int(item["size"]),
                    checksum=checksum,
                    content_type=content_type,
                )
            )
        required = {"video", "subtitle", "voice", "timeline"}
        if {str(item["kind"]) for item in resource_entries} != required:
            raise JianyingInputError("JIANYING_RESOURCES_INCOMPLETE")
        resource_paths = {
            str(item["kind"]): str(item["zip_path"]) for item in resource_entries
        }
        video_metadata = next(
            item for item in resource_entries if item["kind"] == "video"
        )
        base_payloads = build_jianying_template_files(
            snapshot_id, normalized_timeline, resource_paths, video_metadata
        )
        base_files: list[ManifestFile] = []
        for path, payload in base_payloads.items():
            if isinstance(payload, bytes):
                base_files.append(
                    ManifestFile(
                        path,
                        content_base64=base64.b64encode(payload).decode("ascii"),
                        content_type="image/jpeg",
                    )
                )
            else:
                base_files.append(
                    ManifestFile(path, content=payload, content_type="application/json")
                )
        inline_bytes = len(
            json.dumps(
                [asdict(item) for item in base_files],
                ensure_ascii=False,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
        )
        if inline_bytes > INLINE_MAX_BYTES:
            raise JianyingInputError("JIANYING_MANIFEST_TOO_LARGE")
        final_paths = [item.zip_path for item in base_files + files]
        if len(final_paths) != len(set(final_paths)):
            raise JianyingInputError("JIANYING_ZIP_PATH_CONFLICT")
        return JianyingManifest(
            JIANYING_TEMPLATE_VERSION,
            f"NarratoAI_{snapshot_id}.zip",
            tuple(base_files + files),
        )
