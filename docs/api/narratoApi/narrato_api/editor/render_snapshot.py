"""编辑草稿与 Core 渲染请求之间的唯一转换契约。"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from typing import Any


DEFAULT_VIDEO_RATIO = "16:9"
DEFAULT_SUBTITLE_STYLE = "经典白色"
_ORIGINAL_SOUND_MARKER = re.compile(r"^\s*播放原片(?:[_\-\s]*\d+)?\s*$")


class RenderSnapshotError(ValueError):
    """草稿无法安全转换为最终渲染快照。"""


def _is_original_sound_marker(value: object) -> bool:
    """兜底识别历史脚本中的原片播放标记。"""

    return isinstance(value, str) and _ORIGINAL_SOUND_MARKER.fullmatch(value) is not None


def _number(value: object, *, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RenderSnapshotError(f"{field} must be a finite number")
    number = float(value)
    if not math.isfinite(number):
        raise RenderSnapshotError(f"{field} must be a finite number")
    return number


def _ready_assets(assets: Sequence[object]) -> dict[str, Mapping[str, object]]:
    result: dict[str, Mapping[str, object]] = {}
    for asset in assets:
        asset_id = getattr(asset, "id", None)
        cdn_url = getattr(asset, "cdn_url", None)
        duration = getattr(asset, "duration_seconds", None)
        if not isinstance(asset_id, str) or not asset_id or not isinstance(cdn_url, str) or not cdn_url:
            continue
        if isinstance(duration, bool) or not isinstance(duration, (int, float)) or duration <= 0:
            continue
        result[asset_id] = {"id": asset_id, "cdn_url": cdn_url, "duration_seconds": float(duration)}
    return result


def editor_draft_from_script(
    *,
    timeline: Sequence[object],
    assets: Sequence[object],
    voice_id: str,
    background_music: Mapping[str, object] | None = None,
    subtitle_style: str | None = None,
    video_ratio: str | None = None,
) -> dict[str, Any]:
    """将 Core 已验证脚本转换为前端编辑器草稿，绝不制造空解说片段。"""

    by_id = _ready_assets(assets)
    clips: list[dict[str, object]] = []
    subtitles: list[dict[str, object]] = []
    cursor = 0.0
    for index, raw in enumerate(timeline, start=1):
        if not isinstance(raw, Mapping):
            raise RenderSnapshotError("script timeline item is invalid")
        asset_id = raw.get("source_asset_id")
        narration = raw.get("narration")
        if not isinstance(asset_id, str) or asset_id not in by_id:
            raise RenderSnapshotError("script timeline references an unavailable source")
        if not isinstance(narration, str) or not narration.strip():
            raise RenderSnapshotError("script timeline narration is required")
        source_start = _number(raw.get("start"), field="timeline.start")
        source_end = _number(raw.get("end"), field="timeline.end")
        asset = by_id[asset_id]
        asset_duration = asset["duration_seconds"]
        if not isinstance(asset_duration, float):
            raise RenderSnapshotError("script timeline source duration is invalid")
        duration = asset_duration
        if source_start < 0 or source_end <= source_start or source_end > duration + 0.02:
            raise RenderSnapshotError("script timeline range is invalid")
        clip_duration = source_end - source_start
        region_id = f"script-{index:04}"
        picture = raw.get("picture")
        original_sound = (
            raw.get("original_sound") is True
            or _is_original_sound_marker(narration)
        )
        clips.extend((
            {
                "id": f"video-{index:04}", "track_id": "video", "start": cursor,
                "duration": clip_duration, "source_start": source_start, "asset_id": asset_id,
                "asset_url": asset["cdn_url"], "region_id": region_id,
            },
            {
                "id": f"script-{index:04}", "track_id": "script", "start": cursor,
                "duration": clip_duration, "text": narration.strip(), "region_id": region_id,
                "picture": picture.strip() if isinstance(picture, str) else "",
                "original_sound": original_sound,
                **{
                    key: raw[key]
                    for key in (
                        "event_id",
                        "visual_anchor",
                        "narration_anchor_text",
                        "match_confidence",
                        "visual_lead",
                        "narration_start_offset",
                    )
                    if key in raw
                },
            },
        ))
        subtitles.append({
            "start": cursor,
            "end": cursor + clip_duration,
            "text": narration.strip(),
            "region_id": region_id,
        })
        cursor += clip_duration
    if not clips:
        raise RenderSnapshotError("script timeline must not be empty")

    settings: dict[str, object] = {
        "voice_role": voice_id,
        "volume": 100,
        "rate": 1,
        "subtitle_style": subtitle_style or DEFAULT_SUBTITLE_STYLE,
        "video_ratio": video_ratio or DEFAULT_VIDEO_RATIO,
    }
    if background_music:
        asset_id = background_music.get("asset_id")
        asset_url = background_music.get("cdn_url")
        volume = background_music.get("volume")
        if isinstance(asset_id, str) and isinstance(asset_url, str) and asset_id and asset_url:
            clips.append({
                "id": f"bgm-{asset_id}", "track_id": "bgm", "start": 0,
                "duration": cursor, "source_start": 0, "asset_id": asset_id,
                "asset_url": asset_url, "region_id": f"bgm-{asset_id}",
            })
            background_music_setting: dict[str, object] = {
                "asset_id": asset_id, "cdn_url": asset_url,
                "volume": int(volume) if isinstance(volume, int) and not isinstance(volume, bool) else 50,
            }
            filename = background_music.get("filename")
            if isinstance(filename, str) and filename:
                background_music_setting["filename"] = filename
            settings["background_music"] = background_music_setting
    return {"version": 1, "clips": clips, "subtitles": subtitles, "settings": settings}


def render_snapshot_from_draft(
    *, content: Mapping[str, object], assets: Sequence[object], narration_settings: Mapping[str, object], background_music: Mapping[str, object] | None = None,
) -> dict[str, Any]:
    """冻结编辑器草稿为 Core `/video-render/tasks` 的规范输入。"""

    raw_clips = content.get("clips")
    if not isinstance(raw_clips, list):
        raise RenderSnapshotError("editor draft clips are required")
    by_id = _ready_assets(assets)
    raw_subtitles = content.get("subtitles")
    subtitles = raw_subtitles if isinstance(raw_subtitles, list) else []
    raw_editor_settings = content.get("settings")
    editor_settings = (
        raw_editor_settings if isinstance(raw_editor_settings, Mapping) else {}
    )
    scripts: dict[str, dict[str, object]] = {}
    videos: list[Mapping[str, object]] = []
    for raw in raw_clips:
        if not isinstance(raw, Mapping):
            continue
        track_id = raw.get("track_id")
        region_id = raw.get("region_id")
        if track_id == "script" and isinstance(region_id, str) and isinstance(raw.get("text"), str):
            scripts[region_id] = {
                "text": str(raw["text"]).strip(),
                "picture": (
                    str(raw["picture"]).strip()
                    if isinstance(raw.get("picture"), str)
                    else ""
                ),
                "original_sound": (
                    raw.get("original_sound") is True
                    or _is_original_sound_marker(raw.get("text"))
                ),
                **{
                    key: raw[key]
                    for key in (
                        "event_id",
                        "visual_anchor",
                        "narration_anchor_text",
                        "match_confidence",
                        "visual_lead",
                        "narration_start_offset",
                    )
                    if key in raw
                },
            }
        elif track_id == "video":
            videos.append(raw)
    # New drafts carry the segment identity on every cue.  Keep legacy cues in
    # a separate pool so a malformed/mismatched new identity can never steal a
    # subtitle from another region by positional fallback.
    subtitles_by_region: dict[str, Mapping[str, object]] = {}
    legacy_subtitles: list[tuple[int, Mapping[str, object]]] = []
    for subtitle_index, raw_subtitle in enumerate(subtitles):
        if not isinstance(raw_subtitle, Mapping):
            continue
        subtitle_region_id = raw_subtitle.get("region_id")
        if isinstance(subtitle_region_id, str) and subtitle_region_id:
            subtitles_by_region.setdefault(subtitle_region_id, raw_subtitle)
        else:
            legacy_subtitles.append((subtitle_index, raw_subtitle))

    def legacy_subtitle_start(item: tuple[int, Mapping[str, object]]) -> float:
        value = item[1].get("start")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return math.inf
        number = float(value)
        return number if math.isfinite(number) else math.inf

    legacy_subtitles.sort(key=lambda item: (legacy_subtitle_start(item), item[0]))
    claimed_legacy_subtitles: set[int] = set()

    timeline: list[dict[str, object]] = []
    for raw in sorted(
        videos, key=lambda item: _number(item.get("start"), field="clip.start")
    ):
        asset_id = raw.get("asset_id")
        region_id = raw.get("region_id")
        if not isinstance(asset_id, str) or asset_id not in by_id or not isinstance(region_id, str):
            raise RenderSnapshotError("editor video clip is invalid")
        script = scripts.get(region_id, {})
        narration = str(script.get("text") or "")
        if not narration:
            raise RenderSnapshotError("each render video clip requires narration")
        source_start = _number(raw.get("source_start", 0), field="clip.source_start")
        duration = _number(raw.get("duration"), field="clip.duration")
        source_end = source_start + duration
        source = by_id[asset_id]
        source_duration = source["duration_seconds"]
        if not isinstance(source_duration, float):
            raise RenderSnapshotError("editor video source duration is invalid")
        if source_start < 0 or duration <= 0 or source_end > source_duration + 0.02:
            raise RenderSnapshotError("editor video clip range is invalid")
        subtitle = narration
        matched_subtitle = subtitles_by_region.get(region_id)
        if matched_subtitle is None:
            clip_start = _number(raw.get("start"), field="clip.start")
            legacy_match = next(
                (
                    item
                    for item in legacy_subtitles
                    if item[0] not in claimed_legacy_subtitles
                    and abs(legacy_subtitle_start(item) - clip_start) < 0.02
                ),
                None,
            )
            if legacy_match is None:
                legacy_match = next(
                    (
                        item
                        for item in legacy_subtitles
                        if item[0] not in claimed_legacy_subtitles
                    ),
                    None,
                )
            if legacy_match is not None:
                claimed_legacy_subtitles.add(legacy_match[0])
                matched_subtitle = legacy_match[1]
        if matched_subtitle is not None:
            candidate = matched_subtitle.get("text")
            if isinstance(candidate, str) and candidate.strip():
                subtitle = candidate.strip()
        original_sound = (
            script.get("original_sound") is True
            or _is_original_sound_marker(narration)
        )
        anchor_text = script.get("narration_anchor_text")
        visual_anchor = script.get("visual_anchor")
        confidence = script.get("match_confidence")
        event_id = script.get("event_id")
        anchor_valid = (
            not original_sound
            and isinstance(anchor_text, str)
            and bool(anchor_text.strip())
            and anchor_text.strip() in narration
            and isinstance(event_id, str)
            and bool(event_id.strip())
            and type(visual_anchor) in (int, float)
            and math.isfinite(float(visual_anchor))
            and source_start <= float(visual_anchor) <= source_end
            and type(confidence) in (int, float)
            and math.isfinite(float(confidence))
            and 0 <= float(confidence) <= 1
        )
        alignment: dict[str, object] = {}
        if anchor_valid:
            alignment = {
                "event_id": event_id,
                "visual_anchor": float(visual_anchor),
                "narration_anchor_text": anchor_text.strip(),
                "match_confidence": float(confidence),
            }
            lead = script.get("visual_lead")
            if type(lead) in (int, float) and math.isfinite(float(lead)):
                alignment["visual_lead"] = float(lead)
            offset = script.get("narration_start_offset")
            if (
                type(offset) in (int, float)
                and math.isfinite(float(offset))
                and float(offset) >= 0
            ):
                alignment["narration_start_offset"] = float(offset)
        timeline.append({
            "source_asset_id": asset_id,
            "start": source_start,
            "end": source_end,
            "narration": narration,
            "subtitle": subtitle,
            "original_sound": original_sound,
            **alignment,
        })
    if not timeline:
        raise RenderSnapshotError("editor draft has no renderable timeline")
    voice_id = editor_settings.get("voice_role") or narration_settings.get("voice_id")
    if not isinstance(voice_id, str) or not voice_id.strip():
        raise RenderSnapshotError("voice_id is required")
    volume = editor_settings.get("volume", 100)
    rate = editor_settings.get("rate", 1.0)
    if (
        isinstance(volume, bool)
        or not isinstance(volume, (int, float))
        or not 0 <= float(volume) <= 100
    ):
        raise RenderSnapshotError("editor voice volume is invalid")
    if (
        isinstance(rate, bool)
        or not isinstance(rate, (int, float))
        or not 0.5 <= float(rate) <= 2.0
    ):
        raise RenderSnapshotError("editor voice rate is invalid")
    original_sound_volume = narration_settings.get(
        "original_sound_volume",
        100 if any(item["original_sound"] is True for item in timeline) else 0,
    )
    if (
        isinstance(original_sound_volume, bool)
        or not isinstance(original_sound_volume, (int, float))
        or not 0 <= float(original_sound_volume) <= 100
    ):
        raise RenderSnapshotError("original sound volume is invalid")
    render_config: dict[str, object] = {
        "video_ratio": (
            narration_settings.get("video_ratio")
            or editor_settings.get("video_ratio")
            or DEFAULT_VIDEO_RATIO
        ),
        "subtitle_style": (
            narration_settings.get("subtitle_style")
            or editor_settings.get("subtitle_style")
            or DEFAULT_SUBTITLE_STYLE
        ),
        "voice_volume": int(round(float(volume))),
        "voice_rate": float(rate),
        "original_sound_volume": int(round(float(original_sound_volume))),
        "source_subtitle_layouts": narration_settings.get("source_subtitle_layouts") or {},
        "narration_subtitle_position": narration_settings.get("narration_subtitle_position") or {"y": 0.82, "font_scale": 0.9},
    }
    if background_music:
        asset_id = background_music.get("asset_id")
        audio_url = background_music.get("cdn_url") or background_music.get("audio_url")
        bgm_volume = background_music.get("volume", 50)
        if (
            not isinstance(asset_id, str)
            or not asset_id
            or not isinstance(audio_url, str)
            or not audio_url
            or isinstance(bgm_volume, bool)
            or not isinstance(bgm_volume, (int, float))
            or not 0 <= float(bgm_volume) <= 100
        ):
            raise RenderSnapshotError("background music is invalid")
        render_config["background_music"] = {
            "asset_id": asset_id,
            "audio_url": audio_url,
            "volume": int(round(float(bgm_volume))),
        }
    return {
        "voice_id": voice_id,
        "sources": [
            {"source_asset_id": asset_id, "video_url": by_id[asset_id]["cdn_url"]}
            for asset_id in dict.fromkeys(
                str(item["source_asset_id"]) for item in timeline
            )
        ],
        "timeline": timeline,
        "render_config": render_config,
    }
