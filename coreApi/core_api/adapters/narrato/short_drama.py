from __future__ import annotations

from core_api.type_coercion import as_float, as_int, as_mapping

import json
import hashlib
import logging
import math
import re
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, NoReturn, Protocol, cast

import httpx
import requests
from openai import OpenAI

from core_api.adapters.narrato.media_probe import AdapterError, SRT_MAX_BYTES, parse_srt
from core_api.adapters.narrato.prompts.short_drama_plot_analysis import (
    PLOT_ANALYSIS_SYSTEM_PROMPT,
    plot_analysis_prompt_metadata,
    render_plot_analysis_prompt,
)
from core_api.infrastructure.oss_client import Downloader
from core_api.runtime.artifact_store import ArtifactStore
from core_api.runtime.workspace import CoreTaskWorkspace

JSON_MAX_BYTES = 5 * 1024 * 1024
PUBLIC_TIMELINE_FIELDS = (
    "source_asset_id",
    "start",
    "end",
    "narration",
    "picture",
    "original_sound",
    "event_id",
    "visual_anchor",
    "narration_anchor_text",
    "match_confidence",
    "visual_lead",
    "narration_start_offset",
)

AUDIO_UNDERSTANDING_SCHEMA: dict[str, object] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["language", "full_text", "segments"],
    "properties": {
        "language": {"type": "string"},
        "full_text": {"type": "string"},
        "segments": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "start", "end", "speaker", "text", "emotion", "confidence"
                ],
                "properties": {
                    "start": {"type": "number"},
                    "end": {"type": "number"},
                    "speaker": {"type": "string"},
                    "text": {"type": "string"},
                    "emotion": {"type": "string"},
                    "confidence": {"type": "number"},
                },
            },
        },
    },
}

VIDEO_UNDERSTANDING_SCHEMA: dict[str, object] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["summary", "characters", "events"],
    "properties": {
        "summary": {"type": "string"},
        "characters": {"type": "array", "items": {"type": "string"}},
        "events": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "event_id", "start_time", "anchor_time", "end_time",
                    "recommended_clip_start", "recommended_clip_end", "characters",
                    "action", "emotion", "dialogue", "visual_evidence",
                    "audio_evidence", "importance", "confidence",
                ],
                "properties": {
                    "event_id": {"type": "string"},
                    "start_time": {"type": "number"},
                    "anchor_time": {"type": "number"},
                    "end_time": {"type": "number"},
                    "recommended_clip_start": {"type": "number"},
                    "recommended_clip_end": {"type": "number"},
                    "characters": {"type": "array", "items": {"type": "string"}},
                    "action": {"type": "string", "minLength": 1},
                    "emotion": {"type": "string"},
                    "dialogue": {"type": "string"},
                    "visual_evidence": {"type": "string", "minLength": 1},
                    "audio_evidence": {"type": "string"},
                    "importance": {"type": "number"},
                    "confidence": {"type": "number"},
                },
            },
        },
    },
}

logger = logging.getLogger(__name__)


def normalize_short_drama_timeline_items(items: object) -> list[dict[str, object]]:
    """按 Task2 公开字段契约裁剪时间线，不导入 legacy 进程全局。"""

    if isinstance(items, Mapping):
        items = items.get("items")
    if not isinstance(items, list):
        return []
    return [
        {key: item[key] for key in PUBLIC_TIMELINE_FIELDS if key in item}
        for item in items
        if isinstance(item, Mapping)
    ]


class ShortDramaInputError(AdapterError):
    """分析输入、字幕或前序 Artifact 不符合稳定协议。"""

    code = "SHORT_DRAMA_INPUT_INVALID"


class ScriptValidationError(AdapterError):
    """文案时间线确定性校验失败且不可自动重试。"""

    code = "SCRIPT_VALIDATION_FAILED"

    def __init__(
        self,
        reason: str,
        *,
        details: Mapping[str, object] | None = None,
        diagnostics: Mapping[str, object] | None = None,
    ) -> None:
        super().__init__(reason)
        self.reason = reason
        self.details = dict(details or {})
        self.diagnostics = dict(diagnostics or {})

    def error_payload(self) -> dict[str, object]:
        """返回可持久化且不含凭据、URL 或本地路径的诊断摘要。"""

        payload: dict[str, object] = {"code": self.code, "reason": self.reason}
        if self.details:
            payload["details"] = self.details
        if self.diagnostics:
            payload["diagnostics"] = self.diagnostics
        return payload


class ProviderTemporaryError(AdapterError):
    """供应商网络、限流或短暂故障。"""

    code = "PROVIDER_TEMPORARY_FAILURE"
    retryable = True


class ProviderResponseError(AdapterError):
    """供应商返回确定性无效结构。"""

    code = "PROVIDER_RESPONSE_INVALID"


PLOT_ANALYSIS_KEYWORDS = ("剧情", "情节", "角色", "故事", "内容")


def validate_plot_analysis_output(output: object) -> str:
    """复刻剧情理解的文本输出校验，不对 Markdown 内容做重写。"""

    if not isinstance(output, str) or not output.strip():
        raise ProviderResponseError("PLOT_ANALYSIS_EMPTY")
    normalized = output.strip()
    if len(normalized) < 50:
        raise ProviderResponseError("PLOT_ANALYSIS_TOO_SHORT")
    if not any(keyword in normalized for keyword in PLOT_ANALYSIS_KEYWORDS):
        logger.warning("short_drama_plot_analysis_keywords_missing")
    return normalized


class ProviderOutputError(ProviderResponseError):
    """直接模型输出可能通过重试修复；保留截断后的无效值供一次 repair 使用。"""

    retryable = True

    def __init__(self, invalid_output: object):
        super().__init__("PROVIDER_RESPONSE_INVALID")
        self.invalid_output = invalid_output


@dataclass(frozen=True, slots=True)
class ShortDramaSource:
    """一个显式排序的视频、字幕和时长快照。"""

    source_asset_id: str
    video_url: str
    video_name: str | None = None
    subtitle_name: str | None = None
    subtitle_url: str | None = None
    duration_seconds: float | None = None
    subtitle_text: str | None = None
    subtitle_is_artifact: bool = False


class ShortDramaProvider(Protocol):
    """隔离供应商差异的最薄剧情分析与文案协议。"""

    def analyze_story(
        self,
        subtitles: Sequence[Mapping[str, str]],
        *,
        language: str,
        config: Mapping[str, object],
    ) -> Mapping[str, object]:
        """分析按显式来源排列的字幕剧情。"""
        ...

    def understand_audio(
        self,
        source: ShortDramaSource,
        *,
        language: str,
        config: Mapping[str, object],
    ) -> Mapping[str, object]:
        """通过公网视频 URL 理解内嵌音频。"""
        ...

    def analyze_video(
        self,
        source: ShortDramaSource,
        *,
        subtitle_text: str,
        language: str,
        config: Mapping[str, object],
    ) -> Mapping[str, object]:
        """通过公网视频 URL 执行一次完整视觉/剧情理解。"""
        ...

    def generate_script(
        self,
        analysis: Mapping[str, object],
        *,
        sources: Sequence[ShortDramaSource],
        language: str,
        config: Mapping[str, object],
    ) -> object:
        """从稳定分析 DTO 生成结构化文案。"""
        ...

    def match_script(
        self, script: object, *, sources: Sequence[ShortDramaSource]
    ) -> object:
        """将文案片段匹配到显式来源时间线。"""
        ...

    def repair_script(
        self,
        invalid_script: object,
        *,
        validation_errors: Sequence[str],
        sources: Sequence[ShortDramaSource],
    ) -> object:
        """根据确定性校验摘要至多修复一次。"""
        ...


