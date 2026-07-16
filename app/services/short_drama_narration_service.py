"""不依赖 WebUI 的短剧解说核心服务。"""

from __future__ import annotations

import json
import math
import os
import re
from dataclasses import dataclass
from typing import Any, Callable, Iterable

from app.services.media_probe import probe_media
from app.services.short_drama_narration_validation import normalize_script_video_sources
from app.services.subtitle_text import read_subtitle_text


PUBLIC_SCRIPT_FIELDS = [
    "_id",
    "video_id",
    "video_name",
    "timestamp",
    "picture",
    "narration",
    "OST",
]
SHORT_DRAMA_PROMPT_CATEGORY = "short_drama_narration"
DEFAULT_NARRATION_CHARS_PER_SECOND = 5
NARRATION_DURATION_COEFFICIENTS = {
    SHORT_DRAMA_PROMPT_CATEGORY: (0.15, 0.25),
    "film_tv_narration": (0.12, 0.25),
    "short_drama_editing": (0.2, 0.35),
    "documentary": (0.2, 0.4),
}


class ShortDramaNarrationError(RuntimeError):
    """表示短剧解说脚本构建失败。"""

    def __init__(self, message: str, *, reason: str = "generation_failed") -> None:
        """保存稳定失败原因，供 UI 适配为既有提示文案。"""

        super().__init__(message)
        self.reason = reason


@dataclass(frozen=True, slots=True)
class ShortDramaAnalysisRequest:
    """描述一次不含 UI 状态的短剧脚本构建请求。"""

    video_paths: list[str]
    short_name: str = ""
    plot_analysis: str = ""
    subtitle_content: str = ""
    narration_copy: str = ""
    temperature: float = 0.7
    narration_language: str = "简体中文（中国）"
    drama_genre: str = "逆袭/复仇"
    original_sound_ratio: int = 30
    analyzer: Any | None = None
    narration_result: dict[str, Any] | None = None
    stream_callback: Callable[[dict[str, Any]], None] | None = None


def normalize_paths(paths: str | Iterable[str] | None) -> list[str]:
    """清理、去重并保留输入顺序地返回文件路径。"""

    if isinstance(paths, str):
        paths = [paths]
    normalized: list[str] = []
    seen: set[str] = set()
    for path in paths or []:
        if not isinstance(path, str):
            continue
        path = path.strip()
        if path and path not in seen:
            normalized.append(path)
            seen.add(path)
    return normalized


def build_narration_char_range(
    source_duration_seconds: float,
    prompt_category: str,
    original_sound_ratio: int,
    chars_per_second: float = DEFAULT_NARRATION_CHARS_PER_SECOND,
) -> str:
    """按视频时长、场景系数和原声比例计算建议解说字数区间。"""

    try:
        duration = float(source_duration_seconds or 0)
        speed = float(chars_per_second or 0)
        ratio = int(original_sound_ratio or 0)
    except (TypeError, ValueError):
        return ""
    if duration <= 0 or speed <= 0:
        return ""

    narration_ratio = max(0.0, 1.0 - min(max(ratio, 0), 100) / 100)
    if narration_ratio <= 0:
        return ""
    minimum_coefficient, maximum_coefficient = NARRATION_DURATION_COEFFICIENTS.get(
        prompt_category,
        NARRATION_DURATION_COEFFICIENTS[SHORT_DRAMA_PROMPT_CATEGORY],
    )
    minimum = math.floor(duration * minimum_coefficient * narration_ratio * speed)
    maximum = math.ceil(duration * maximum_coefficient * narration_ratio * speed)
    if maximum <= 0:
        return ""
    minimum = max(1, minimum)
    return f"{minimum}-{max(minimum, maximum)}"


def build_narration_char_range_for_video_paths(
    video_paths: str | Iterable[str] | None,
    prompt_category: str,
    original_sound_ratio: int,
    chars_per_second: float = DEFAULT_NARRATION_CHARS_PER_SECOND,
) -> str:
    """探测多个视频的总时长并构建建议解说字数区间。"""

    total_duration = 0.0
    for video_path in normalize_paths(video_paths):
        if not os.path.exists(video_path):
            continue
        try:
            total_duration += probe_media(video_path).duration_seconds
        except Exception:
            # 任一已有媒体不可探测时不返回可能误导用户的字数范围。
            return ""
    return build_narration_char_range(
        total_duration,
        prompt_category,
        original_sound_ratio,
        chars_per_second,
    )


