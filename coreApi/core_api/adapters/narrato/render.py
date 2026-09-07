from __future__ import annotations

from core_api.type_coercion import as_float, as_int

import json
import hashlib
import math
import re
import wave
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from PIL import Image, ImageDraw, ImageFont

from core_api.adapters.narrato.media_probe import (
    AdapterError,
    SRT_MAX_BYTES,
    VIDEO_MAX_BYTES,
    parse_srt,
)
from core_api.infrastructure.oss_client import Downloader
from core_api.runtime.artifact_store import ArtifactStore
from core_api.runtime.workspace import CoreTaskWorkspace
from core_api.runtime.process_runner import ProcessRunner
from core_api.adapters.narrato.tts import (
    TtsProvider,
    TtsSynthesisResult,
    TtsWordTimestamp,
    validate_wav,
)

JSON_MAX_BYTES = 5 * 1024 * 1024

_VIDEO_RATIOS = {
    "9:16": 9 / 16,
    "16:9": 16 / 9,
    "4:3": 4 / 3,
    "3:4": 3 / 4,
    "1:1": 1.0,
}


def _voice_anchor_offset(
    narration: str,
    anchor_text: object,
    words: Sequence[TtsWordTimestamp],
) -> float | None:
    """把文案锚点映射到火山 TTS 原生字级时间轴。"""

    if not isinstance(anchor_text, str) or not anchor_text.strip() or not words:
        return None
    normalized_anchor = re.sub(r"\s+", "", anchor_text)
    normalized_narration = re.sub(r"\s+", "", narration)
    anchor_char = normalized_narration.find(normalized_anchor)
    if (
        anchor_char < 0
        or normalized_narration.find(normalized_anchor, anchor_char + 1) >= 0
    ):
        return None
    word_text = ""
    word_starts: list[tuple[int, float]] = []
    for word in words:
        normalized_word = re.sub(r"\s+", "", word.word)
        if not normalized_word:
            continue
        word_starts.append((len(word_text), word.start_time))
        word_text += normalized_word
    occurrence = word_text.find(normalized_anchor)
    if (
        occurrence < 0
        or word_text.find(normalized_anchor, occurrence + 1) >= 0
    ):
        # 方舟偶尔会对数字/TN 做轻微归一化；按文案中的相对字符位置回退。
        return None
    return next(
        (start for index, start in reversed(word_starts) if index <= occurrence),
        None,
    )


@dataclass(frozen=True, slots=True)
class VideoContentRegion:
    x: int
    y: int
    width: int
    height: int


def _effective_video_content_region(
    canvas_width: int,
    canvas_height: int,
    source_width: int | None,
    source_height: int | None,
) -> VideoContentRegion:
    """返回 contain 缩放后真实画面区域，字幕不得绘制到黑边之外。"""

    if not source_width or not source_height:
        return VideoContentRegion(0, 0, canvas_width, canvas_height)
    scale = min(canvas_width / source_width, canvas_height / source_height)
    width = max(1, as_int(round(source_width * scale)))
    height = max(1, as_int(round(source_height * scale)))
    return VideoContentRegion(
        (canvas_width - width) // 2,
        (canvas_height - height) // 2,
        width,
        height,
    )


def _voice_separation_client_token(core_task_id: str) -> str:
    """生成不暴露内部路径且可跨 attempt 复用的稳定第三方幂等键。"""

    return f"narrato-{hashlib.sha256(core_task_id.encode()).hexdigest()[:48]}"


def _even(value: float) -> int:
    """FFmpeg yuv420p 的画布宽高必须是正偶数。"""

    return max(2, as_int(round(value / 2) * 2))


def _normalize_render_config(
    value: Mapping[str, object] | None,
    *,
    has_original_sound: bool = False,
) -> dict[str, object]:
    """冻结渲染端真正消费的配置，未知值回落到安全产品默认值。"""

    raw = dict(value or {})
    ratio = str(raw.get("video_ratio") or "original")
    if ratio not in {"original", *_VIDEO_RATIOS}:
        ratio = "original"
    position = raw.get("narration_subtitle_position")
    position = dict(position) if isinstance(position, Mapping) else {}
    y = position.get("y", 0.82)
    scale = position.get("font_scale", 0.9)
    y = as_float(y) if type(y) in (int, float) and math.isfinite(as_float(y)) else 0.82
    scale = (
        as_float(scale)
        if type(scale) in (int, float) and math.isfinite(as_float(scale))
        else 0.9
    )
    layouts: dict[str, dict[str, float]] = {}
    raw_layouts = raw.get("source_subtitle_layouts")
    if isinstance(raw_layouts, Mapping):
        for source_id, layout in raw_layouts.items():
            if not isinstance(source_id, str) or not isinstance(layout, Mapping):
                continue
            region = layout.get("region") if "region" in layout else layout
            if layout.get("status", "confirmed") != "confirmed" or not isinstance(
                region, Mapping
            ):
                continue
            try:
                normalized = {
                    key: as_float(region[key])
                    for key in ("x", "y", "width", "height")
                }
            except (KeyError, TypeError, ValueError):
                continue
            if (
                0 <= normalized["x"] <= 1
                and 0 <= normalized["y"] <= 1
                and 0 < normalized["width"] <= 1
                and 0 < normalized["height"] <= 1
                and normalized["x"] + normalized["width"] <= 1
                and normalized["y"] + normalized["height"] <= 1
            ):
                layouts[source_id] = normalized
    return {
        **raw,
        "video_ratio": ratio,
        "subtitle_style": str(raw.get("subtitle_style") or "经典白色"),
        "source_subtitle_layouts": layouts,
        "narration_subtitle_position": {
            "y": min(1.0, max(0.0, y)),
            "font_scale": min(1.5, max(0.7, scale)),
        },
        "original_sound_volume": as_int(
            raw.get("original_sound_volume", 100 if has_original_sound else 0)
        ),
    }