class FakeShortDramaProvider:
    """不访问网络且支持无效首答、修复和临时失败注入的 Fake。"""

    def __init__(
        self,
        *,
        match_results: list[object] | None = None,
        repair_result: object | None = None,
        invalid_first: bool = False,
        retryable_failures: int = 0,
    ) -> None:
        self.match_results = list(match_results or [])
        self.repair_result = repair_result
        self.invalid_first = invalid_first
        self.retryable_failures = retryable_failures
        self.repair_calls = 0
        self.repair_validation_errors: list[str] = []
        self._matched = 0
        self._analysis_events: dict[str, Mapping[str, object]] = {}

    def _maybe_fail(self) -> None:
        if self.retryable_failures > 0:
            self.retryable_failures -= 1
            raise ProviderTemporaryError("PROVIDER_TEMPORARY_FAILURE")

    def analyze_story(
        self,
        subtitles: Sequence[Mapping[str, str]],
        *,
        language: str,
        config: Mapping[str, object],
    ) -> Mapping[str, object]:
        """按输入顺序生成确定性剧情摘要，不回显供应商私有内容。"""

        self._maybe_fail()
        scenes = [
            {
                "source_asset_id": str(item["source_asset_id"]),
                "summary": str(item["subtitle_text"]).strip()[:500],
            }
            for item in subtitles
        ]
        return {
            "title": "Fake 短剧分析",
            "summary": " / ".join(item["summary"] for item in scenes),
            "scenes": scenes,
            "language": language,
        }

    def understand_audio(self, source, *, language, config):
        self._maybe_fail()
        end = min(source.duration_seconds or 3.0, 3.0)
        return {
            "language": language,
            "full_text": f"{source.source_asset_id} 测试台词",
            "segments": [{
                "start": 0.0,
                "end": end,
                "speaker": "角色",
                "text": f"{source.source_asset_id} 测试台词",
                "emotion": "中性",
                "confidence": 1.0,
            }],
        }

    def analyze_video(self, source, *, subtitle_text, language, config):
        self._maybe_fail()
        duration = source.duration_seconds or 3.0
        end = min(duration, 3.0)
        anchor = min(end, max(0.0, end / 2))
        return {
            "summary": subtitle_text[:500] or f"{source.source_asset_id} 剧情",
            "characters": ["角色"],
            "events": [{
                "event_id": f"{source.source_asset_id}:event_001",
                "start_time": 0.0,
                "anchor_time": anchor,
                "end_time": end,
                "recommended_clip_start": 0.0,
                "recommended_clip_end": end,
                "characters": ["角色"],
                "action": "测试动作",
                "emotion": "中性",
                "dialogue": subtitle_text[:200],
                "visual_evidence": "测试画面",
                "audio_evidence": "测试音频",
                "importance": 1.0,
                "confidence": 1.0,
            }],
        }

    def generate_script(
        self,
        analysis: Mapping[str, object],
        *,
        sources: Sequence[ShortDramaSource],
        language: str,
        config: Mapping[str, object],
    ) -> object:
        """按显式来源顺序生成基础文案。"""

        self._maybe_fail()
        self._analysis_events = {
            str(item.get("source_asset_id")): item
            for item in analysis.get("events", [])
            if isinstance(item, Mapping)
            and isinstance(item.get("source_asset_id"), str)
        } if isinstance(analysis.get("events"), list) else {}
        return [
            {
                "source_asset_id": source.source_asset_id,
                "start": 0.0,
                "end": min(3.0, source.duration_seconds or 3.0),
                "narration": f"{source.source_asset_id} 剧情解说",
                **self._fake_anchor_fields(source.source_asset_id),
            }
            for source in sources
        ]

    def match_script(
        self, script: object, *, sources: Sequence[ShortDramaSource]
    ) -> object:
        """返回注入结果或保持基础脚本，不按文件名猜测来源。"""

        if self.match_results:
            result = self.match_results.pop(0)
        elif self.invalid_first and self._matched == 0:
            result = [{"invalid": True}]
        else:
            result = script
        self._matched += 1
        return result

    def repair_script(
        self,
        invalid_script: object,
        *,
        validation_errors: Sequence[str],
        sources: Sequence[ShortDramaSource],
    ) -> object:
        """只记录一次显式修复调用并返回确定性合法结果。"""

        self.repair_calls += 1
        self.repair_validation_errors = list(validation_errors)
        if self.repair_result is not None:
            return self.repair_result
        return [
            {
                "source_asset_id": source.source_asset_id,
                "start": 0.0,
                "end": min(3.0, source.duration_seconds or 3.0),
                "narration": f"{source.source_asset_id} 修复后解说",
                **self._fake_anchor_fields(source.source_asset_id),
            }
            for source in sources
        ]

    def _fake_anchor_fields(self, source_asset_id: str) -> dict[str, object]:
        event = self._analysis_events.get(source_asset_id)
        if event is None:
            return {}
        return {
            "event_id": event["event_id"],
            "visual_anchor": event["anchor_time"],
            "narration_anchor_text": source_asset_id,
            "match_confidence": event["confidence"],
            "visual_lead": 0.15,
        }


def _validation_error(
    message: str, **details: object
) -> ScriptValidationError:
    return ScriptValidationError(message, details=details)


_ORIGINAL_SOUND_MARKER = re.compile(r"^\s*播放原片(?:[_\-\s]*\d+)?\s*$")


def _is_original_sound_marker(value: object) -> bool:
    """识别提示词契约中的原片播放占位符，避免被当成解说正文。"""

    return isinstance(value, str) and _ORIGINAL_SOUND_MARKER.fullmatch(value) is not None


def _legacy_original_sound(value: object) -> bool:
    """兼容旧 Streamlit OST 字段，但不把字符串 ``"0"`` 误判为真。"""

    if value is True or value == 1:
        return True
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return False


def validate_timeline(
    items: object,
    sources: Sequence[ShortDramaSource],
    *,
    original_sound_ratio: int | None = None,
    max_total_duration: float | None = None,
    target_duration_seconds: float | None = None,
    narration_chars_per_second: float | None = 5.0,
    warnings: list[dict[str, object]] | None = None,
    anchor_events: Sequence[Mapping[str, object]] | None = None,
) -> list[dict[str, object]]:
    """校验结构并按口播速率尽量扩展片段；无法扩展时记录软告警。"""

    if not isinstance(items, list) or not items:
        raise _validation_error("SCRIPT_ITEMS_INVALID")
    source_order = [source.source_asset_id for source in sources]
    if len(source_order) != len(set(source_order)):
        raise _validation_error("SOURCE_ASSET_ID_DUPLICATED")
    source_by_id = {source.source_asset_id: source for source in sources}
    event_by_id = {
        str(event.get("event_id")): event
        for event in (anchor_events or [])
        if isinstance(event.get("event_id"), str)
    }
    first_seen: list[str] = []
    previous_end: dict[str, float] = {}
    normalized: list[dict[str, object]] = []
    for item_index, raw in enumerate(items):
        if not isinstance(raw, dict):
            raise _validation_error("SCRIPT_ITEM_INVALID", item_index=item_index)
        required = {"source_asset_id", "start", "end", "narration"}
        if not required <= raw.keys():
            raise _validation_error(
                "SCRIPT_FIELDS_INVALID",
                item_index=item_index,
                missing_fields=sorted(required - raw.keys()),
            )
        source_id = raw["source_asset_id"]
        narration = raw["narration"]
        if not isinstance(source_id, str) or source_id not in source_by_id:
            raise _validation_error(
                "SCRIPT_SOURCE_UNKNOWN",
                item_index=item_index,
                source_asset_id=str(source_id)[:128],
            )
        if not isinstance(narration, str) or not narration.strip():
            raise _validation_error(
                "SCRIPT_NARRATION_EMPTY", item_index=item_index
            )
        if type(raw["start"]) not in (int, float) or type(raw["end"]) not in (
            int,
            float,
        ):
            raise _validation_error("SCRIPT_TIME_INVALID", item_index=item_index)
        start, end = as_float(raw["start"]), as_float(raw["end"])
        if not math.isfinite(start) or not math.isfinite(end):
            raise _validation_error("SCRIPT_TIME_INVALID", item_index=item_index)
        if start < 0 or end <= start:
            raise _validation_error(
                "SCRIPT_TIME_INVALID", item_index=item_index, start=start, end=end
            )
        duration = source_by_id[source_id].duration_seconds
        if duration is not None and end > duration:
            raise _validation_error(
                "SCRIPT_TIME_EXCEEDS_SOURCE",
                item_index=item_index,
                source_asset_id=source_id,
                end=end,
                source_duration=duration,
            )
        if start < previous_end.get(source_id, 0.0):
            raise _validation_error(
                "SCRIPT_TIMELINE_UNORDERED",
                item_index=item_index,
                source_asset_id=source_id,
                start=start,
                previous_end=previous_end.get(source_id, 0.0),
            )
        previous_end[source_id] = end
        if source_id not in first_seen:
            first_seen.append(source_id)
        item = {key: raw[key] for key in PUBLIC_TIMELINE_FIELDS if key in raw}
        item["start"], item["end"], item["narration"] = start, end, narration.strip()
        if "visual_anchor" in item:
            anchor = item["visual_anchor"]
            if (
                type(anchor) not in (int, float)
                or not math.isfinite(as_float(anchor))
                or not start <= as_float(anchor) <= end
            ):
                raise _validation_error(
                    "SCRIPT_VISUAL_ANCHOR_INVALID", item_index=item_index
                )
            item["visual_anchor"] = as_float(anchor)
        if "match_confidence" in item:
            item["match_confidence"] = _confidence(item["match_confidence"])
        if "visual_lead" in item:
            lead = item["visual_lead"]
            if type(lead) not in (int, float) or not -2 <= as_float(lead) <= 2:
                raise _validation_error(
                    "SCRIPT_VISUAL_LEAD_INVALID", item_index=item_index
                )
            item["visual_lead"] = as_float(lead)
        anchor_text = item.get("narration_anchor_text")
        if anchor_text is not None and (
            not isinstance(anchor_text, str) or not anchor_text.strip()
        ):
            raise _validation_error(
                "SCRIPT_NARRATION_ANCHOR_INVALID", item_index=item_index
            )
        if isinstance(anchor_text, str) and anchor_text.strip() not in narration:
            raise _validation_error(
                "SCRIPT_NARRATION_ANCHOR_NOT_FOUND", item_index=item_index
            )
        if "visual_anchor" in item and any(
            key not in item
            for key in ("event_id", "narration_anchor_text", "match_confidence")
        ):
            raise _validation_error(
                "SCRIPT_ANCHOR_FIELDS_INCOMPLETE", item_index=item_index
            )
        # “播放原片_N”是生成契约中的语义标记，不是可朗读的解说正文。
        # 即使模型漏掉 original_sound，也必须在进入编辑器/渲染器前确定性修正。
        if _is_original_sound_marker(narration):
            item["original_sound"] = True
        original_sound = item.get("original_sound") is True
        if event_by_id and not original_sound:
            required_anchor_fields = {
                "event_id", "visual_anchor", "narration_anchor_text", "match_confidence"
            }
            if not required_anchor_fields <= item.keys():
                raise _validation_error(
                    "SCRIPT_ANCHOR_FIELDS_INCOMPLETE", item_index=item_index
                )
            event = event_by_id.get(str(item["event_id"]))
            if (
                event is None
                or event.get("source_asset_id") != source_id
                or type(event.get("anchor_time")) not in (int, float)
                or abs(
                    as_float(event["anchor_time"])
                    - as_float(item["visual_anchor"])
                )
                > 0.05
            ):
                raise _validation_error(
                    "SCRIPT_EVENT_ANCHOR_MISMATCH", item_index=item_index
                )
        if not original_sound:
            segment_duration = end - start
            if narration_chars_per_second is not None:
                char_count = len(re.sub(r"\s+", "", narration))
                max_chars = max(
                    1,
                    math.floor(
                        segment_duration * narration_chars_per_second + 1e-6
                    ),
                )
                if char_count > max_chars:
                    required_end = start + char_count / narration_chars_per_second
                    next_start = next(
                        (
                            as_float(candidate.get("start"))
                            for candidate in items[item_index + 1 :]
                            if isinstance(candidate, dict)
                            and candidate.get("source_asset_id") == source_id
                            and type(candidate.get("start")) in (int, float)
                        ),
                        duration,
                    )
                    boundaries = [
                        value
                        for value in (duration, next_start)
                        if value is not None
                    ]
                    boundary = min(boundaries) if boundaries else required_end
                    if required_end <= boundary + 1e-6:
                        end = required_end
                        item["end"] = end
                        previous_end[source_id] = end
                        max_chars = char_count
                    else:
                        warning = {
                            "code": "SCRIPT_NARRATION_ITEM_TOO_LONG",
                            "item_index": item_index,
                            "source_asset_id": source_id,
                            "start": start,
                            "end": end,
                            "segment_duration": segment_duration,
                            "char_count": char_count,
                            "max_chars": max_chars,
                        }
                        if warnings is not None:
                            warnings.append(warning)
                        logger.warning(
                            "short_drama_narration_item_too_long",
                            extra=warning,
                        )
        normalized.append(item)
    expected_first_seen = [
        source_id for source_id in source_order if source_id in first_seen
    ]
    if first_seen != expected_first_seen:
        # source 数组是唯一排序事实，禁止按文件名、目录或 mtime 重排。
            raise _validation_error(
                "SCRIPT_SOURCE_ORDER_INVALID",
                actual=first_seen,
                expected=expected_first_seen,
            )
    if original_sound_ratio is not None:
        if normalized[0].get("original_sound") is True:
            raise _validation_error(
                "SCRIPT_FIRST_ITEM_MUST_BE_NARRATION", item_index=0
            )
        # 原声比例只用于 LLM 生成参考，不要求输出命中精确片段数量。
    # 总片段时长只用于 LLM 生成参考，不作为确定性失败条件。
    _ = max_total_duration, target_duration_seconds
    return normalized


