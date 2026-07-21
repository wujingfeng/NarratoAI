from __future__ import annotations

from core_api.type_coercion import as_float, as_int, as_mapping

import json
import hashlib
import logging
import math
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, NoReturn, Protocol, cast

import httpx
import requests
from openai import OpenAI

from core_api.adapters.narrato.media_probe import AdapterError, SRT_MAX_BYTES, parse_srt
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
)

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


class ProviderTemporaryError(AdapterError):
    """供应商网络、限流或短暂故障。"""

    code = "PROVIDER_TEMPORARY_FAILURE"
    retryable = True


class ProviderResponseError(AdapterError):
    """供应商返回确定性无效结构。"""

    code = "PROVIDER_RESPONSE_INVALID"


@dataclass(frozen=True, slots=True)
class ShortDramaSource:
    """一个显式排序的视频、字幕和时长快照。"""

    source_asset_id: str
    video_url: str
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
        self._matched = 0

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
        return [
            {
                "source_asset_id": source.source_asset_id,
                "start": 0.0,
                "end": min(1.5, source.duration_seconds or 1.5),
                "narration": f"{source.source_asset_id} 剧情解说",
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
        if self.repair_result is not None:
            return self.repair_result
        return [
            {
                "source_asset_id": source.source_asset_id,
                "start": 0.0,
                "end": min(1.5, source.duration_seconds or 1.5),
                "narration": f"{source.source_asset_id} 修复后解说",
            }
            for source in sources
        ]


def _validation_error(message: str) -> ScriptValidationError:
    return ScriptValidationError(message)


def validate_timeline(
    items: object, sources: Sequence[ShortDramaSource]
) -> list[dict[str, object]]:
    """校验字段、来源顺序、范围、时长与同源时间线并返回副本。"""

    if not isinstance(items, list) or not items:
        raise _validation_error("SCRIPT_ITEMS_INVALID")
    source_order = [source.source_asset_id for source in sources]
    if len(source_order) != len(set(source_order)):
        raise _validation_error("SOURCE_ASSET_ID_DUPLICATED")
    source_by_id = {source.source_asset_id: source for source in sources}
    first_seen: list[str] = []
    previous_end: dict[str, float] = {}
    normalized: list[dict[str, object]] = []
    for raw in items:
        if not isinstance(raw, dict):
            raise _validation_error("SCRIPT_ITEM_INVALID")
        required = {"source_asset_id", "start", "end", "narration"}
        if not required <= raw.keys():
            raise _validation_error("SCRIPT_FIELDS_INVALID")
        source_id = raw["source_asset_id"]
        narration = raw["narration"]
        if not isinstance(source_id, str) or source_id not in source_by_id:
            raise _validation_error("SCRIPT_SOURCE_UNKNOWN")
        if not isinstance(narration, str) or not narration.strip():
            raise _validation_error("SCRIPT_NARRATION_EMPTY")
        if type(raw["start"]) not in (int, float) or type(raw["end"]) not in (
            int,
            float,
        ):
            raise _validation_error("SCRIPT_TIME_INVALID")
        start, end = as_float(raw["start"]), as_float(raw["end"])
        if not math.isfinite(start) or not math.isfinite(end):
            raise _validation_error("SCRIPT_TIME_INVALID")
        if start < 0 or end <= start:
            raise _validation_error("SCRIPT_TIME_INVALID")
        duration = source_by_id[source_id].duration_seconds
        if duration is not None and end > duration:
            raise _validation_error("SCRIPT_TIME_EXCEEDS_SOURCE")
        if start < previous_end.get(source_id, 0.0):
            raise _validation_error("SCRIPT_TIMELINE_UNORDERED")
        previous_end[source_id] = end
        if source_id not in first_seen:
            first_seen.append(source_id)
        item = {key: raw[key] for key in PUBLIC_TIMELINE_FIELDS if key in raw}
        item["start"], item["end"], item["narration"] = start, end, narration.strip()
        normalized.append(item)
    expected_first_seen = [
        source_id for source_id in source_order if source_id in first_seen
    ]
    if first_seen != expected_first_seen:
        # source 数组是唯一排序事实，禁止按文件名、目录或 mtime 重排。
        raise _validation_error("SCRIPT_SOURCE_ORDER_INVALID")
    return normalized


def _source_from_snapshot(raw: Mapping[str, object]) -> ShortDramaSource:
    artifact = raw.get("subtitle_artifact")
    artifact_url = artifact.get("url") if isinstance(artifact, dict) else None
    return ShortDramaSource(
        source_asset_id=str(raw.get("source_asset_id") or ""),
        video_url=str(raw.get("video_url") or ""),
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
    summary = str(value.get("summary") or "").strip()[:5000]
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
    return {"title": title, "summary": summary, "scenes": scenes}


@dataclass(slots=True)
class ShortDramaAdapter:
    """执行显式来源的分析、文案、一次修复、校验与 JSON Artifact 上传。"""

    provider: ShortDramaProvider
    downloader: Downloader | None = None
    artifact_store: ArtifactStore | None = None
    artifact_downloader: Downloader | None = None

    def generate_script(
        self,
        *,
        analysis: Mapping[str, object],
        sources: Sequence[ShortDramaSource],
        language: str = "zh-CN",
        config: Mapping[str, object] | None = None,
    ) -> list[dict[str, object]]:
        """固定执行生成、匹配、完整校验、至多一次修复和再次完整校验。"""

        generated = self.provider.generate_script(
            analysis, sources=sources, language=language, config=config or {}
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
            return validate_timeline(repaired_normalized, sources)
        normalized = normalize_short_drama_timeline_items(matched)
        try:
            return validate_timeline(normalized, sources)
        except ScriptValidationError as first_error:
            # 首答无效只调用一次 repair；repair 后必须重新执行同一完整 validator。
            repaired = self.provider.repair_script(
                matched,
                validation_errors=[first_error.code],
                sources=sources,
            )
            repaired_normalized = normalize_short_drama_timeline_items(repaired)
            return validate_timeline(repaired_normalized, sources)

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
        """读取显式字幕、生成安全分析 JSON 并上传 Artifact。"""

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
                    text = _subtitle_text(subtitle_bytes)
                except (OSError, UnicodeError, AdapterError) as exc:
                    raise ShortDramaInputError("SUBTITLE_INVALID") from exc
            if not text.strip():
                raise ShortDramaInputError("SUBTITLE_EMPTY")
            subtitles.append(
                {
                    "source_asset_id": source.source_asset_id,
                    "subtitle_text": text.strip(),
                }
            )
        analysis = _safe_analysis(
            self.provider.analyze_story(
                subtitles, language=language, config=config_snapshot
            ),
            [item.source_asset_id for item in parsed_sources],
        )
        payload = {
            "schema_version": "short-drama-analysis.v1",
            "model_snapshot": _public_model_snapshot(model_snapshot),
            "language": language,
            "config_snapshot": dict(config_snapshot),
            "source_order": list(source_order),
            "sources": _public_source_map(sources),
            "analysis": analysis,
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
            or analysis_payload.get("schema_version") != "short-drama-analysis.v1"
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
                    text = _subtitle_text(subtitle_bytes)
                except (OSError, UnicodeError, AdapterError) as exc:
                    raise ShortDramaInputError("SUBTITLE_INVALID") from exc
            resolved_sources.append(
                ShortDramaSource(
                    source_asset_id=source.source_asset_id,
                    video_url=source.video_url,
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


SUPPORTED_SHORT_DRAMA_PROVIDERS = frozenset({"openai"})


def short_drama_provider_supported(provider_code: str) -> bool:
    """返回生产 resolver 是否有该供应商的显式装配。"""

    return provider_code == "fake" or provider_code in SUPPORTED_SHORT_DRAMA_PROVIDERS


class NarratoShortDramaProvider:
    """将统一 Core 协议薄适配到仓库既有 SubtitleAnalyzerAdapter。"""

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

    def _completion(
        self,
        stage: str,
        prompt: str,
        *,
        temperature: float,
        max_tokens: int,
        json_output: bool = False,
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
                    "content": "你是 NarratoAI 短剧分析与解说助手，严格遵循输入事实。",
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
        return "\n\n".join(
            f"[video_id={index}]\n{item['subtitle_text']}"
            for index, item in enumerate(subtitles, 1)
        )

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
            '"original_sound":"optional boolean"}]}。'
            "items 必须为非空数组；source_asset_id 必须来自 source map；"
            "start/end 必须是有限数，start>=0 且 end>start，end 不得超过对应 "
            "duration_seconds；片段必须遵循 source_order，且同来源时间不得重叠或逆序；"
            "narration 必须是非空字符串。"
            f"source map={json.dumps(source_map, ensure_ascii=False, separators=(',', ':'))}"
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
                f"剧情分析\n语言：{language}\n提示类别：{self.prompt_category}\n字幕：\n{subtitle_content}",
                temperature=as_float(config.get("temperature", 0.7)),
                max_tokens=self._max_tokens(config),
            )
        summary = raw if isinstance(raw, str) else json.dumps(raw, ensure_ascii=False)
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
        drama_genre = str(config.get("drama_genre") or "逆袭/复仇")
        narration_style = str(config.get("narration_style") or "").strip()
        if narration_style:
            drama_genre = f"{drama_genre}；风格：{narration_style}"
        kwargs = {
            "short_name": str(config.get("short_name") or "短剧"),
            "plot_analysis": plot_analysis,
            "subtitle_content": subtitle_content,
            "temperature": as_float(config.get("temperature", 0.7)),
            "max_tokens": self._max_tokens(config),
            "narration_language": language,
            "drama_genre": drama_genre,
            "narration_char_range": str(config.get("narration_char_range") or ""),
        }
        if self.analyzer is not None:
            narration_copy = self._result(
                self._call(cast(Any, self.analyzer).generate_narration_copy, **kwargs),
                "narration_copy",
            )
        else:
            narration_copy = self._completion(
                "generation",
                "生成解说正文\n"
                f"语言：{language}\n类型：{drama_genre}\n"
                f"剧情：{plot_analysis}\n字幕：\n{subtitle_content}",
                temperature=as_float(config.get("temperature", 0.7)),
                max_tokens=self._max_tokens(config),
            )
        self._context.update(
            kwargs
            | {
                "narration_copy": narration_copy,
                "sources": sources,
                "original_sound_ratio": as_int(config.get("original_sound_ratio", 30)),
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
                f"匹配画面。{self._timeline_contract(sources)}\n"
                f"原声比例：{context['original_sound_ratio']}\n"
                f"字幕：{context['subtitle_content']}\n文案：{script}",
                temperature=as_float(context["temperature"]),
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
                f"修复脚本。{self._timeline_contract(sources)}\n"
                f"错误：{','.join(validation_errors)}\n"
                f"字幕：{context['subtitle_content']}\n"
                f"无效结果：{json.dumps(invalid_script, ensure_ascii=False, allow_nan=False)}",
                temperature=as_float(context["temperature"]),
                max_tokens=as_int(context["max_tokens"]),
                json_output=True,
            )
        return self._bounded_timeline(raw, sources)

    def _bounded_timeline(
        self, raw: object, sources: Sequence[ShortDramaSource]
    ) -> list[dict[str, object]]:
        timeline = _legacy_script_to_timeline(raw, sources)
        max_output_items = self.model_limits.get("max_output_items")
        if type(max_output_items) is int and len(timeline) > max_output_items:
            raise ProviderResponseError("PROVIDER_RESPONSE_INVALID")
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
            if type(video_id) is not int or video_id < 1 or video_id > len(sources):
                raise ProviderResponseError("PROVIDER_RESPONSE_INVALID")
            source_id = sources[video_id - 1].source_asset_id
        start: object
        end: object
        if "timestamp" in item:
            start, end = _timestamp_seconds(str(item["timestamp"]))
        else:
            start, end = item.get("start"), item.get("end")
        result.append(
            {
                "source_asset_id": source_id,
                "start": start,
                "end": end,
                "narration": item.get("narration"),
                **({"picture": item["picture"]} if "picture" in item else {}),
                **({"original_sound": bool(item["OST"])} if "OST" in item else {}),
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