def _source_subtitle_blur_region(
    region: Mapping[str, object],
) -> tuple[float, float]:
    """返回原字幕遮挡区域的归一化纵向范围。"""

    return as_float(region["y"]), as_float(region["height"])


def _source_subtitle_blur_pixels(
    region: Mapping[str, object], width: int, height: int
) -> tuple[int, int, int, int]:
    """原字幕通常横跨整行；纵向严格使用已确认坐标。"""

    top, region_height = _source_subtitle_blur_region(region)
    y = max(0, min(height - 2, as_int(round(top * height))))
    h = max(2, min(height - y, as_int(round(region_height * height))))
    return 0, y, width, h


def _expanded_source_subtitle_blur_pixels(
    region: Mapping[str, object], width: int, height: int
) -> tuple[int, int, int, int]:
    """给检测框增加纵向安全边距，避免字形上下沿在遮罩外仍可辨认。"""

    x, y, w, h = _source_subtitle_blur_pixels(region, width, height)
    padding = max(
        as_int(round(height * 0.015)),
        min(as_int(round(h * 0.30)), as_int(round(height * 0.03))),
    )
    target_height = max(h + padding * 2, as_int(round(height * 0.08)))
    center = y + h / 2
    expanded_y = max(0, as_int(round(center - target_height / 2)))
    expanded_bottom = min(height, expanded_y + target_height)
    if expanded_bottom - expanded_y < target_height:
        expanded_y = max(0, expanded_bottom - target_height)
    return x, expanded_y, w, max(2, expanded_bottom - expanded_y)


def _output_dimensions(first_width: int, first_height: int, ratio: str) -> tuple[int, int]:
    """默认保留首个视频像素尺寸；显式比例使用其最长边构造画布。"""

    if ratio == "original" or ratio not in _VIDEO_RATIOS:
        return _even(first_width), _even(first_height)
    target = _VIDEO_RATIOS[ratio]
    long_edge = max(first_width, first_height)
    if target >= 1:
        return _even(long_edge), _even(long_edge / target)
    return _even(long_edge * target), _even(long_edge)


def _escape_subtitles_filter_path(path: Path) -> str:
    """转义 FFmpeg subtitles filter 中具有语法含义的路径字符。"""

    return re.sub(r"([\\':,\[\]])", r"\\\1", str(path))


class RenderInputError(AdapterError):
    """不可变快照、来源或时间线输入无效。"""

    code = "RENDER_INPUT_INVALID"


class RenderTemporaryError(AdapterError):
    """渲染后端发生可自动重试的临时错误。"""

    code = "RENDER_TEMPORARY_FAILURE"
    retryable = True


class RenderBackend(Protocol):
    """接收显式输入路径的请求级渲染后端协议。"""

    def render(
        self,
        *,
        sources: Sequence[Path],
        source_order: Sequence[str],
        timeline: Sequence[Mapping[str, object]],
        output_dir: Path,
        render_config: Mapping[str, object] | None = None,
        heartbeat: Callable[[], None] | None = None,
    ) -> Mapping[str, object]:
        """返回最终视频、字幕和合并配音路径。"""
        ...


class FakeRenderBackend:
    """无 FFmpeg/网络依赖的确定性渲染测试后端。"""

    def render(
        self,
        *,
        sources,
        source_order,
        timeline,
        output_dir,
        render_config=None,
        heartbeat=None,
        progress: Callable[[int], None] | None = None,
    ):
        """在 attempt output 内创建最小但非空的媒体产物。"""

        video = output_dir / "final.mp4"
        subtitle = output_dir / "subtitle.srt"
        voice = output_dir / "voice.wav"
        video.write_bytes(b"\x00\x00\x00\x18ftypmp42fake-render")
        cues = []
        adjusted = []
        cursor = 0.0
        for index, item in enumerate(timeline, 1):

            def stamp(value):
                milliseconds = as_int(as_float(value) * 1000)
                hours, remainder = divmod(milliseconds, 3_600_000)
                minutes, remainder = divmod(remainder, 60_000)
                seconds, millis = divmod(remainder, 1000)
                return f"{hours:02}:{minutes:02}:{seconds:02},{millis:03}"

            duration = as_float(item["end"]) - as_float(item["start"])
            adjusted.append(
                {
                    **item,
                    "source_start": as_float(item["start"]),
                    "source_end": as_float(item["end"]),
                    "start": cursor,
                    "end": cursor + duration,
                }
            )
            if item.get("original_sound") is not True:
                cues.append(
                    f"{len(cues) + 1}\n{stamp(cursor)} --> "
                    f"{stamp(cursor + duration)}\n"
                    f"{item.get('subtitle') or item['narration']}\n"
                )
            cursor += duration
        subtitle.write_text("\n".join(cues) or "\n", encoding="utf-8")
        with wave.open(str(voice), "wb") as output:
            output.setparams((1, 2, 16_000, 1_600, "NONE", "not compressed"))
            output.writeframes(b"\0\0" * 1_600)
        return {
            "video": video,
            "subtitle": subtitle,
            "voice": voice,
            "timeline": adjusted,
            "width": 1280,
            "height": 720,
            "duration": cursor,
        }