def _source_from_snapshot(raw: Mapping[str, object]) -> ShortDramaSource:
    artifact = raw.get("subtitle_artifact")
    artifact_url = artifact.get("url") if isinstance(artifact, dict) else None
    return ShortDramaSource(
        source_asset_id=str(raw.get("source_asset_id") or ""),
        video_url=str(raw.get("video_url") or ""),
        video_name=str(raw.get("video_name") or "") or None,
        subtitle_name=str(raw.get("subtitle_name") or "") or None,
        subtitle_url=str(raw.get("subtitle_url") or artifact_url or "") or None,
        duration_seconds=as_float(raw["duration_seconds"])
        if raw.get("duration_seconds") is not None
        else None,
        subtitle_text=str(raw.get("subtitle_text") or "") or None,
        subtitle_is_artifact=isinstance(artifact, dict),
    )


def _public_source_map(
    sources: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    """构造可公开且可精确比较的不可变来源快照。"""

    result: list[dict[str, object]] = []
    for order, raw in enumerate(sources):
        item: dict[str, object] = {
            "source_asset_id": raw.get("source_asset_id"),
            "order": order,
            "video_url": raw.get("video_url"),
            "duration_seconds": raw.get("duration_seconds"),
        }
        for name_key in ("video_name", "subtitle_name"):
            if raw.get(name_key) is not None:
                item[name_key] = raw.get(name_key)
        if raw.get("subtitle_url") is not None:
            item["subtitle_url"] = raw.get("subtitle_url")
        elif isinstance(raw.get("subtitle_artifact"), Mapping):
            artifact = as_mapping(raw["subtitle_artifact"])
            item["subtitle_artifact"] = {
                "artifact_id": artifact.get("artifact_id"),
                "url": artifact.get("url"),
            }
        elif raw.get("subtitle_text") is not None:
            item["subtitle_text"] = raw.get("subtitle_text")
        result.append(item)
    return result


def _public_model_snapshot(snapshot: Mapping[str, object]) -> dict[str, object]:
    return {
        key: snapshot[key] for key in ("model_id", "catalog_version") if key in snapshot
    }


def _source_maps_match(
    artifact_value: object, requested: Sequence[Mapping[str, object]]
) -> bool:
    """严格校验必需来源字段；文案请求可省略已冻结的字幕引用。"""

    if not isinstance(artifact_value, list) or not artifact_value:
        return False
    expected = _public_source_map(requested)
    if len(artifact_value) != len(expected):
        return False
    allowed = {
        "source_asset_id",
        "order",
        "video_url",
        "duration_seconds",
        "video_name",
        "subtitle_name",
        "subtitle_url",
        "subtitle_artifact",
        "subtitle_text",
    }
    for artifact, request in zip(artifact_value, expected, strict=True):
        if not isinstance(artifact, Mapping) or not set(artifact) <= allowed:
            return False
        if set(("source_asset_id", "order", "video_url", "duration_seconds")) - set(
            artifact
        ):
            return False
        subtitle_keys = {
            key
            for key in ("subtitle_url", "subtitle_artifact", "subtitle_text")
            if key in artifact
        }
        if len(subtitle_keys) != 1:
            return False
        if "subtitle_url" in artifact and not isinstance(artifact["subtitle_url"], str):
            return False
        if "subtitle_artifact" in artifact:
            subtitle_artifact = artifact["subtitle_artifact"]
            if (
                not isinstance(subtitle_artifact, Mapping)
                or set(subtitle_artifact) != {"artifact_id", "url"}
                or not all(
                    isinstance(value, str) and value
                    for value in subtitle_artifact.values()
                )
            ):
                return False
        if "subtitle_text" in artifact and not isinstance(
            artifact["subtitle_text"], str
        ):
            return False
        for key in ("source_asset_id", "order", "video_url", "duration_seconds"):
            if artifact.get(key) != request.get(key):
                return False
        for key in ("video_name", "subtitle_name"):
            if key in request and artifact.get(key) != request[key]:
                return False
        for key in ("subtitle_url", "subtitle_artifact", "subtitle_text"):
            if key in request and artifact.get(key) != request[key]:
                return False
    return True


def _resolve_source_snapshots(
    artifact_value: object, requested: Sequence[Mapping[str, object]]
) -> list[dict[str, object]]:
    """以请求基础映射为准，并继承 analysis 冻结的可选字幕来源。"""

    if not _source_maps_match(artifact_value, requested):
        raise ShortDramaInputError("ANALYSIS_ARTIFACT_INVALID")
    assert isinstance(artifact_value, list)
    resolved: list[dict[str, object]] = []
    for artifact, request in zip(artifact_value, requested, strict=True):
        assert isinstance(artifact, Mapping)
        item = dict(request)
        for key in ("video_name", "subtitle_name"):
            if key not in item and key in artifact:
                item[key] = artifact[key]
        if not any(
            key in item
            for key in ("subtitle_url", "subtitle_artifact", "subtitle_text")
        ):
            for key in ("subtitle_url", "subtitle_artifact", "subtitle_text"):
                if key in artifact:
                    item[key] = artifact[key]
                    break
        resolved.append(item)
    return resolved


def _safe_analysis(value: object, source_order: Sequence[str]) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise ProviderResponseError("PROVIDER_RESPONSE_INVALID")
    title = str(value.get("title") or "").strip()[:200]
    summary = str(value.get("summary") or "").strip()
    raw_scenes = value.get("scenes", [])
    if (
        not summary
        or not isinstance(raw_scenes, Sequence)
        or isinstance(raw_scenes, (str, bytes))
    ):
        raise ProviderResponseError("PROVIDER_RESPONSE_INVALID")
    source_ids = set(source_order)
    scenes: list[dict[str, str]] = []
    for raw in raw_scenes:
        if not isinstance(raw, Mapping):
            raise ProviderResponseError("PROVIDER_RESPONSE_INVALID")
        source_id = raw.get("source_asset_id")
        scene_summary = raw.get("summary")
        if (
            not isinstance(source_id, str)
            or source_id not in source_ids
            or not isinstance(scene_summary, str)
            or not scene_summary.strip()
        ):
            raise ProviderResponseError("PROVIDER_RESPONSE_INVALID")
        scenes.append(
            {"source_asset_id": source_id, "summary": scene_summary.strip()[:1000]}
        )
    first_seen: list[str] = []
    for scene in scenes:
        if scene["source_asset_id"] not in first_seen:
            first_seen.append(scene["source_asset_id"])
    expected = [source_id for source_id in source_order if source_id in first_seen]
    if first_seen != expected:
        raise ProviderResponseError("PROVIDER_RESPONSE_INVALID")
    result: dict[str, object] = {"title": title, "summary": summary, "scenes": scenes}
    characters = value.get("characters")
    events = value.get("events")
    if isinstance(characters, list) and all(isinstance(item, str) for item in characters):
        result["characters"] = [item.strip()[:120] for item in characters if item.strip()]
    if isinstance(events, list):
        safe_events: list[dict[str, object]] = []
        event_ids: set[str] = set()
        for raw in events:
            if not isinstance(raw, Mapping):
                raise ProviderResponseError("PROVIDER_RESPONSE_INVALID")
            source_id = raw.get("source_asset_id")
            if not isinstance(source_id, str) or source_id not in source_ids:
                raise ProviderResponseError("PROVIDER_RESPONSE_INVALID")
            event = _safe_video_event(raw, duration_seconds=None)
            event_id = str(event["event_id"])
            if event_id in event_ids:
                raise ProviderResponseError("PROVIDER_RESPONSE_INVALID")
            event_ids.add(event_id)
            event["source_asset_id"] = source_id
            safe_events.append(event)
        result["events"] = safe_events
    return result


def _bounded_text(value: object, *, maximum: int = 4_000) -> str:
    if not isinstance(value, str):
        raise ProviderResponseError("PROVIDER_RESPONSE_INVALID")
    return value.strip()[:maximum]


def _confidence(value: object) -> float:
    if type(value) not in (int, float):
        raise ProviderResponseError("PROVIDER_RESPONSE_INVALID")
    number = as_float(value)
    if not math.isfinite(number) or not 0 <= number <= 1:
        raise ProviderResponseError("PROVIDER_RESPONSE_INVALID")
    return number


def _safe_audio_understanding(
    value: object,
    *,
    language: str,
    duration_seconds: float | None,
) -> dict[str, object]:
    if not isinstance(value, Mapping) or not isinstance(value.get("segments"), list):
        raise ProviderResponseError("PROVIDER_RESPONSE_INVALID")
    previous_end = 0.0
    segments: list[dict[str, object]] = []
    for raw in value["segments"]:
        if not isinstance(raw, Mapping):
            raise ProviderResponseError("PROVIDER_RESPONSE_INVALID")
        start, end = raw.get("start"), raw.get("end")
        if type(start) not in (int, float) or type(end) not in (int, float):
            raise ProviderResponseError("PROVIDER_RESPONSE_INVALID")
        start_f, end_f = as_float(start), as_float(end)
        if (
            not math.isfinite(start_f)
            or not math.isfinite(end_f)
            or start_f < previous_end
            or end_f <= start_f
            or (duration_seconds is not None and end_f > duration_seconds + 0.5)
        ):
            raise ProviderResponseError("PROVIDER_RESPONSE_INVALID")
        text = _bounded_text(raw.get("text"))
        if not text:
            raise ProviderResponseError("PROVIDER_RESPONSE_INVALID")
        segments.append({
            "start": start_f,
            "end": end_f,
            "speaker": _bounded_text(raw.get("speaker", ""), maximum=120),
            "text": text,
            "emotion": _bounded_text(raw.get("emotion", ""), maximum=120),
            "confidence": _confidence(raw.get("confidence")),
        })
        previous_end = end_f
    full_text = _bounded_text(value.get("full_text"), maximum=100_000)
    if not segments or not full_text:
        raise ProviderResponseError("PROVIDER_RESPONSE_INVALID")
    return {
        "language": _bounded_text(value.get("language") or language, maximum=32),
        "full_text": full_text,
        "segments": segments,
    }


def _safe_video_event(
    value: Mapping[str, object], *, duration_seconds: float | None
) -> dict[str, object]:
    numeric: dict[str, float] = {}
    for key in (
        "start_time", "anchor_time", "end_time", "recommended_clip_start",
        "recommended_clip_end",
    ):
        raw = value.get(key)
        if type(raw) not in (int, float) or not math.isfinite(as_float(raw)):
            raise ProviderResponseError("PROVIDER_RESPONSE_INVALID")
        numeric[key] = as_float(raw)
    if not (
        0
        <= numeric["recommended_clip_start"]
        <= numeric["start_time"]
        <= numeric["anchor_time"]
        <= numeric["end_time"]
        <= numeric["recommended_clip_end"]
    ):
        raise ProviderResponseError("PROVIDER_RESPONSE_INVALID")
    if duration_seconds is not None and max(numeric.values()) > duration_seconds + 0.5:
        raise ProviderResponseError("PROVIDER_RESPONSE_INVALID")
    characters = value.get("characters")
    if not isinstance(characters, list) or not all(
        isinstance(item, str) for item in characters
    ):
        raise ProviderResponseError("PROVIDER_RESPONSE_INVALID")
    event_id = _bounded_text(value.get("event_id"), maximum=160)
    action = _bounded_text(value.get("action"))
    visual_evidence = _bounded_text(value.get("visual_evidence"))
    if not event_id or not action or not visual_evidence:
        raise ProviderResponseError("PROVIDER_RESPONSE_INVALID")
    return {
        "event_id": event_id,
        **numeric,
        "characters": [item.strip()[:120] for item in characters if item.strip()],
        "action": action,
        "emotion": _bounded_text(value.get("emotion"), maximum=120),
        "dialogue": _bounded_text(value.get("dialogue")),
        "visual_evidence": visual_evidence,
        "audio_evidence": _bounded_text(value.get("audio_evidence")),
        "importance": _confidence(value.get("importance")),
        "confidence": _confidence(value.get("confidence")),
    }


def _safe_video_understanding(
    value: object, *, duration_seconds: float | None
) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise ProviderResponseError("PROVIDER_RESPONSE_INVALID")
    characters = value.get("characters")
    events = value.get("events")
    if (
        not isinstance(characters, list)
        or not all(isinstance(item, str) for item in characters)
        or not isinstance(events, list)
        or not events
    ):
        raise ProviderResponseError("PROVIDER_RESPONSE_INVALID")
    safe_events = [
        _safe_video_event(item, duration_seconds=duration_seconds)
        for item in events
        if isinstance(item, Mapping)
    ]
    if len(safe_events) != len(events):
        raise ProviderResponseError("PROVIDER_RESPONSE_INVALID")
    previous = -1.0
    event_ids: set[str] = set()
    for event in safe_events:
        if as_float(event["start_time"]) < previous:
            raise ProviderResponseError("PROVIDER_RESPONSE_INVALID")
        event_id = str(event["event_id"])
        if event_id in event_ids:
            raise ProviderResponseError("PROVIDER_RESPONSE_INVALID")
        event_ids.add(event_id)
        previous = as_float(event["start_time"])
    summary = _bounded_text(value.get("summary"), maximum=20_000)
    if not summary:
        raise ProviderResponseError("PROVIDER_RESPONSE_INVALID")
    return {
        "summary": summary,
        "characters": [item.strip()[:120] for item in characters if item.strip()],
        "events": safe_events,
    }


def _srt_timestamp(seconds: float) -> str:
    milliseconds = max(0, round(seconds * 1000))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1_000)
    return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"


