from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable, Protocol

from core_api.infrastructure.oss_client import Downloader
from core_api.runtime.workspace import CoreTaskWorkspace


VIDEO_MAX_BYTES = 300 * 1024 * 1024
SRT_MAX_BYTES = 5 * 1024 * 1024
VIDEO_EXTENSIONS = frozenset({"mp4", "mov", "avi"})


class AdapterError(RuntimeError):
    """原子能力适配器可分类错误的基类。"""

    code = "ADAPTER_ERROR"
    retryable = False


class MediaConstraintError(AdapterError):
    """视频真实容器、流或时长不符合产品约束。"""

    code = "MEDIA_INVALID"


class MediaDamagedError(AdapterError):
    """视频无法被探测或文件已经损坏。"""

    code = "MEDIA_DAMAGED"


class SrtConstraintError(AdapterError):
    """SRT 编码、cue 或时间轴不合法。"""

    code = "SRT_INVALID"


class ProbeResult(Protocol):
    """既有 FFprobe 服务返回值的稳定最小接口。"""

    duration_seconds: float
    container: str
    video_codec: str | None
    audio_codec: str | None
    width: int | None
    height: int | None
    has_video: bool
    has_audio: bool


def _extension(value: str, *, video_only: bool = False) -> str:
    raw = str(value or "").strip()
    if raw.startswith("."):
        raw = raw[1:]
    normalized = raw.lower()
    allowed = VIDEO_EXTENSIONS if video_only else VIDEO_EXTENSIONS | {"srt"}
    if normalized not in allowed or any(char in raw for char in ("/", "\\", "%", ".")):
        raise MediaConstraintError("MEDIA_EXTENSION_UNSUPPORTED")
    return normalized


def validate_video(probe: ProbeResult, *, declared_extension: str) -> dict[str, Any]:
    """校验 10 分钟上限、真实视频流和容器并返回统一元数据。"""

    extension = _extension(declared_extension, video_only=True)
    duration = float(probe.duration_seconds)
    if duration > 600.0:
        raise MediaConstraintError("MEDIA_TOO_LONG")
    if duration <= 0:
        raise MediaConstraintError("MEDIA_DURATION_INVALID")
    if (
        not probe.has_video
        or not probe.video_codec
        or not probe.width
        or not probe.height
        or int(probe.width) <= 0
        or int(probe.height) <= 0
    ):
        raise MediaConstraintError("MEDIA_VIDEO_STREAM_INVALID")
    container = str(probe.container or "").lower()
    if container != extension:
        raise MediaConstraintError("MEDIA_CONTAINER_MISMATCH")
    return {
        "media_type": "video",
        "duration_seconds": duration,
        "container": container,
        "video_codec": str(probe.video_codec),
        "audio_codec": str(probe.audio_codec) if probe.audio_codec else None,
        "width": int(probe.width),
        "height": int(probe.height),
        "has_audio": bool(probe.has_audio),
    }


_TIMESTAMP = re.compile(
    r"^(?P<hours>\d{2}):(?P<minutes>[0-5]\d):(?P<seconds>[0-5]\d)[,.](?P<millis>\d{3})$"
)


def _seconds(value: str) -> float:
    match = _TIMESTAMP.fullmatch(value.strip())
    if not match:
        raise SrtConstraintError("SRT_TIMESTAMP_INVALID")
    return (
        int(match["hours"]) * 3600
        + int(match["minutes"]) * 60
        + int(match["seconds"])
        + int(match["millis"]) / 1000
    )


def _decode_srt(content: bytes) -> tuple[str, str]:
    for encoding in ("utf-8-sig", "utf-16", "gb18030"):
        try:
            text = content.decode(encoding)
        except UnicodeError:
            continue
        if "\x00" not in text:
            return text, "utf-8" if encoding == "utf-8-sig" else encoding
    raise SrtConstraintError("SRT_ENCODING_INVALID")


def parse_srt(content: bytes) -> dict[str, Any]:
    """解析 SRT 并确定 cue 非空、时间轴有序且不重叠。"""

    if not content or len(content) > SRT_MAX_BYTES:
        raise SrtConstraintError("SRT_SIZE_INVALID")
    text, encoding = _decode_srt(content)
    blocks = [
        block for block in re.split(r"\r?\n\s*\r?\n", text.strip()) if block.strip()
    ]
    if not blocks:
        raise SrtConstraintError("SRT_EMPTY")
    previous_end = 0.0
    expected_index = 1
    last_end = 0.0
    for block in blocks:
        lines = block.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        if len(lines) < 3:
            raise SrtConstraintError("SRT_CUE_INVALID")
        try:
            index = int(lines[0].strip())
        except ValueError as exc:
            raise SrtConstraintError("SRT_INDEX_INVALID") from exc
        if index != expected_index:
            raise SrtConstraintError("SRT_INDEX_INVALID")
        expected_index += 1
        parts = [part.strip() for part in lines[1].split("-->")]
        if len(parts) != 2:
            raise SrtConstraintError("SRT_TIMESTAMP_INVALID")
        start, end = _seconds(parts[0]), _seconds(parts[1].split()[0])
        if start < 0 or end <= start or start < previous_end:
            raise SrtConstraintError("SRT_TIMELINE_INVALID")
        if not any(line.strip() for line in lines[2:]):
            raise SrtConstraintError("SRT_TEXT_EMPTY")
        previous_end = end
        last_end = end
    return {
        "media_type": "subtitle",
        "cue_count": len(blocks),
        "duration_seconds": last_end,
        "encoding": encoding,
    }


@dataclass(slots=True)
class MediaProbeAdapter:
    """远程探测视频元数据，并依据已复核声明接收 SRT。"""

    downloader: Downloader
    probe: Callable[[str], ProbeResult]

    def run(
        self,
        *,
        source_url: str,
        media_type: str,
        declared_extension: str,
        workspace: CoreTaskWorkspace,
    ) -> dict[str, Any]:
        """执行媒体探测且不上传输入副本。"""

        if media_type == "video":
            extension = _extension(declared_extension, video_only=True)
        elif media_type == "subtitle":
            extension = _extension(declared_extension)
            if extension != "srt":
                raise SrtConstraintError("SRT_EXTENSION_INVALID")
        else:
            raise MediaConstraintError("MEDIA_TYPE_INVALID")
        if media_type == "video":
            try:
                probe_result = self.probe(source_url)
            except Exception as exc:
                # FFprobe 详情可能含远程 URL 或内部信息，只保留稳定损坏分类。
                raise MediaDamagedError("MEDIA_DAMAGED") from exc
            return validate_video(probe_result, declared_extension=extension)

        # 上传确认已经通过对象大小、类型、扩展名和归属复核；SRT 内容在后续实际
        # 使用字幕的处理节点读取，探测阶段不再创建本地副本。
        return {"media_type": "subtitle"}