@dataclass(slots=True)
class FfmpegRenderBackend:
    """用受治理 FFmpeg 与请求级 TTS Provider 合成最终媒体。"""

    provider: TtsProvider
    voice_snapshot: Mapping[str, object]
    runner: ProcessRunner
    timeout_seconds: float = 1800.0

    @staticmethod
    def _caption_font(text: str, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
        """优先选择包含中日韩字形的系统字体，最后回退 Pillow 默认字体。"""

        del text
        for candidate in (
            "/System/Library/Fonts/PingFang.ttc",
            "/System/Library/Fonts/STHeiti Medium.ttc",
            "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ):
            try:
                return ImageFont.truetype(candidate, size=size)
            except OSError:
                continue
        return ImageFont.load_default()

    @staticmethod
    def _caption_lines(
        text: str,
        *,
        draw: ImageDraw.ImageDraw,
        font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
        max_width: int,
        stroke_width: int,
    ) -> list[str]:
        """按真实字形宽度换行；英文保持单词完整，中文允许逐字断行。"""

        tokens = text.split(" ") if " " in text.strip() else list(text.strip())
        separator = " " if " " in text.strip() else ""
        lines: list[str] = []
        current = ""
        for token in tokens:
            candidate = token if not current else f"{current}{separator}{token}"
            box = draw.textbbox(
                (0, 0), candidate, font=font, stroke_width=stroke_width
            )
            if current and box[2] - box[0] > max_width:
                lines.append(current)
                current = token
            else:
                current = candidate
        if current:
            lines.append(current)
        return lines or [text.strip()]

    def _semantic_caption_segments(
        self,
        *,
        text: str,
        draw: ImageDraw.ImageDraw,
        font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
        max_width: int,
        stroke_width: int,
    ) -> list[str] | None:
        """按语义标点拆 cue，并保证每个 cue 最多两行且不拆英文单词。"""

        value = text.strip()
        if not value:
            return []

        def fits(candidate: str) -> bool:
            lines = self._caption_lines(
                candidate,
                draw=draw,
                font=font,
                max_width=max_width,
                stroke_width=stroke_width,
            )
            return len(lines) <= 2 and all(
                draw.textbbox(
                    (0, 0), line, font=font, stroke_width=stroke_width
                )[2]
                <= max_width
                for line in lines
            )

        semantic_units = [
            part
            for part in re.findall(r".*?[。！？!?；;，,]|.+$", value)
            if part
        ]
        result: list[str] = []
        for unit in semantic_units:
            if fits(unit):
                if result and fits(result[-1] + unit):
                    result[-1] += unit
                else:
                    result.append(unit)
                continue
            tokens = (
                re.findall(r"\S+\s*", unit)
                if re.search(r"[A-Za-z]", unit) and " " in unit
                else list(unit)
            )
            current = ""
            for token in tokens:
                candidate = current + token
                if current and not fits(candidate):
                    result.append(current)
                    current = token
                elif not current and not fits(token):
                    return None
                else:
                    current = candidate
            if current:
                result.append(current)
        return result if result and "".join(result) == value else None

    def _expand_caption_timeline(
        self,
        *,
        timeline: Sequence[Mapping[str, object]],
        source_regions: Sequence[VideoContentRegion],
        width: int,
        height: int,
        style: str,
        position_y: float,
        font_scale: float,
    ) -> tuple[list[dict[str, object]], list[VideoContentRegion]]:
        """将长解说拆成共享于 SRT、PNG 和 concat 的细粒度 cue。"""

        del style
        expanded: list[dict[str, object]] = []
        expanded_regions: list[VideoContentRegion] = []
        for item, region in zip(timeline, source_regions, strict=True):
            segment_start = as_float(item["start"])
            segment_end = as_float(item["end"])
            start = as_float(
                item["start"]
                if item.get("original_sound") is True
                else item.get("narration_start", item["start"])
            )
            end = as_float(
                item["end"]
                if item.get("original_sound") is True
                else item["narration_end"]
            )
            if item.get("original_sound") is True:
                expanded.append({**item, "subtitle": ""})
                expanded_regions.append(region)
                continue
            if start > segment_start + 1e-6:
                expanded.append({
                    **item,
                    "start": segment_start,
                    "end": start,
                    "narration_end": start,
                    "subtitle": "",
                })
                expanded_regions.append(region)
            text = str(item.get("subtitle") or item.get("narration") or "").strip()
            image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
            draw = ImageDraw.Draw(image)
            font_size = max(18, as_int(round(height * 0.055 * font_scale)))
            stroke_width = max(2, as_int(round(height * 0.004)))
            max_width = max(1, as_int(round(region.width * 0.86)))
            segments = self._semantic_caption_segments(
                text=text,
                draw=draw,
                font=self._caption_font(text, font_size),
                max_width=max_width,
                stroke_width=stroke_width,
            )
            if not segments:
                segments = [text]
            weights = [max(1, len(re.sub(r"\s+", "", part))) for part in segments]
            total_weight = sum(weights)
            cursor = start
            for index, (part, weight) in enumerate(zip(segments, weights, strict=True)):
                cue_end = (
                    end
                    if index == len(segments) - 1
                    else cursor + (end - start) * weight / total_weight
                )
                expanded.append(
                    {
                        **item,
                        "start": cursor,
                        "end": cue_end,
                        "narration_end": cue_end,
                        "subtitle": part,
                        "position_y": item.get("position_y", position_y),
                    }
                )
                expanded_regions.append(region)
                cursor = cue_end
            if end < segment_end - 1e-6:
                expanded.append({
                    **item,
                    "start": end,
                    "end": segment_end,
                    "narration_end": segment_end,
                    "subtitle": "",
                })
                expanded_regions.append(region)
        return expanded, expanded_regions

    def _render_caption_images(
        self,
        *,
        timeline: Sequence[Mapping[str, object]],
        width: int,
        height: int,
        style: str,
        output_dir: Path,
        position: Mapping[str, object] | None = None,
        source_regions: Sequence[object] | None = None,
    ) -> list[Path]:
        """生成透明全画布字幕图；同一图层的显示时段由 FFmpeg overlay 控制。"""

        position = position if isinstance(position, Mapping) else {}
        y = as_float(position.get("y", 0.82))
        font_scale = as_float(position.get("font_scale", 0.9))
        fill = (255, 255, 255, 255)
        stroke = (0, 0, 0, 255)
        if style in {"白字蓝边", "blue_outline"}:
            stroke = (0, 102, 255, 255)
        elif style in {"霓虹描边", "neon_outline"}:
            stroke = (255, 0, 255, 255)
        paths: list[Path] = []
        for index, item in enumerate(timeline):
            raw_text = (
                item.get("subtitle")
                if "subtitle" in item
                else item.get("narration")
            )
            text = str(raw_text or "").strip()
            image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
            draw = ImageDraw.Draw(image)
            region = (
                source_regions[index]
                if source_regions is not None and index < len(source_regions)
                else VideoContentRegion(0, 0, width, height)
            )
            stroke_width = max(2, as_int(round(height * 0.004)))
            # 字号只由同一画布/内容区和用户 scale 决定，不再按每条文字缩小。
            font_size = max(18, as_int(round(height * 0.055 * font_scale)))
            max_width = max(1, as_int(round(region.width * 0.86)))
            font = self._caption_font(text, font_size)
            lines = self._caption_lines(
                text,
                draw=draw,
                font=font,
                max_width=max_width,
                stroke_width=stroke_width,
            )[:2]
            rendered = "\n".join(lines)
            if text:
                item_y = as_float(item.get("position_y", y))
                center_y = region.y + item_y * region.height
                center_y = min(
                    region.y + region.height - font_size,
                    max(region.y + font_size, center_y),
                )
                draw.multiline_text(
                    (region.x + region.width / 2, center_y),
                    rendered,
                    font=font,
                    fill=fill,
                    anchor="mm",
                    align="center",
                    spacing=max(2, font_size // 5),
                    stroke_width=stroke_width,
                    stroke_fill=stroke,
                )
            path = output_dir / f"caption_{index:04}.png"
            image.save(path, format="PNG")
            paths.append(path)
        return paths

    @staticmethod
    def _require_process_success(result) -> None:
        """区分可恢复进程超时与确定性媒体/codec/format 错误。"""
        if result.timed_out:
            raise RenderTemporaryError("RENDER_TEMPORARY_FAILURE")
        if result.exit_code != 0:
            raise RenderInputError("RENDER_MEDIA_INVALID")

    def render(
        self,
        *,
        sources,
        source_order,
        timeline,
        output_dir,
        render_config=None,
        heartbeat=None,
        progress: Callable[[int], None] | None = None,
    ):
        """按真实 TTS 时长扩展源片裁剪范围并生成严格对齐的最终媒体。"""
        config = _normalize_render_config(
            render_config,
            has_original_sound=any(
                item.get("original_sound") is True for item in timeline
            ),
        )
        source_by_id = dict(zip(source_order, sources, strict=True))
        source_info: dict[str, dict[str, float | int]] = {}
        for source_id, source in source_by_id.items():
            try:
                probe = self.runner.run(
                    [
                        "ffprobe",
                        "-v",
                        "error",
                        "-show_entries",
                        "format=duration:stream=codec_type,width,height",
                        "-of",
                        "json",
                        str(source),
                    ],
                    timeout_seconds=min(self.timeout_seconds, 60),
                    cwd=output_dir,
                    heartbeat=heartbeat,
                )
            except OSError as exc:
                raise RenderTemporaryError("RENDER_PROCESS_UNAVAILABLE") from exc
            self._require_process_success(probe)
            try:
                payload = json.loads(probe.stdout)
                streams = payload.get("streams")
                streams = streams if isinstance(streams, list) else []
                stream = next(
                    (
                        item
                        for item in streams
                        if isinstance(item, Mapping)
                        and item.get("codec_type") == "video"
                    ),
                    streams[0] if streams else {},
                )
                duration = as_float(payload["format"]["duration"])
                width = as_int(stream.get("width", 1280))
                height = as_int(stream.get("height", 720))
                has_audio = any(
                    isinstance(item, Mapping) and item.get("codec_type") == "audio"
                    for item in streams
                )
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                raise RenderInputError("RENDER_MEDIA_INVALID") from exc
            if (
                not math.isfinite(duration)
                or duration <= 0
                or width <= 0
                or height <= 0
            ):
                raise RenderInputError("RENDER_MEDIA_INVALID")
            source_info[source_id] = {
                "duration": duration,
                "width": width,
                "height": height,
                "has_audio": has_audio,
            }
            if any(
                str(item["source_asset_id"]) == source_id
                and as_float(item["end"]) > duration + 0.02
                for item in timeline
            ):
                raise RenderInputError("RENDER_SOURCE_RANGE_INVALID")

        first_info = source_info[str(source_order[0])]
        output_width, output_height = _output_dimensions(
            as_int(first_info["width"]),
            as_int(first_info["height"]),
            str(config["video_ratio"]),
        )

        if progress:
            progress(25)
        segment_voices: list[Path | None] = []
        durations: list[float] = []
        voice_durations: list[float] = []
        source_clip_durations: list[float] = []
        freeze_durations: list[float] = []
        narration_offsets: list[float] = []
        adjusted_timeline: list[dict[str, object]] = []
        cursor = 0.0
        for index, item in enumerate(timeline):
            requested_source_start = as_float(item["start"])
            source_start = requested_source_start
            source_end = as_float(item["end"])
            source_duration = source_end - source_start
            original_sound = item.get("original_sound") is True
            target: Path | None = None
            narration_offset = 0.0
            if original_sound:
                voice_duration = 0.0
                duration = source_duration
            else:
                target = output_dir / f"voice_segment_{index:04}.wav"
                synthesis = self.provider.synthesize(
                    str(item["narration"]),
                    target,
                    voice_snapshot=self.voice_snapshot,
                )
                validate_wav(target)
                with wave.open(str(target), "rb") as voice_file:
                    voice_duration = (
                        voice_file.getnframes() / voice_file.getframerate()
                    )
                if isinstance(synthesis, TtsSynthesisResult):
                    voice_anchor = _voice_anchor_offset(
                        str(item["narration"]),
                        item.get("narration_anchor_text"),
                        synthesis.words,
                    )
                    visual_anchor = item.get("visual_anchor")
                    if (
                        type(visual_anchor) in (int, float)
                        and voice_anchor is not None
                    ):
                        visual_lead = as_float(item.get("visual_lead", 0.15))
                        narration_offset = (
                            as_float(visual_anchor)
                            - source_start
                            + visual_lead
                            - voice_anchor
                        )
                        if narration_offset < 0:
                            source_start = max(
                                0.0, source_start - min(source_start, -narration_offset)
                            )
                            narration_offset = (
                                as_float(visual_anchor)
                                - source_start
                                + visual_lead
                                - voice_anchor
                            )
                        narration_offset = max(0.0, narration_offset)
                    elif type(item.get("narration_start_offset")) in (int, float):
                        narration_offset = max(
                            0.0, as_float(item["narration_start_offset"])
                        )
                elif type(item.get("narration_start_offset")) in (int, float):
                    # 旧 Provider/已人工编辑草稿仍可显式指定；旧草稿默认为 0。
                    narration_offset = max(
                        0.0, as_float(item["narration_start_offset"])
                    )
                source_duration = source_end - source_start
                duration = max(source_duration, narration_offset + voice_duration)
            source_id = str(item["source_asset_id"])
            source_total = as_float(source_info[source_id]["duration"])
            available_duration = max(0.0, source_total - source_start)
            source_clip_duration = min(duration, available_duration)
            freeze_duration = max(0.0, duration - source_clip_duration)
            durations.append(duration)
            voice_durations.append(voice_duration)
            source_clip_durations.append(source_clip_duration)
            freeze_durations.append(freeze_duration)
            narration_offsets.append(narration_offset)
            segment_voices.append(target)
            adjusted_timeline.append(
                {
                    **item,
                    "source_start": source_start,
                    # 音频超长时只扩展当前片段的 source_end；后续片段仍从其
                    # 原始 start 开始，因此允许有意重复同一段源画面。
                    "source_end": source_start + source_clip_duration,
                    "start": cursor,
                    "end": cursor + duration,
                    "narration_start_offset": narration_offset,
                    "narration_start": cursor + narration_offset,
                    "narration_end": (
                        cursor
                        if original_sound
                        else cursor + narration_offset + voice_duration
                    ),
                    "original_sound": original_sound,
                }
            )
            cursor += duration
        if progress:
            progress(40)

        raw_video = output_dir / "video_raw.mp4"
        argv = ["ffmpeg", "-nostdin", "-y"]
        for item, clip_duration in zip(
            adjusted_timeline, source_clip_durations, strict=True
        ):
            argv.extend(
                [
                    "-ss",
                    f"{as_float(item['source_start']):g}",
                    "-t",
                    f"{clip_duration:.6f}",
                    "-i",
                    str(source_by_id[str(item["source_asset_id"])]),
                ]
            )
        filters: list[str] = []
        layouts = config["source_subtitle_layouts"]
        original_volume = as_float(config.get("original_sound_volume", 100)) / 100
        for index, (item, duration, freeze_duration) in enumerate(
            zip(timeline, durations, freeze_durations, strict=True)
        ):
            source_id = str(item["source_asset_id"])
            source_width = as_int(source_info[source_id]["width"])
            source_height = as_int(source_info[source_id]["height"])
            source_label = f"[{index}:v:0]"
            region = layouts.get(source_id) if isinstance(layouts, Mapping) else None
            # 原声片段要保留原画语境；只有解说片段才遮掉硬字幕。
            if isinstance(region, Mapping) and item.get("original_sound") is not True:
                x, y, mask_width, mask_height = _expanded_source_subtitle_blur_pixels(
                    region, source_width, source_height
                )
                filters.extend(
                    [
                        f"{source_label}split=2[src{index}][masksrc{index}]",
                        f"[masksrc{index}]crop={mask_width}:{mask_height}:{x}:{y},"
                        f"gblur=sigma=18:steps=2[blur{index}]",
                        f"[src{index}][blur{index}]overlay={x}:{y}:eval=init,"
                        f"drawbox=x={x}:y={y}:w={mask_width}:h={mask_height}:"
                        f"color=black@0.30:t=fill[masked{index}]",
                    ]
                )
                source_label = f"[masked{index}]"
            filters.append(
                f"{source_label}"
                f"scale={output_width}:{output_height}:force_original_aspect_ratio=decrease,"
                f"pad={output_width}:{output_height}:(ow-iw)/2:(oh-ih)/2,fps=30,"
                "setsar=1,settb=AVTB,setpts=PTS-STARTPTS,"
                f"tpad=stop_mode=clone:stop_duration={freeze_duration:.6f},"
                f"trim=duration={duration:.6f},setpts=PTS-STARTPTS[v{index}]"
            )
            if (
                item.get("original_sound") is True
                and bool(source_info[source_id].get("has_audio"))
            ):
                filters.append(
                    f"[{index}:a:0]aresample=48000,aformat=sample_fmts=fltp:"
                    "channel_layouts=stereo,"
                    f"volume={original_volume:.6f},apad,atrim=duration={duration:.6f},"
                    f"asetpts=PTS-STARTPTS[a{index}]"
                )
            else:
                filters.append(
                    f"anullsrc=r=48000:cl=stereo,atrim=duration={duration:.6f},"
                    f"asetpts=PTS-STARTPTS[a{index}]"
                )
        labels = "".join(f"[v{index}][a{index}]" for index in range(len(timeline)))
        filters.append(f"{labels}concat=n={len(timeline)}:v=1:a=1[v][sourcea]")
        argv.extend(
            [
                "-filter_complex",
                ";".join(filters),
                "-map",
                "[v]",
                "-map",
                "[sourcea]",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-preset",
                "veryfast",
                "-c:a",
                "aac",
                str(raw_video),
            ]
        )
        result = self.runner.run(
            argv,
            timeout_seconds=self.timeout_seconds,
            cwd=output_dir,
            heartbeat=heartbeat,
        )
        self._require_process_success(result)
        if progress:
            progress(50)

        # 配音轨在原声片段处补静音，最终与 raw_video 中仅保留的原声混合。
        voice = output_dir / "voice.wav"
        audio_argv = ["ffmpeg", "-nostdin", "-y"]
        voice_input_by_segment: dict[int, int] = {}
        for segment_index, target in enumerate(segment_voices):
            if target is not None:
                voice_input_by_segment[segment_index] = len(voice_input_by_segment)
                audio_argv.extend(["-i", str(target)])
        if not voice_input_by_segment:
            audio_argv.extend(
                [
                    "-f",
                    "lavfi",
                    "-i",
                    "anullsrc=r=16000:cl=mono",
                    "-t",
                    f"{sum(durations):.6f}",
                    "-c:a",
                    "pcm_s16le",
                    str(voice),
                ]
            )
        else:
            audio_filters: list[str] = []
            for segment_index, duration in enumerate(durations):
                input_index = voice_input_by_segment.get(segment_index)
                if input_index is None:
                    audio_filters.append(
                        f"anullsrc=r=16000:cl=mono,atrim=duration={duration:.6f},"
                        f"asetpts=PTS-STARTPTS[va{segment_index}]"
                    )
                else:
                    delay_ms = max(0, round(narration_offsets[segment_index] * 1000))
                    audio_filters.append(
                        f"[{input_index}:a:0]aresample=16000,"
                        f"adelay={delay_ms}:all=1,apad,"
                        f"atrim=duration={duration:.6f},"
                        f"asetpts=PTS-STARTPTS[va{segment_index}]"
                    )
            audio_labels = "".join(
                f"[va{index}]" for index in range(len(durations))
            )
            audio_filters.append(
                f"{audio_labels}concat=n={len(durations)}:v=0:a=1[voicea]"
            )
            audio_argv.extend(
                [
                    "-filter_complex",
                    ";".join(audio_filters),
                    "-map",
                    "[voicea]",
                    "-c:a",
                    "pcm_s16le",
                    str(voice),
                ]
            )
        result = self.runner.run(
            audio_argv,
            timeout_seconds=self.timeout_seconds,
            cwd=output_dir,
            heartbeat=heartbeat,
        )
        self._require_process_success(result)
        validate_wav(voice)
        if progress:
            progress(65)

        position = config["narration_subtitle_position"]
        position_y = as_float(position.get("y", 0.82))
        font_scale = as_float(position.get("font_scale", 0.9))
        content_regions: list[VideoContentRegion] = []
        for item in adjusted_timeline:
            source_id = str(item["source_asset_id"])
            info = source_info[source_id]
            content_regions.append(
                _effective_video_content_region(
                    output_width,
                    output_height,
                    as_int(info["width"]),
                    as_int(info["height"]),
                )
            )
            source_layout = (
                layouts.get(source_id) if isinstance(layouts, Mapping) else None
            )
            if isinstance(source_layout, Mapping):
                item["position_y"] = min(
                    0.96,
                    max(
                        0.04,
                        as_float(source_layout["y"])
                        + as_float(source_layout["height"]) / 2,
                    ),
                )
        caption_timeline, caption_regions = self._expand_caption_timeline(
            timeline=adjusted_timeline,
            source_regions=content_regions,
            width=output_width,
            height=output_height,
            style=str(config.get("subtitle_style") or "经典白色"),
            position_y=position_y,
            font_scale=font_scale,
        )

        def stamp(value: float) -> str:
            total = as_int(round(value * 1000))
            hours, rem = divmod(total, 3_600_000)
            minutes, rem = divmod(rem, 60_000)
            seconds, millis = divmod(rem, 1_000)
            return f"{hours:02}:{minutes:02}:{seconds:02},{millis:03}"

        subtitle = output_dir / "subtitle.srt"
        subtitle_rows = [
            item for item in caption_timeline if str(item.get("subtitle") or "").strip()
        ]
        subtitle_content = "\n".join(
                f"{index}\n{stamp(as_float(item['start']))} --> "
                f"{stamp(as_float(item['end']))}\n{item['subtitle']}\n"
                for index, item in enumerate(subtitle_rows, 1)
            )
        subtitle.write_text(subtitle_content or "\n", encoding="utf-8")
        caption_images = self._render_caption_images(
            timeline=caption_timeline,
            width=output_width,
            height=output_height,
            style=str(config.get("subtitle_style") or "经典白色"),
            position=position,
            source_regions=caption_regions,
            output_dir=output_dir,
        )
        manifest = output_dir / "captions.ffconcat"
        manifest_lines = ["ffconcat version 1.0"]
        for image, item in zip(caption_images, caption_timeline, strict=True):
            escaped = str(image).replace("'", "'\\''")
            manifest_lines.extend(
                [
                    f"file '{escaped}'",
                    f"duration {as_float(item['end']) - as_float(item['start']):.6f}",
                ]
            )
        if caption_images:
            escaped = str(caption_images[-1]).replace("'", "'\\''")
            manifest_lines.append(f"file '{escaped}'")
        manifest.write_text("\n".join(manifest_lines) + "\n", encoding="utf-8")
        if progress:
            progress(72)

        final = output_dir / "final.mp4"
        total_duration = sum(durations)
        final_argv = [
            "ffmpeg",
            "-nostdin",
            "-y",
            "-i",
            str(raw_video),
            "-i",
            str(voice),
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(manifest),
            "-filter_complex",
            "[0:v][2:v]overlay=0:0:format=auto:eof_action=pass[captioned];"
            "[0:a:0][1:a:0]amix=inputs=2:normalize=0:dropout_transition=0[a]",
            "-map",
            "[captioned]",
            "-map",
            "[a]",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-t",
            f"{total_duration:.6f}",
            str(final),
        ]
        result = self.runner.run(
            final_argv,
            timeout_seconds=self.timeout_seconds,
            cwd=output_dir,
            heartbeat=heartbeat,
        )
        self._require_process_success(result)
        if progress:
            progress(90)
        return {
            "video": final,
            "subtitle": subtitle,
            "voice": voice,
            "timeline": adjusted_timeline,
            "width": output_width,
            "height": output_height,
            "duration": total_duration,
        }


@dataclass(slots=True)
class RenderAdapter:
    """按不可变 revision 与显式 source order 生成四类正式产物。"""

    downloader: Downloader
    backend: RenderBackend
    artifact_store: ArtifactStore

    def run_subtitle(
        self,
        *,
        workspace: CoreTaskWorkspace,
        core_task_id: str,
        attempt_no: int,
        snapshot_id: str,
        timeline: Sequence[Mapping[str, object]],
        lease_guard: Callable[[], None] | None = None,
    ) -> dict[str, object]:
        """从不可变时间线生成 UTF-8 SRT，不读取共享字幕文件。"""
        if not snapshot_id or not timeline:
            raise RenderInputError("RENDER_TIMELINE_INVALID")
        cues: list[str] = []
        previous = 0.0
        for index, item in enumerate(timeline, 1):
            start, end, text = item.get("start"), item.get("end"), item.get("text")
            if (
                type(start) not in (int, float)
                or type(end) not in (int, float)
                or not math.isfinite(as_float(start))
                or not math.isfinite(as_float(end))
                or as_float(start) < previous
                or as_float(end) <= as_float(start)
                or not isinstance(text, str)
                or not text.strip()
            ):
                raise RenderInputError("RENDER_TIMELINE_INVALID")
            previous = as_float(end)

            def stamp(value: float) -> str:
                total = as_int(value * 1000)
                hours, rem = divmod(total, 3_600_000)
                minutes, rem = divmod(rem, 60_000)
                seconds, millis = divmod(rem, 1_000)
                return f"{hours:02}:{minutes:02}:{seconds:02},{millis:03}"

            cues.append(
                f"{index}\n{stamp(as_float(start))} --> {stamp(as_float(end))}\n{text.strip()}\n"
            )
        target = workspace.controlled_path("output", "subtitle", "srt")
        target.write_text("\n".join(cues), encoding="utf-8")
        if target.stat().st_size > SRT_MAX_BYTES:
            raise RenderInputError("RENDER_SUBTITLE_INVALID")
        metadata = parse_srt(target.read_bytes())
        if lease_guard:
            lease_guard()
        artifact = self.artifact_store.upload(
            workspace=workspace,
            local_path=target,
            core_task_id=core_task_id,
            attempt_no=attempt_no,
            kind="subtitle",
            content_type="application/x-subrip; charset=utf-8",
        )
        return {
            "metadata": {**metadata, "snapshot_id": snapshot_id},
            "artifacts": [artifact.to_dict()],
        }

    def run(
        self,
        *,
        workspace: CoreTaskWorkspace,
        core_task_id: str,
        attempt_no: int,
        snapshot_id: str,
        source_order: Sequence[str],
        sources: Sequence[Mapping[str, object]],
        timeline: Sequence[Mapping[str, object]],
        voice_id: str,
        voice_snapshot: Mapping[str, object],
        render_config: Mapping[str, object] | None = None,
        lease_guard: Callable[[], None] | None = None,
    ) -> dict[str, object]:
        """下载显式来源、验证时间线并上传 video/subtitle/voice/timeline。"""

        if not snapshot_id or voice_snapshot.get("voice_id") != voice_id:
            raise RenderInputError("RENDER_INPUT_INVALID")
        normalized_render_config = _normalize_render_config(
            render_config,
            has_original_sound=any(
                isinstance(item, Mapping) and item.get("original_sound") is True
                for item in timeline
            ),
        )
        source_ids = [item.get("source_asset_id") for item in sources]
        if (
            list(source_order) != source_ids
            or len(source_ids) != len(set(source_ids))
            or not source_ids
        ):
            raise RenderInputError("RENDER_SOURCE_ORDER_INVALID")
        source_set = set(source_ids)
        validated: list[dict[str, object]] = []
        first_seen: list[str] = []
        for item in timeline:
            source_id = item.get("source_asset_id")
            start, end, narration = (
                item.get("start"),
                item.get("end"),
                item.get("narration"),
            )
            if (
                source_id not in source_set
                or type(start) not in (int, float)
                or type(end) not in (int, float)
                or not math.isfinite(as_float(start))
                or not math.isfinite(as_float(end))
                or as_float(start) < 0
                or as_float(end) <= as_float(start)
                or not isinstance(narration, str)
                or not narration.strip()
            ):
                raise RenderInputError("RENDER_TIMELINE_INVALID")
            if source_id not in first_seen:
                first_seen.append(str(source_id))
            optional: dict[str, object] = {}
            event_id = item.get("event_id")
            if event_id is not None:
                if not isinstance(event_id, str) or not event_id.strip():
                    raise RenderInputError("RENDER_TIMELINE_INVALID")
                optional["event_id"] = event_id.strip()[:160]
            visual_anchor = item.get("visual_anchor")
            if visual_anchor is not None:
                if (
                    type(visual_anchor) not in (int, float)
                    or not math.isfinite(as_float(visual_anchor))
                    or not as_float(start) <= as_float(visual_anchor) <= as_float(end)
                ):
                    raise RenderInputError("RENDER_TIMELINE_INVALID")
                optional["visual_anchor"] = as_float(visual_anchor)
            anchor_text = item.get("narration_anchor_text")
            if anchor_text is not None:
                if (
                    not isinstance(anchor_text, str)
                    or not anchor_text.strip()
                    or anchor_text.strip() not in narration
                ):
                    raise RenderInputError("RENDER_TIMELINE_INVALID")
                optional["narration_anchor_text"] = anchor_text.strip()
            match_confidence = item.get("match_confidence")
            if match_confidence is not None:
                if (
                    type(match_confidence) not in (int, float)
                    or not math.isfinite(as_float(match_confidence))
                    or not 0 <= as_float(match_confidence) <= 1
                ):
                    raise RenderInputError("RENDER_TIMELINE_INVALID")
                optional["match_confidence"] = as_float(match_confidence)
            visual_lead = item.get("visual_lead")
            if visual_lead is not None:
                if (
                    type(visual_lead) not in (int, float)
                    or not math.isfinite(as_float(visual_lead))
                    or not -2 <= as_float(visual_lead) <= 2
                ):
                    raise RenderInputError("RENDER_TIMELINE_INVALID")
                optional["visual_lead"] = as_float(visual_lead)
            offset = item.get("narration_start_offset")
            if offset is not None:
                if (
                    type(offset) not in (int, float)
                    or not math.isfinite(as_float(offset))
                    or as_float(offset) < 0
                ):
                    raise RenderInputError("RENDER_TIMELINE_INVALID")
                optional["narration_start_offset"] = as_float(offset)
            validated.append(
                {
                    "source_asset_id": source_id,
                    "start": as_float(start),
                    "end": as_float(end),
                    "narration": narration.strip(),
                    "subtitle": (
                        str(item.get("subtitle")).strip()
                        if isinstance(item.get("subtitle"), str)
                        and str(item.get("subtitle")).strip()
                        else narration.strip()
                    ),
                    "original_sound": bool(item.get("original_sound", False)),
                    **optional,
                }
            )
        expected_seen = [item for item in source_order if item in first_seen]
        if first_seen != expected_seen or not validated:
            raise RenderInputError("RENDER_TIMELINE_INVALID")
        paths = []
        for index, source in enumerate(sources):
            target = workspace.controlled_path("input", f"source_{index:03}", "mp4")
            self.downloader.download(
                str(source["video_url"]), target, max_bytes=VIDEO_MAX_BYTES
            )
            paths.append(target)
        try:
            produced = self.backend.render(
                sources=paths,
                source_order=source_order,
                timeline=validated,
                output_dir=workspace.output_dir,
                render_config=normalized_render_config,
                heartbeat=lease_guard,
            )
        except AdapterError:
            raise
        except Exception as exc:
            raise RenderTemporaryError("RENDER_TEMPORARY_FAILURE") from exc
        rendered_timeline = produced.get("timeline")
        if not isinstance(rendered_timeline, Sequence) or isinstance(
            rendered_timeline, (str, bytes)
        ):
            raise RenderInputError("RENDER_OUTPUT_INVALID")
        timeline_path = workspace.controlled_path("output", "timeline", "json")
        timeline_path.write_text(
            json.dumps(
                {
                    "schema_version": "short-drama-render.v1",
                    "snapshot_id": snapshot_id,
                    "source_order": list(source_order),
                    "items": list(rendered_timeline),
                    "render_config": normalized_render_config,
                },
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            encoding="utf-8",
        )
        try:
            if timeline_path.stat().st_size > JSON_MAX_BYTES:
                raise RenderInputError("RENDER_TIMELINE_TOO_LARGE")
            subtitle = Path(str(produced["subtitle"]))
            if subtitle.stat().st_size > SRT_MAX_BYTES:
                raise RenderInputError("RENDER_SUBTITLE_INVALID")
            subtitle_bytes = subtitle.read_bytes()
            if subtitle_bytes.strip():
                parse_srt(subtitle_bytes)
            elif not all(
                isinstance(item, Mapping) and item.get("original_sound") is True
                for item in rendered_timeline
            ):
                raise RenderInputError("RENDER_SUBTITLE_INVALID")
            video, voice = Path(str(produced["video"])), Path(str(produced["voice"]))
            for path in (video, subtitle, voice):
                if (
                    path.parent.resolve() != workspace.output_dir.resolve()
                    or not path.is_file()
                    or path.stat().st_size <= 0
                ):
                    raise RenderInputError("RENDER_OUTPUT_INVALID")
            with video.open("rb") as stream:
                if b"ftyp" not in stream.read(32):
                    raise RenderInputError("RENDER_VIDEO_INVALID")
            validate_wav(voice)
        except (OSError, KeyError, ValueError) as exc:
            if isinstance(exc, RenderInputError):
                raise
            raise RenderInputError("RENDER_OUTPUT_INVALID") from exc
        if lease_guard:
            lease_guard()
        uploaded = []
        try:
            for kind, path, content_type in (
                ("video", video, "video/mp4"),
                ("subtitle", subtitle, "application/x-subrip; charset=utf-8"),
                ("voice", voice, "audio/wav"),
                ("timeline", timeline_path, "application/json"),
            ):
                if lease_guard:
                    lease_guard()
                uploaded.append(
                    self.artifact_store.upload(
                        workspace=workspace,
                        local_path=path,
                        core_task_id=core_task_id,
                        attempt_no=attempt_no,
                        kind=kind,
                        content_type=content_type,
                    )
                )
        except BaseException:
            self.artifact_store.compensate(uploaded)
            raise
        artifacts = [item.to_dict() for item in uploaded]
        video_artifact = next(
            (item for item in artifacts if item.get("kind") == "video"), None
        )
        if video_artifact is not None:
            if isinstance(produced.get("width"), int):
                video_artifact["width"] = produced["width"]
            if isinstance(produced.get("height"), int):
                video_artifact["height"] = produced["height"]
            if isinstance(produced.get("duration"), (int, float)):
                video_artifact["duration"] = as_float(produced["duration"])
        return {
            "metadata": {
                "snapshot_id": snapshot_id,
                "source_count": len(paths),
                "render_config": normalized_render_config,
                "jianying_snapshot": {
                    "timeline": [
                        {
                            "source_asset_id": item.get("source_asset_id"),
                            "start": as_float(item.get("start", 0)),
                            "end": as_float(item.get("end", 0)),
                            "narration": str(
                                item.get("subtitle") or item.get("narration") or ""
                            ),
                        }
                        for item in rendered_timeline
                        if isinstance(item, Mapping)
                        and item.get("original_sound") is not True
                    ],
                    "video": {
                        "width": produced.get("width"),
                        "height": produced.get("height"),
                        "duration": produced.get("duration"),
                    },
                },
            },
            "artifacts": artifacts,
        }