def _segments_to_srt(segments: Sequence[Mapping[str, object]]) -> str:
    blocks = []
    for index, segment in enumerate(segments, 1):
        blocks.append(
            f"{index}\n{_srt_timestamp(as_float(segment['start']))} --> "
            f"{_srt_timestamp(as_float(segment['end']))}\n{segment['text']}"
        )
    return "\n\n".join(blocks) + "\n"


@dataclass(slots=True)
class ShortDramaAdapter:
    """执行显式来源的分析、文案、一次修复、校验与 JSON Artifact 上传。"""

    provider: ShortDramaProvider
    downloader: Downloader | None = None
    artifact_store: ArtifactStore | None = None
    artifact_downloader: Downloader | None = None
    validation_warnings: list[dict[str, object]] = field(
        default_factory=list, init=False
    )

    @staticmethod
    def _validation_failure(
        error: ScriptValidationError,
        *,
        stage: str,
        items: Sequence[Mapping[str, object]],
    ) -> ScriptValidationError:
        """附加有界阶段和时间线摘要，避免只留下无法定位的总错误码。"""

        preview = [
            {
                key: (
                    str(item.get(key))[:500]
                    if isinstance(item.get(key), str)
                    else item.get(key)
                )
                for key in PUBLIC_TIMELINE_FIELDS
                if key in item
            }
            for item in items[:50]
        ]
        return ScriptValidationError(
            error.reason,
            details=error.details,
            diagnostics={
                "stage": stage,
                "item_count": len(items),
                "items": preview,
                "truncated": len(items) > len(preview),
            },
        )

    def generate_script(
        self,
        *,
        analysis: Mapping[str, object],
        sources: Sequence[ShortDramaSource],
        language: str = "zh-CN",
        config: Mapping[str, object] | None = None,
    ) -> list[dict[str, object]]:
        """固定执行生成、匹配、完整校验、至多一次修复和再次完整校验。"""

        frozen_config = dict(config or {})
        self.validation_warnings.clear()
        validator_options: dict[str, object] = {
            "narration_chars_per_second": 5.0,
            "warnings": self.validation_warnings,
            "anchor_events": (
                analysis.get("events")
                if isinstance(analysis.get("events"), list)
                else []
            ),
        }
        if "original_sound_ratio" in frozen_config:
            validator_options["original_sound_ratio"] = as_int(
                frozen_config["original_sound_ratio"]
            )
        if frozen_config.get("target_duration_seconds") is not None:
            validator_options["target_duration_seconds"] = as_float(
                frozen_config["target_duration_seconds"]
            )
        generated = self.provider.generate_script(
            analysis, sources=sources, language=language, config=frozen_config
        )
        try:
            matched = self.provider.match_script(generated, sources=sources)
        except ProviderResponseError as first_error:
            repaired = self.provider.repair_script(
                generated,
                validation_errors=[first_error.code],
                sources=sources,
            )
            repaired_normalized = normalize_short_drama_timeline_items(repaired)
            try:
                return validate_timeline(
                    repaired_normalized, sources, **validator_options
                )
            except ScriptValidationError as final_error:
                raise self._validation_failure(
                    final_error,
                    stage="repair_after_provider_output_error",
                    items=repaired_normalized,
                ) from final_error
        normalized = normalize_short_drama_timeline_items(matched)
        try:
            return validate_timeline(normalized, sources, **validator_options)
        except ScriptValidationError as first_error:
            # 首答无效只调用一次 repair；repair 后必须重新执行同一完整 validator。
            repaired = self.provider.repair_script(
                matched,
                validation_errors=[str(first_error)],
                sources=sources,
            )
            repaired_normalized = normalize_short_drama_timeline_items(repaired)
            try:
                return validate_timeline(
                    repaired_normalized, sources, **validator_options
                )
            except ScriptValidationError as final_error:
                raise self._validation_failure(
                    final_error,
                    stage="repair_after_timeline_validation",
                    items=repaired_normalized,
                ) from final_error

    def run_audio_understanding(
        self,
        *,
        sources: Sequence[Mapping[str, object]],
        source_order: Sequence[str],
        model_id: str,
        model_snapshot: Mapping[str, object],
        language: str,
        config_snapshot: Mapping[str, object],
        workspace: CoreTaskWorkspace,
        core_task_id: str,
        attempt_no: int,
        lease_guard: Callable[[], None] | None = None,
    ) -> dict[str, object]:
        """按素材各调用一次方舟，直接理解公网视频中的内嵌音轨。"""

        del model_id
        parsed_sources = [_source_from_snapshot(item) for item in sources]
        if [item.source_asset_id for item in parsed_sources] != list(source_order):
            raise ShortDramaInputError("SOURCE_ORDER_MISMATCH")
        if config_snapshot.get("fps") != 1:
            raise ShortDramaInputError("SHORT_DRAMA_CONFIG_INVALID")
        understood: list[dict[str, object]] = []
        subtitle_records: list[dict[str, object]] = []
        artifacts: list[dict[str, object]] = []
        if self.artifact_store is None:
            raise ShortDramaInputError("ARTIFACT_STORE_UNAVAILABLE")
        for index, source in enumerate(parsed_sources):
            result = _safe_audio_understanding(
                self.provider.understand_audio(
                    source, language=language, config=config_snapshot
                ),
                language=language,
                duration_seconds=source.duration_seconds,
            )
            understood.append({"source_asset_id": source.source_asset_id, **result})
            srt_path = workspace.controlled_path(
                "output", f"subtitle_{index:04}", "srt"
            )
            srt_path.write_text(
                _segments_to_srt(cast(Sequence[Mapping[str, object]], result["segments"])),
                encoding="utf-8",
            )
            if lease_guard is not None:
                lease_guard()
            artifact = self.artifact_store.upload(
                workspace=workspace,
                local_path=srt_path,
                core_task_id=core_task_id,
                attempt_no=attempt_no,
                kind="subtitle",
                content_type="application/x-subrip; charset=utf-8",
            ).to_dict()
            artifacts.append(artifact)
            subtitle_records.append({
                "source_asset_id": source.source_asset_id,
                "subtitle_name": source.subtitle_name
                or f"{source.video_name or source.source_asset_id}.srt",
                "artifact": artifact,
            })
        payload = {
            "schema_version": "short-drama-audio-understanding.v1",
            "model_snapshot": _public_model_snapshot(model_snapshot),
            "language": language,
            "config_snapshot": dict(config_snapshot),
            "source_order": list(source_order),
            "sources": _public_source_map(sources),
            "results": understood,
        }
        artifacts.append(
            self._write_and_upload(
                payload=payload,
                filename="audio_understanding",
                kind="audio_understanding",
                workspace=workspace,
                core_task_id=core_task_id,
                attempt_no=attempt_no,
                lease_guard=lease_guard,
            )
        )
        return {
            "metadata": {
                "schema_version": payload["schema_version"],
                "source_order": list(source_order),
                "fps": 1,
                "min_frame_tokens": 64,
                "min_frame_tokens_mode": "provider_default",
            },
            "subtitles": subtitle_records,
            "audio_understanding": understood,
            "artifacts": artifacts,
        }
    def run_analysis(
        self,
        *,
        sources: Sequence[Mapping[str, object]],
        source_order: Sequence[str],
        model_id: str,
        model_snapshot: Mapping[str, object],
        language: str,
        config_snapshot: Mapping[str, object],
        workspace: CoreTaskWorkspace,
        core_task_id: str,
        attempt_no: int,
        lease_guard: Callable[[], None] | None = None,
    ) -> dict[str, object]:
        """每个素材仅调用一次公网视频理解并上传完整事件 Artifact。"""

        parsed_sources = [_source_from_snapshot(item) for item in sources]
        if [item.source_asset_id for item in parsed_sources] != list(source_order):
            raise ShortDramaInputError("SOURCE_ORDER_MISMATCH")
        subtitles: list[dict[str, str]] = []
        for index, source in enumerate(parsed_sources):
            if source.subtitle_text:
                text = source.subtitle_text
            else:
                selected_downloader = (
                    self.artifact_downloader
                    if source.subtitle_is_artifact
                    and self.artifact_downloader is not None
                    else self.downloader
                )
                if selected_downloader is None or not source.subtitle_url:
                    raise ShortDramaInputError("SUBTITLE_REQUIRED")
                target = workspace.controlled_path("input", f"subtitle_{index}", "srt")
                selected_downloader.download(
                    source.subtitle_url, target, max_bytes=SRT_MAX_BYTES
                )
                try:
                    subtitle_bytes = target.read_bytes()
                    parse_srt(subtitle_bytes)
                    text = _subtitle_timeline_text(subtitle_bytes)
                except (OSError, UnicodeError, AdapterError) as exc:
                    raise ShortDramaInputError("SUBTITLE_INVALID") from exc
            if not text.strip():
                raise ShortDramaInputError("SUBTITLE_EMPTY")
            subtitles.append(
                {
                    "source_asset_id": source.source_asset_id,
                    "video_name": source.video_name or "",
                    "subtitle_name": source.subtitle_name or "",
                    "subtitle_text": text.strip(),
                }
            )
        scenes: list[dict[str, object]] = []
        characters: list[str] = []
        events: list[dict[str, object]] = []
        for source, subtitle in zip(parsed_sources, subtitles, strict=True):
            understood = _safe_video_understanding(
                self.provider.analyze_video(
                    source,
                    subtitle_text=subtitle["subtitle_text"],
                    language=language,
                    config=config_snapshot,
                ),
                duration_seconds=source.duration_seconds,
            )
            scenes.append({
                "source_asset_id": source.source_asset_id,
                "summary": understood["summary"],
            })
            for character in cast(Sequence[str], understood["characters"]):
                if character not in characters:
                    characters.append(character)
            for event in cast(Sequence[Mapping[str, object]], understood["events"]):
                event_id = str(event["event_id"])
                if not event_id.startswith(f"{source.source_asset_id}:"):
                    event_id = f"{source.source_asset_id}:{event_id}"
                events.append({
                    "source_asset_id": source.source_asset_id,
                    **event,
                    "event_id": event_id,
                })
        summary = "\n\n".join(str(item["summary"]) for item in scenes)
        analysis = _safe_analysis(
            {
                "title": str(config_snapshot.get("short_name") or "短剧分析"),
                "summary": summary,
                "scenes": scenes,
                "characters": characters,
                "events": events,
            },
            [item.source_asset_id for item in parsed_sources],
        )
        payload = {
            # v1 顶层继续兼容已持久化消费者；仅向 analysis 增加 characters/events。
            "schema_version": "short-drama-analysis.v1",
            "model_snapshot": _public_model_snapshot(model_snapshot),
            "language": language,
            "config_snapshot": dict(config_snapshot),
            "source_order": list(source_order),
            "sources": _public_source_map(sources),
            "analysis": analysis,
            "prompt_metadata": plot_analysis_prompt_metadata(),
            "video_sampling": {
                "fps": 1,
                "min_frame_tokens": 64,
                "min_frame_tokens_mode": "provider_default",
            },
        }
        artifact = self._write_and_upload(
            payload=payload,
            filename="analysis",
            kind="analysis",
            workspace=workspace,
            core_task_id=core_task_id,
            attempt_no=attempt_no,
            lease_guard=lease_guard,
        )
        return {
            "metadata": {
                "schema_version": payload["schema_version"],
                "source_order": list(source_order),
            },
            # The Business API projects only this validated public analysis into
            # the Agent conversation. Provider raw responses remain private.
            "analysis": analysis,
            "artifacts": [artifact],
        }

    def run_script_generation(
        self,
        *,
        sources: Sequence[Mapping[str, object]],
        source_order: Sequence[str],
        analysis_artifact: Mapping[str, object],
        model_id: str,
        model_snapshot: Mapping[str, object],
        language: str,
        config_snapshot: Mapping[str, object],
        workspace: CoreTaskWorkspace,
        core_task_id: str,
        attempt_no: int,
        lease_guard: Callable[[], None] | None = None,
    ) -> dict[str, object]:
        """消费显式分析 Artifact 并登记 timeline 与 editor_draft。"""

        parsed_sources = [_source_from_snapshot(item) for item in sources]
        if [item.source_asset_id for item in parsed_sources] != list(source_order):
            raise ShortDramaInputError("SOURCE_ORDER_MISMATCH")
        downloader = self.artifact_downloader or self.downloader
        url = analysis_artifact.get("url")
        if downloader is None or not isinstance(url, str) or not url:
            raise ShortDramaInputError("ANALYSIS_ARTIFACT_REQUIRED")
        target = workspace.controlled_path("input", "analysis", "json")
        downloader.download(url, target, max_bytes=JSON_MAX_BYTES)
        try:
            analysis_payload = json.loads(target.read_text(encoding="utf-8"))
            analysis = analysis_payload["analysis"]
        except (
            OSError,
            UnicodeError,
            json.JSONDecodeError,
            KeyError,
            TypeError,
        ) as exc:
            raise ShortDramaInputError("ANALYSIS_ARTIFACT_INVALID") from exc
        if (
            not isinstance(analysis_payload, Mapping)
            or analysis_payload.get("schema_version")
            not in {"short-drama-analysis.v1", "short-drama-analysis.v2"}
            or analysis_payload.get("source_order") != list(source_order)
            or not isinstance(analysis, Mapping)
        ):
            # 前序 Artifact 必须绑定同一显式 source map，禁止跨顺序误用。
            raise ShortDramaInputError("ANALYSIS_ARTIFACT_INVALID")
        resolved_snapshots = _resolve_source_snapshots(
            analysis_payload.get("sources"), sources
        )
        parsed_sources = [_source_from_snapshot(item) for item in resolved_snapshots]
        resolved_sources: list[ShortDramaSource] = []
        for index, source in enumerate(parsed_sources):
            text = source.subtitle_text
            if not text:
                subtitle_downloader = (
                    self.artifact_downloader
                    if source.subtitle_is_artifact
                    else self.downloader
                )
                if subtitle_downloader is None or not source.subtitle_url:
                    raise ShortDramaInputError("SUBTITLE_REQUIRED")
                subtitle_target = workspace.controlled_path(
                    "input", f"script_subtitle_{index}", "srt"
                )
                subtitle_downloader.download(
                    source.subtitle_url, subtitle_target, max_bytes=SRT_MAX_BYTES
                )
                try:
                    subtitle_bytes = subtitle_target.read_bytes()
                    parse_srt(subtitle_bytes)
                    text = _subtitle_timeline_text(subtitle_bytes)
                except (OSError, UnicodeError, AdapterError) as exc:
                    raise ShortDramaInputError("SUBTITLE_INVALID") from exc
            resolved_sources.append(
                ShortDramaSource(
                    source_asset_id=source.source_asset_id,
                    video_url=source.video_url,
                    video_name=source.video_name,
                    subtitle_name=source.subtitle_name,
                    subtitle_url=source.subtitle_url,
                    duration_seconds=source.duration_seconds,
                    subtitle_text=text.strip(),
                    subtitle_is_artifact=source.subtitle_is_artifact,
                )
            )
        timeline_items = self.generate_script(
            analysis=analysis,
            sources=resolved_sources,
            language=language,
            config=config_snapshot,
        )
        common = {
            "model_snapshot": _public_model_snapshot(model_snapshot),
            "language": language,
            "config_snapshot": dict(config_snapshot),
            "source_order": list(source_order),
            "sources": _public_source_map(resolved_snapshots),
            "diagnostics": {
                "validation_warnings": list(self.validation_warnings),
            },
        }
        timeline = {
            "schema_version": "short-drama-timeline.v1",
            **common,
            "items": timeline_items,
        }
        editor = {
            "schema_version": "short-drama-editor-draft.v1",
            **common,
            "tracks": [{"type": "narration", "items": timeline_items}],
        }
        artifacts = [
            self._write_and_upload(
                payload=timeline,
                filename="timeline",
                kind="timeline",
                workspace=workspace,
                core_task_id=core_task_id,
                attempt_no=attempt_no,
                lease_guard=lease_guard,
            ),
            self._write_and_upload(
                payload=editor,
                filename="editor_draft",
                kind="editor_draft",
                workspace=workspace,
                core_task_id=core_task_id,
                attempt_no=attempt_no,
                lease_guard=lease_guard,
            ),
        ]
        return {
            "metadata": {
                "schema_version": timeline["schema_version"],
                "source_order": list(source_order),
            },
            # Business 在 Core 终态收口事务中必须立即物化可编辑草稿；Artifact
            # 仍用于审计/恢复，但不能要求 Business 在持锁事务内再次下载 OSS。
            "editor_draft": editor,
            "artifacts": artifacts,
        }

    def _write_and_upload(
        self,
        *,
        payload: Mapping[str, object],
        filename: str,
        kind: str,
        workspace: CoreTaskWorkspace,
        core_task_id: str,
        attempt_no: int,
        lease_guard: Callable[[], None] | None,
    ) -> dict[str, object]:
        """确定性序列化有界 JSON，并在不可逆上传前执行租约 fencing。"""

        if self.artifact_store is None:
            raise ShortDramaInputError("ARTIFACT_STORE_UNAVAILABLE")
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        if not encoded or len(encoded) > JSON_MAX_BYTES:
            raise ShortDramaInputError("ARTIFACT_JSON_TOO_LARGE")
        path = workspace.controlled_path("output", filename, "json")
        path.write_bytes(encoded)
        if lease_guard is not None:
            lease_guard()
        return self.artifact_store.upload(
            workspace=workspace,
            local_path=path,
            core_task_id=core_task_id,
            attempt_no=attempt_no,
            kind=kind,
            content_type="application/json; charset=utf-8",
        ).to_dict()