def build_combined_subtitle_content(
    subtitle_paths: str | Iterable[str] | None,
    video_paths: str | Iterable[str] | None = None,
) -> str:
    """将多份字幕合并为带稳定视频来源标记的文本。"""

    sections: list[str] = []
    normalized_videos = normalize_paths(video_paths)
    for index, subtitle_path in enumerate(normalize_paths(subtitle_paths), start=1):
        if not os.path.exists(subtitle_path):
            continue
        video_path = (
            normalized_videos[index - 1] if index <= len(normalized_videos) else ""
        )
        header = f"# 视频 {index}"
        if video_path:
            header += f": {os.path.basename(video_path)}"
        header += f"\n字幕文件: {os.path.basename(subtitle_path)}"
        sections.append(f"{header}\n{read_subtitle_text(subtitle_path).text}".strip())
    return "\n\n".join(sections)


def parse_and_fix_json(json_string: str) -> dict[str, Any] | None:
    """解析模型 JSON，并修复常见代码块、双括号与尾逗号问题。"""

    value = str(json_string or "").strip()
    if not value:
        return None
    candidates = [value, value.replace("{{", "{").replace("}}", "}")]
    code_block = re.search(r"```json\s*(.*?)\s*```", value, re.DOTALL | re.IGNORECASE)
    if code_block:
        candidates.append(code_block.group(1).strip())
    start, end = value.find("{"), value.rfind("}")
    if start >= 0 and end > start:
        candidates.append(value[start : end + 1])

    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            continue

    repaired = candidates[-1]
    repaired = repaired.replace("{{", "{").replace("}}", "}")
    repaired = re.sub(r"#.*", "", repaired)
    repaired = re.sub(r"//.*", "", repaired)
    repaired = re.sub(r",\s*([}\]])", r"\1", repaired)
    repaired = re.sub(r"'([^']*)':", r'"\1":', repaired)
    repaired = re.sub(r"(\w+)(\s*):", r'"\1"\2:', repaired)
    repaired = re.sub(r'""([^\"]*?)""', r'"\1"', repaired)
    try:
        parsed = json.loads(repaired)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        return None


def normalize_narration_items_video_sources(
    items: object, video_paths: Iterable[str]
) -> list[dict[str, Any]]:
    """将脚本片段的视频编号和文件名归一化到请求中的视频来源。"""

    return normalize_script_video_sources(items, normalize_paths(video_paths))


def strip_planner_only_fields(items: Iterable[object]) -> list[dict[str, Any]]:
    """仅保留可公开给剪辑流程使用的脚本字段。"""

    return [
        {field: item[field] for field in PUBLIC_SCRIPT_FIELDS if field in item}
        for item in items
        if isinstance(item, dict)
    ]


def build_short_drama_script(request: ShortDramaAnalysisRequest) -> list[dict]:
    """调用分析器或消费既有结果，返回规范化的短剧解说脚本片段。"""

    result = request.narration_result
    if result is None:
        if request.analyzer is None:
            raise ShortDramaNarrationError("缺少短剧脚本分析器")
        result = request.analyzer.match_narration_copy_to_script(
            short_name=request.short_name,
            plot_analysis=request.plot_analysis,
            subtitle_content=request.subtitle_content,
            narration_copy=request.narration_copy,
            temperature=request.temperature,
            narration_language=request.narration_language,
            drama_genre=request.drama_genre,
            original_sound_ratio=request.original_sound_ratio,
            stream_callback=request.stream_callback,
        )
    if not isinstance(result, dict) or result.get("status") != "success":
        message = result.get("message") if isinstance(result, dict) else "返回结构无效"
        raise ShortDramaNarrationError(f"短剧脚本生成失败: {message}")

    parsed = parse_and_fix_json(str(result.get("narration_script") or ""))
    if parsed is None:
        raise ShortDramaNarrationError("短剧脚本 JSON 解析失败", reason="invalid_json")
    if not isinstance(parsed.get("items"), list):
        raise ShortDramaNarrationError(
            "短剧脚本 JSON 缺少 items 数组", reason="missing_items"
        )
    normalized = normalize_narration_items_video_sources(
        parsed["items"], request.video_paths
    )
    return strip_planner_only_fields(normalized)


CORE_TIMELINE_PUBLIC_FIELDS = (
    "source_asset_id",
    "start",
    "end",
    "narration",
    "picture",
    "original_sound",
)


def normalize_short_drama_timeline_items(items: object) -> list[dict[str, Any]]:
    """为 Core 时间线裁剪公开字段，但不猜测、改写或重排来源。"""

    if isinstance(items, dict):
        items = items.get("items")
    if not isinstance(items, list):
        return []
    return [
        {field: item[field] for field in CORE_TIMELINE_PUBLIC_FIELDS if field in item}
        for item in items
        if isinstance(item, dict)
    ]
