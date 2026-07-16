"""统一的 FFprobe 媒体元数据探测服务。"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path


class MediaProbeError(RuntimeError):
    """表示媒体文件无法被 FFprobe 正确探测。"""


@dataclass(frozen=True, slots=True)
class MediaInfo:
    """表示经过归一化的媒体元数据。"""

    duration_seconds: float
    container: str
    video_codec: str | None
    audio_codec: str | None
    width: int | None
    height: int | None
    has_video: bool
    has_audio: bool


def _ffprobe_binary() -> str:
    """返回当前环境配置的 FFprobe 可执行文件。"""

    for env_name in ("NARRATO_FFPROBE_EXE", "IMAGEIO_FFPROBE_EXE"):
        candidate = os.environ.get(env_name, "").strip()
        if candidate and os.path.isfile(candidate):
            return candidate
    for env_name in ("NARRATO_FFMPEG_EXE", "IMAGEIO_FFMPEG_EXE"):
        ffmpeg_candidate = os.environ.get(env_name, "").strip()
        sibling = os.path.join(os.path.dirname(ffmpeg_candidate), "ffprobe")
        if ffmpeg_candidate and os.path.isfile(sibling):
            return sibling
    try:
        import imageio_ffmpeg

        ffmpeg_candidate = imageio_ffmpeg.get_ffmpeg_exe()
        sibling = os.path.join(os.path.dirname(ffmpeg_candidate), "ffprobe")
        if ffmpeg_candidate and os.path.isfile(sibling):
            return sibling
    except Exception:
        # 自动发现失败时保持旧逻辑，继续使用 PATH 中的 ffprobe。
        pass
    return "ffprobe"


def _normalize_container(format_name: object, path: str) -> str:
    """将 FFprobe 的复合容器名归一化为稳定短名称。"""

    names = [part.strip().lower() for part in str(format_name or "").split(",") if part.strip()]
    suffix = Path(path).suffix.lower().lstrip(".")
    aliases = {"m4v": "mp4", "m4a": "mp4", "qt": "mov", "matroska": "mkv"}

    # MP4 的 FFprobe format_name 通常是复合列表，优先使用可识别的文件后缀。
    if suffix in names or (suffix == "mp4" and "mp4" in names):
        return aliases.get(suffix, suffix)
    if "mp4" in names:
        return "mp4"
    if "mov" in names:
        return "mov"
    return aliases.get(names[0], names[0]) if names else suffix


def _positive_float(value: object) -> float:
    """将 FFprobe 数值转换为非负浮点数。"""

    try:
        return max(0.0, float(value or 0))
    except (TypeError, ValueError):
        return 0.0


def probe_media(path: str) -> MediaInfo:
    """使用 FFprobe 返回统一媒体元数据，探测失败时抛出 MediaProbeError。"""

    normalized_path = os.path.abspath(str(path or "").strip())
    if not path or not os.path.isfile(normalized_path):
        raise MediaProbeError(f"媒体文件不存在: {path}")

    try:
        result = subprocess.run(
            [
                _ffprobe_binary(),
                "-v",
                "error",
                "-print_format",
                "json",
                "-show_streams",
                "-show_format",
                normalized_path,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise MediaProbeError(f"FFprobe 执行失败: {exc}") from exc

    if result.returncode != 0:
        detail = result.stderr.strip() or "未知错误"
        raise MediaProbeError(f"FFprobe 探测失败: {detail}")

    try:
        payload = json.loads(result.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise MediaProbeError("FFprobe 返回了无效 JSON") from exc

    try:
        if not isinstance(payload, dict):
            raise TypeError("根节点不是对象")
        raw_streams = payload.get("streams", [])
        raw_format = payload.get("format", {})
        if not isinstance(raw_streams, list) or not all(isinstance(stream, dict) for stream in raw_streams):
            raise TypeError("streams 不是对象数组")
        if not isinstance(raw_format, dict):
            raise TypeError("format 不是对象")

        streams = raw_streams
        format_data = raw_format
        video_stream = next((stream for stream in streams if stream.get("codec_type") == "video"), None)
        audio_stream = next((stream for stream in streams if stream.get("codec_type") == "audio"), None)
        duration = _positive_float(format_data.get("duration"))
        if duration <= 0:
            duration = max((_positive_float(stream.get("duration")) for stream in streams), default=0.0)
        width = int(video_stream["width"]) if video_stream and video_stream.get("width") else None
        height = int(video_stream["height"]) if video_stream and video_stream.get("height") else None
    except (AttributeError, TypeError, ValueError) as exc:
        raise MediaProbeError(f"FFprobe 返回结构无效: {exc}") from exc
    if duration <= 0:
        raise MediaProbeError("FFprobe 未获取到有效媒体时长")

    return MediaInfo(
        duration_seconds=duration,
        container=_normalize_container(format_data.get("format_name"), normalized_path),
        video_codec=video_stream.get("codec_name") if video_stream else None,
        audio_codec=audio_stream.get("codec_name") if audio_stream else None,
        width=width,
        height=height,
        has_video=video_stream is not None,
        has_audio=audio_stream is not None,
    )