def _subtitle_text(content: bytes) -> str:
    """从已通过 SRT 校验的字节提取纯文本，不保留本地路径。"""

    text = None
    for encoding in ("utf-8-sig", "utf-16", "gb18030"):
        try:
            candidate = content.decode(encoding)
        except UnicodeError:
            continue
        if "\x00" not in candidate:
            text = candidate
            break
    if text is None:
        raise UnicodeError("SRT_ENCODING_INVALID")
    lines = []
    for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        stripped = line.strip()
        if not stripped or stripped.isdigit() or "-->" in stripped:
            continue
        lines.append(stripped)
    return "\n".join(lines)


def _subtitle_timeline_text(content: bytes) -> str:
    """解码并保留 SRT 时间轴，供模型按真实窗口匹配画面。"""

    for encoding in ("utf-8-sig", "utf-16", "gb18030"):
        try:
            candidate = content.decode(encoding)
        except UnicodeError:
            continue
        if "\x00" not in candidate:
            return candidate.replace("\r\n", "\n").replace("\r", "\n").strip()
    raise UnicodeError("SRT_ENCODING_INVALID")


class ProviderAdapterUnavailableError(AdapterError):
    """已启用模型尚无对应生产供应商 Adapter。"""

    code = "PROVIDER_ADAPTER_UNAVAILABLE"


class UnavailableShortDramaProvider:
    """把供应商 Adapter 缺失转成 attempt 内的确定性失败。"""

    @staticmethod
    def _raise() -> NoReturn:
        raise ProviderAdapterUnavailableError("PROVIDER_ADAPTER_UNAVAILABLE")

    def analyze_story(
        self,
        subtitles: Sequence[Mapping[str, str]],
        *,
        language: str,
        config: Mapping[str, object],
    ) -> Mapping[str, object]:
        """拒绝执行未配置的剧情分析。"""
        self._raise()

    def understand_audio(self, source, *, language, config):
        self._raise()

    def analyze_video(self, source, *, subtitle_text, language, config):
        self._raise()

    def generate_script(
        self,
        analysis: Mapping[str, object],
        *,
        sources: Sequence[ShortDramaSource],
        language: str,
        config: Mapping[str, object],
    ) -> object:
        """拒绝执行未配置的文案生成。"""
        self._raise()

    def match_script(
        self, script: object, *, sources: Sequence[ShortDramaSource]
    ) -> object:
        """拒绝执行未配置的画面匹配。"""
        self._raise()

    def repair_script(
        self,
        invalid_script: object,
        *,
        validation_errors: Sequence[str],
        sources: Sequence[ShortDramaSource],
    ) -> object:
        """拒绝执行未配置的文案修复。"""
        self._raise()


# 阿里云 DashScope/MaaS 暴露 OpenAI-compatible Chat Completions；与 openai
# 共用请求局部客户端，不需要注册进程全局 Provider。
SUPPORTED_SHORT_DRAMA_PROVIDERS = frozenset({"openai", "aliyun", "volcengine_ark"})


def short_drama_provider_supported(provider_code: str) -> bool:
    """返回生产 resolver 是否有该供应商的显式装配。"""

    return provider_code == "fake" or provider_code in SUPPORTED_SHORT_DRAMA_PROVIDERS


class NarratoShortDramaProvider:
    """Core 自有短剧 Provider；生产执行使用 attempt 私有模型客户端。"""

    def __init__(
        self,
        *,
        provider_code: str,
        provider_model_code: str,
        api_key: str,
        base_url: str,
        prompt_category: str = "short_drama_narration",
        model_limits: Mapping[str, object] | None = None,
        analyzer_factory: Callable[..., object] | None = None,
        client_factory: Callable[..., object] | None = None,
    ) -> None:
        self.analyzer = (
            analyzer_factory(
                api_key=api_key,
                model=provider_model_code,
                base_url=base_url,
                provider=provider_code,
                prompt_category=prompt_category,
            )
            if analyzer_factory is not None
            else None
        )
        if client_factory is None:

            def client_factory(**kwargs):
                return OpenAI(**kwargs)

        self.client = (
            None
            if self.analyzer is not None
            else client_factory(api_key=api_key, base_url=base_url or None)
        )
        self.provider_model_code = provider_model_code
        self.prompt_category = prompt_category
        self._context: dict[str, object] = {}
        self.model_limits = dict(model_limits or {})
        self.stream_sink: Callable[[str, str, bool], None] | None = None

    def set_stream_sink(
        self, sink: Callable[[str, str, bool], None] | None
    ) -> None:
        """Attach one attempt-scoped sink for public inference snapshots."""

        self.stream_sink = sink

    def _completion(
        self,
        stage: str,
        prompt: str,
        *,
        temperature: float,
        max_tokens: int,
        json_output: bool = False,
        system_prompt: str | None = None,
    ) -> str:
        """使用 attempt 私有 client 与冻结模型执行一次显式 completion。"""

        logger.info(
            "short_drama_completion",
            extra={
                "stage": stage,
                "prompt_length": len(prompt),
                "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
                "model_sha256": hashlib.sha256(
                    self.provider_model_code.encode()
                ).hexdigest(),
            },
        )
        kwargs: dict[str, object] = {
            "model": self.provider_model_code,
            "messages": [
                {
                    "role": "system",
                    "content": system_prompt
                    or "你是 NarratoAI 短剧分析与解说助手，严格遵循输入事实。",
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_output:
            kwargs["response_format"] = {"type": "json_object"}
        assert self.client is not None
        client = cast(Any, self.client)
        if self.stream_sink is not None:
            return self._streaming_completion(stage, client, kwargs)
        response = cast(Any, self._call(client.chat.completions.create, **kwargs))
        try:
            content = response.choices[0].message.content
        except (AttributeError, IndexError, TypeError) as exc:
            raise ProviderResponseError("PROVIDER_RESPONSE_INVALID") from exc
        if not isinstance(content, str) or not content.strip():
            raise ProviderResponseError("PROVIDER_RESPONSE_INVALID")
        logger.info(
            "short_drama_completion_succeeded",
            extra={"stage": stage, "response_length": len(content)},
        )
        return content.strip()

    def _structured_multimodal_completion(
        self,
        stage: str,
        *,
        video_url: str,
        prompt: str,
        schema_name: str,
        schema: Mapping[str, object],
        max_tokens: int,
    ) -> Mapping[str, object]:
        """调用方舟 OpenAI-compatible Chat API；不下载或 Base64 化媒体。"""

        if self.client is None or not video_url.startswith("https://"):
            raise ShortDramaInputError("PUBLIC_VIDEO_URL_REQUIRED")
        kwargs: dict[str, object] = {
            "model": self.provider_model_code,
            "messages": [
                {
                    "role": "system",
                    "content": "你是 NarratoAI 短剧多模态理解助手，只依据输入媒体返回事实。",
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "video_url",
                            "video_url": {"url": video_url, "fps": 1},
                        },
                        {"type": "text", "text": prompt},
                    ],
                },
            ],
            "temperature": 0.1,
            "max_tokens": max_tokens,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": schema_name,
                    "strict": True,
                    "schema": dict(schema),
                },
            },
        }
        logger.info(
            "short_drama_multimodal_completion",
            extra={
                "stage": stage,
                "prompt_length": len(prompt),
                "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
                "model_sha256": hashlib.sha256(
                    self.provider_model_code.encode()
                ).hexdigest(),
                "fps": 1,
                "min_frame_tokens": 64,
                "min_frame_tokens_mode": "provider_default",
            },
        )
        client = cast(Any, self.client)
        response = cast(Any, self._call(client.chat.completions.create, **kwargs))
        try:
            content = response.choices[0].message.content
            parsed = json.loads(content)
        except (AttributeError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise ProviderResponseError("PROVIDER_RESPONSE_INVALID") from exc
        if not isinstance(parsed, Mapping):
            raise ProviderResponseError("PROVIDER_RESPONSE_INVALID")
        return parsed

    def _streaming_completion(
        self, stage: str, client: Any, kwargs: dict[str, object]
    ) -> str:
        """Stream provider tokens while persisting only bounded public drafts."""

        assert self.stream_sink is not None
        public_content = stage in {"analysis", "generation"}
        self.stream_sink(stage, "", False)
        stream = cast(
            Any,
            self._call(client.chat.completions.create, **kwargs, stream=True),
        )
        chunks: list[str] = []
        emitted_length = 0
        last_emitted_at = time.monotonic()
        try:
            for chunk in stream:
                try:
                    delta = chunk.choices[0].delta.content
                except (AttributeError, IndexError, TypeError):
                    delta = None
                if not isinstance(delta, str) or not delta:
                    continue
                chunks.append(delta)
                if not public_content:
                    continue
                content = "".join(chunks)
                now = time.monotonic()
                if now - last_emitted_at >= 0.25 or len(content) - emitted_length >= 256:
                    self.stream_sink(stage, content, False)
                    emitted_length = len(content)
                    last_emitted_at = now
        except Exception as exc:
            self._raise_failure(exc)
        finally:
            close = getattr(stream, "close", None)
            if callable(close):
                close()
        content = "".join(chunks).strip()
        if not content:
            raise ProviderResponseError("PROVIDER_RESPONSE_INVALID")
        self.stream_sink(stage, content if public_content else "", True)
        logger.info(
            "short_drama_completion_succeeded",
            extra={"stage": stage, "response_length": len(content)},
        )
        return content

    @staticmethod
    def _status_code(value: object) -> int | None:
        if isinstance(value, Mapping):
            raw = value.get("status_code")
            return raw if type(raw) is int else None
        raw = getattr(value, "status_code", None)
        if type(raw) is int:
            return raw
        raw = getattr(getattr(value, "response", None), "status_code", None)
        return raw if type(raw) is int else None

    @classmethod
    def _raise_failure(cls, failure: object) -> NoReturn:
        current = failure
        messages: list[str] = []
        seen: set[int] = set()
        while current is not None and id(current) not in seen:
            seen.add(id(current))
            messages.append(str(current))
            status_code = cls._status_code(current)
            if status_code in {408, 429} or (
                status_code is not None and status_code >= 500
            ):
                raise ProviderTemporaryError("PROVIDER_TEMPORARY_FAILURE")
            if status_code is not None and 400 <= status_code < 500:
                raise ProviderResponseError("PROVIDER_RESPONSE_INVALID")
            if isinstance(
                current,
                (
                    httpx.TimeoutException,
                    httpx.NetworkError,
                    requests.Timeout,
                    requests.ConnectionError,
                ),
            ):
                raise ProviderTemporaryError("PROVIDER_TEMPORARY_FAILURE")
            current = getattr(current, "__cause__", None) or getattr(
                current, "__context__", None
            )
        message = " ".join(messages).lower()
        if any(
            token in message
            for token in (
                "timeout",
                "timed out",
                "rate limit",
                "too many requests",
                "connection",
                "connection reset",
                "network",
                "server error",
                "service unavailable",
                "bad gateway",
                "gateway timeout",
                "429",
                "超时",
                "限流",
                "连接",
                "网络",
                "稍后重试",
                "暂时",
                "服务不可用",
                "上游服务",
            )
        ) or re.search(r"(?<!\d)(500|502|503|504)(?!\d)", message):
            raise ProviderTemporaryError("PROVIDER_TEMPORARY_FAILURE")
        raise ProviderResponseError("PROVIDER_RESPONSE_INVALID")

    @classmethod
    def _call(cls, method: Callable[..., object], *args, **kwargs) -> object:
        try:
            return method(*args, **kwargs)
        except (ProviderTemporaryError, ProviderResponseError):
            raise
        except Exception as exc:
            cls._raise_failure(exc)

    @classmethod
    def _result(cls, result: object, field: str) -> object:
        if not isinstance(result, Mapping) or result.get("status") != "success":
            cls._raise_failure(result)
        value = result.get(field)
        if value is None:
            raise ProviderResponseError("PROVIDER_RESPONSE_INVALID")
        return value

    @staticmethod
    def _subtitle_content(subtitles: Sequence[Mapping[str, str]]) -> str:
        sections: list[str] = []
        for index, item in enumerate(subtitles, 1):
            header = f"# 视频 {index}"
            video_name = str(item.get("video_name") or "").strip()
            if video_name:
                header += f": {video_name}"
            subtitle_name = str(item.get("subtitle_name") or "").strip()
            if not subtitle_name:
                subtitle_name = f"subtitle_{index}.srt"
            header += f"\n字幕文件: {subtitle_name}"
            sections.append(f"{header}\n{item['subtitle_text']}".strip())
        return "\n\n".join(sections)

    @staticmethod
    def _timeline_contract(sources: Sequence[ShortDramaSource]) -> str:
        source_map = [
            {
                "source_asset_id": source.source_asset_id,
                "source_order": order,
                "duration_seconds": source.duration_seconds,
            }
            for order, source in enumerate(sources)
        ]
        return (
            '输出必须是严格 JSON 对象：{"items":[{'
            '"source_asset_id":"string","start":0.0,"end":1.0,'
            '"narration":"string","picture":"optional string",'
            '"original_sound":false,"event_id":"event id",'
            '"visual_anchor":0.5,"narration_anchor_text":"文案中的锚点短语",'
            '"match_confidence":0.9,"visual_lead":0.15}]}。'
            "items 必须为非空数组；source_asset_id 必须来自 source map；"
            "start/end 必须是有限数，start>=0 且 end>start，end 不得超过对应 "
            "duration_seconds；片段必须遵循 source_order，且同来源时间不得重叠或逆序；"
            "narration 必须是非空字符串；每一项都必须显式输出 original_sound 布尔值。"
            "解说项必须绑定输入事件 event_id；visual_anchor 必须处于 start/end 内；"
            "narration_anchor_text 必须是 narration 中原样出现的短语；"
            "match_confidence 是 0 到 1，visual_lead 建议 0 到 0.3 秒。"
            f"source map={json.dumps(source_map, ensure_ascii=False, separators=(',', ':'))}"
        )

    @staticmethod
    def _editing_requirements(context: Mapping[str, object]) -> str:
        """把产品约束显式放进匹配和修复提示，避免模型返回整片时间线。"""

        target = context.get("target_duration_seconds")
        target_rule = (
            f"全部片段总时长建议接近 {target} 秒，可根据剧情完整性适当调整；"
            if type(target) in (int, float)
            else ""
        )
        return (
            target_rule
            + "第一项必须是解说片段；解说片段不设固定时长，解说正文按片段时长以每秒约 5 个非空白字符控制，"
            "例如 10 秒片段尽量不超过 50 字；"
            "必须优先按句号、问号、叹号、分号、逗号拆成短片段，禁止用一个片段覆盖整段源视频；"
            f"original_sound=true 的条目数量可参考全部条目的 {context.get('original_sound_ratio', 0)}%，"
            "无需精确命中该比例；"
            "且该条目只播放原片原声、必须显式设置 original_sound=true，"
            "narration 使用“播放原片_N”标识；禁止把“播放原片_N”作为解说正文朗读。"
        )

    def _max_tokens(self, config: Mapping[str, object]) -> int:
        """按冻结模型上限校验每阶段输出 token 配额。"""
        model_limit = self.model_limits.get("max_tokens")
        requested = config.get("max_tokens", model_limit or 4096)
        if type(requested) is not int or requested <= 0:
            raise ShortDramaInputError("SHORT_DRAMA_CONFIG_INVALID")
        if type(model_limit) is int and model_limit > 0 and requested > model_limit:
            raise ShortDramaInputError("SHORT_DRAMA_MAX_TOKENS_EXCEEDED")
        return requested

    def analyze_story(self, subtitles, *, language, config):
        subtitle_content = self._subtitle_content(subtitles)
        max_input_chars = self.model_limits.get("max_input_chars")
        if type(max_input_chars) is int and len(subtitle_content) > max_input_chars:
            raise ShortDramaInputError("SHORT_DRAMA_INPUT_INVALID")
        if self.analyzer is not None:
            raw = self._result(
                self._call(cast(Any, self.analyzer).analyze_subtitle, subtitle_content),
                "analysis",
            )
        else:
            raw = self._completion(
                "analysis",
                render_plot_analysis_prompt(subtitle_content),
                temperature=1.0,
                max_tokens=self._max_tokens(config),
                system_prompt=PLOT_ANALYSIS_SYSTEM_PROMPT,
            )
        summary = validate_plot_analysis_output(
            raw if isinstance(raw, str) else json.dumps(raw, ensure_ascii=False)
        )
        self._context = {"subtitle_content": subtitle_content, "plot_analysis": summary}
        return {
            "title": str(config.get("short_name") or "短剧分析"),
            "summary": summary,
            "scenes": [
                {
                    "source_asset_id": item["source_asset_id"],
                    "summary": item["subtitle_text"][:1000],
                }
                for item in subtitles
            ],
        }

    def understand_audio(self, source, *, language, config):
        prompt = (
            "只识别这个视频的内嵌音频，不要根据画面臆测台词。"
            "按自然语义分段，start/end 使用相对视频开头的秒数；识别说话人、情绪，"
            "confidence 为 0 到 1；full_text 和 segments 必须非空。"
            f"目标语言：{language}。"
        )
        raw = self._structured_multimodal_completion(
            "audio_understanding",
            video_url=source.video_url,
            prompt=prompt,
            schema_name="short_drama_audio_understanding",
            schema=AUDIO_UNDERSTANDING_SCHEMA,
            max_tokens=self._max_tokens(config),
        )
        return raw

    def analyze_video(self, source, *, subtitle_text, language, config):
        prompt = (
            "完整分析这个短剧视频的视觉信息，并结合下方已识别字幕生成语义事件时间线。"
            "每个事件必须给出动作真正发生的 anchor_time、推荐裁剪范围、可核验的视觉证据；"
            "不要把字幕出现时间直接当作视觉锚点。时间均为相对当前视频开头的秒数，"
            "events 按 start_time 升序。每个视频只执行这一次完整分析。\n"
            f"目标语言：{language}\n字幕：\n{subtitle_text[:100_000]}"
        )
        return self._structured_multimodal_completion(
            "video_analysis",
            video_url=source.video_url,
            prompt=prompt,
            schema_name="short_drama_video_understanding",
            schema=VIDEO_UNDERSTANDING_SCHEMA,
            max_tokens=self._max_tokens(config),
        )

    def generate_script(self, analysis, *, sources, language, config):
        plot_analysis = str(analysis.get("summary") or "")
        subtitle_content = "\n\n".join(
            f"[video_id={index}]\n{source.subtitle_text}"
            for index, source in enumerate(sources, 1)
            if source.subtitle_text
        )
        if not subtitle_content:
            subtitle_content = str(self._context.get("subtitle_content") or "")
        if not subtitle_content:
            raise ShortDramaInputError("SUBTITLE_REQUIRED")
        max_input_chars = self.model_limits.get("max_input_chars")
        if type(max_input_chars) is int and len(subtitle_content) > max_input_chars:
            raise ShortDramaInputError("SHORT_DRAMA_INPUT_INVALID")
        drama_genre = str(
            config.get("drama_genre")
            or config.get("narration_style")
            or "逆袭/复仇"
        ).strip()
        target_duration = config.get("target_duration_seconds")
        narration_char_range = str(config.get("narration_char_range") or "")
        if not narration_char_range and type(target_duration) is int:
            narration_char_range = (
                f"{round(target_duration * 4.5)}-{round(target_duration * 5.5)}"
            )
        requirements = str(config.get("requirements") or "").strip()
        kwargs = {
            "short_name": str(config.get("short_name") or "短剧"),
            "plot_analysis": plot_analysis,
            "subtitle_content": subtitle_content,
            "temperature": as_float(config.get("temperature", 0.7)),
            "max_tokens": self._max_tokens(config),
            "narration_language": language,
            "drama_genre": drama_genre,
            "narration_char_range": narration_char_range,
        }
        if self.analyzer is not None:
            narration_copy = self._result(
                self._call(cast(Any, self.analyzer).generate_narration_copy, **kwargs),
                "narration_copy",
            )
        else:
            narration_copy = self._completion(
                "generation",
                "# 短剧解说正文创作任务\n"
                f"语言：{language}\n类型：{drama_genre}\n"
                f"用户要求：{requirements or '无额外要求'}\n"
                f"目标成片时长：{target_duration or '未指定'} 秒\n"
                f"解说字数范围：{narration_char_range or '按剧情合理控制'}\n"
                f"剧情：{plot_analysis}\n"
                "视频语义事件："
                f"{json.dumps(analysis.get('events', []), ensure_ascii=False)}\n"
                f"字幕：\n{subtitle_content}",
                temperature=as_float(config.get("temperature", 0.7)),
                max_tokens=self._max_tokens(config),
            )
        self._context.update(
            kwargs
            | {
                "narration_copy": narration_copy,
                "sources": sources,
                "original_sound_ratio": as_int(config.get("original_sound_ratio", 30)),
                "target_duration_seconds": target_duration,
                "requirements": requirements,
                "visual_events": analysis.get("events", []),
            }
        )
        return narration_copy

    def match_script(self, script, *, sources):
        context = self._context
        if self.analyzer is not None:
            raw = self._result(
                self._call(
                    cast(Any, self.analyzer).match_narration_copy_to_script,
                    short_name=context["short_name"],
                    plot_analysis=context["plot_analysis"],
                    subtitle_content=context["subtitle_content"],
                    narration_copy=str(script),
                    temperature=min(as_float(context["temperature"]), 0.3),
                    narration_language=context["narration_language"],
                    drama_genre=context["drama_genre"],
                    original_sound_ratio=context["original_sound_ratio"],
                ),
                "narration_script",
            )
        else:
            raw = self._completion(
                "matching",
                "# 短剧解说文案画面匹配任务\n"
                f"{self._timeline_contract(sources)}\n"
                f"{self._editing_requirements(context)}\n"
                f"用户要求：{context.get('requirements') or '无额外要求'}\n"
                f"原声比例：{context['original_sound_ratio']}\n"
                "视频语义事件（必须据此选择画面与 visual_anchor）："
                f"{json.dumps(context.get('visual_events', []), ensure_ascii=False)}\n"
                f"字幕：{context['subtitle_content']}\n文案：{script}",
                temperature=min(as_float(context["temperature"]), 0.3),
                max_tokens=as_int(context["max_tokens"]),
                json_output=True,
            )
        return self._bounded_timeline(raw, sources)

    def repair_script(self, invalid_script, *, validation_errors, sources):
        context = self._context
        if self.analyzer is not None:
            raw = self._result(
                self._call(
                    cast(Any, self.analyzer).repair_narration_script,
                    short_name=context["short_name"],
                    plot_analysis=context["plot_analysis"],
                    subtitle_content=context["subtitle_content"],
                    invalid_script=json.dumps(
                        invalid_script, ensure_ascii=False, allow_nan=False
                    ),
                    validation_errors=",".join(validation_errors),
                    temperature=min(as_float(context["temperature"]), 0.3),
                    narration_language=context["narration_language"],
                    drama_genre=context["drama_genre"],
                ),
                "narration_script",
            )
        else:
            raw = self._completion(
                "repair",
                "# 短剧解说脚本修复任务\n"
                f"{self._timeline_contract(sources)}\n"
                f"{self._editing_requirements(context)}\n"
                f"错误：{','.join(validation_errors)}\n"
                "视频语义事件："
                f"{json.dumps(context.get('visual_events', []), ensure_ascii=False)}\n"
                f"字幕：{context['subtitle_content']}\n"
                f"无效结果：{json.dumps(invalid_script, ensure_ascii=False, allow_nan=False)}",
                temperature=min(as_float(context["temperature"]), 0.3),
                max_tokens=as_int(context["max_tokens"]),
                json_output=True,
            )
        return self._bounded_timeline(raw, sources)

    def _bounded_timeline(
        self, raw: object, sources: Sequence[ShortDramaSource]
    ) -> list[dict[str, object]]:
        try:
            timeline = _legacy_script_to_timeline(raw, sources)
        except ProviderResponseError as exc:
            raise ProviderOutputError(raw) from exc
        max_output_items = self.model_limits.get("max_output_items")
        if type(max_output_items) is int and len(timeline) > max_output_items:
            raise ProviderOutputError(raw)
        return timeline


def _timestamp_seconds(value: str) -> tuple[float, float]:
    match = re.fullmatch(
        r"(\d{2}):(\d{2}):(\d{2})[,.](\d{3})-(\d{2}):(\d{2}):(\d{2})[,.](\d{3})",
        value.strip(),
    )
    if match is None:
        raise ProviderResponseError("PROVIDER_RESPONSE_INVALID")
    values = [as_int(value) for value in match.groups()]
    return (
        values[0] * 3600 + values[1] * 60 + values[2] + values[3] / 1000,
        values[4] * 3600 + values[5] * 60 + values[6] + values[7] / 1000,
    )


def _legacy_script_to_timeline(
    raw: object, sources: Sequence[ShortDramaSource]
) -> list[dict[str, object]]:
    try:
        items = json.loads(raw) if isinstance(raw, str) else raw
    except json.JSONDecodeError as exc:
        raise ProviderResponseError("PROVIDER_RESPONSE_INVALID") from exc
    if isinstance(items, Mapping):
        items = items.get("items")
    if not isinstance(items, list):
        raise ProviderResponseError("PROVIDER_RESPONSE_INVALID")
    result = []
    for item in items:
        if not isinstance(item, Mapping):
            raise ProviderResponseError("PROVIDER_RESPONSE_INVALID")
        source_id = item.get("source_asset_id")
        if source_id is None:
            video_id = item.get("video_id")
            if isinstance(video_id, str) and video_id.isdigit():
                video_id = as_int(video_id)
            if type(video_id) is not int or video_id < 1 or video_id > len(sources):
                raise ProviderResponseError("PROVIDER_RESPONSE_INVALID")
            source_id = sources[video_id - 1].source_asset_id
        start: object
        end: object
        if "timestamp" in item:
            start, end = _timestamp_seconds(str(item["timestamp"]))
        else:
            start, end = item.get("start"), item.get("end")
        narration = item.get("narration")
        original_sound = _is_original_sound_marker(narration)
        if "original_sound" in item:
            original_sound = original_sound or item.get("original_sound") is True
        if "OST" in item:
            original_sound = original_sound or _legacy_original_sound(item["OST"])
        result.append(
            {
                "source_asset_id": source_id,
                "start": start,
                "end": end,
                "narration": narration,
                **({"picture": item["picture"]} if "picture" in item else {}),
                **({"original_sound": True} if original_sound else {}),
                **{
                    key: item[key]
                    for key in (
                        "event_id",
                        "visual_anchor",
                        "narration_anchor_text",
                        "match_confidence",
                        "visual_lead",
                    )
                    if key in item
                },
            }
        )
    return result


def create_short_drama_provider(
    provider_code: str,
    *,
    provider_model_code: str = "",
    api_key: str = "",
    base_url: str = "",
    prompt_category: str = "short_drama_narration",
    model_limits: Mapping[str, object] | None = None,
    analyzer_factory: Callable[..., object] | None = None,
    client_factory: Callable[..., object] | None = None,
) -> ShortDramaProvider:
    """按已校验供应商代码创建 Adapter；未知供应商禁止静默回退。"""

    if provider_code == "fake":
        return FakeShortDramaProvider()
    if (
        short_drama_provider_supported(provider_code)
        and provider_model_code
        and api_key
    ):
        return NarratoShortDramaProvider(
            provider_code=provider_code,
            provider_model_code=provider_model_code,
            api_key=api_key,
            base_url=base_url,
            prompt_category=prompt_category,
            model_limits=model_limits,
            analyzer_factory=analyzer_factory,
            client_factory=client_factory,
        )
    return UnavailableShortDramaProvider()
