from __future__ import annotations

from dataclasses import dataclass

import pytest

from narrato_api.editor.render_snapshot import (
    RenderSnapshotError,
    editor_draft_from_script,
    render_snapshot_from_draft,
)


@dataclass
class Asset:
    id: str
    cdn_url: str
    duration_seconds: float


def test_script_timeline_materializes_non_empty_editor_draft_and_render_snapshot() -> None:
    assets = [Asset("a", "https://cdn.example/a.mp4", 30), Asset("b", "https://cdn.example/b.mp4", 20)]
    draft = editor_draft_from_script(
        timeline=[
            {
                "source_asset_id": "a",
                "start": 2,
                "end": 8,
                "narration": "第一段解说",
                "picture": "人物进入房间",
                "original_sound": False,
            },
            {
                "source_asset_id": "b",
                "start": 1,
                "end": 5,
                "narration": "播放原片1",
                "picture": "人物原声对白",
                "original_sound": True,
            },
        ],
        assets=assets,
        voice_id="voice-1",
        background_music={"asset_id": "bgm", "cdn_url": "https://cdn.example/bgm.mp3", "volume": 64},
        subtitle_style="经典白色",
        video_ratio="9:16",
    )
    assert [clip["text"] for clip in draft["clips"] if clip["track_id"] == "script"] == ["第一段解说", "播放原片1"]
    script_clips = [clip for clip in draft["clips"] if clip["track_id"] == "script"]
    assert [(clip["picture"], clip["original_sound"]) for clip in script_clips] == [
        ("人物进入房间", False),
        ("人物原声对白", True),
    ]
    assert [cue["region_id"] for cue in draft["subtitles"]] == [
        "script-0001",
        "script-0002",
    ]
    snapshot = render_snapshot_from_draft(
        content=draft,
        assets=assets,
        narration_settings={"voice_id": "voice-1", "subtitle_style": "经典白色", "video_ratio": "9:16"},
        background_music={"asset_id": "bgm", "cdn_url": "https://cdn.example/bgm.mp3", "volume": 64},
    )
    assert snapshot["sources"] == [
        {"source_asset_id": "a", "video_url": "https://cdn.example/a.mp4"},
        {"source_asset_id": "b", "video_url": "https://cdn.example/b.mp4"},
    ]
    assert snapshot["timeline"] == [
        {"source_asset_id": "a", "start": 2.0, "end": 8.0, "narration": "第一段解说", "subtitle": "第一段解说", "original_sound": False},
        {"source_asset_id": "b", "start": 1.0, "end": 5.0, "narration": "播放原片1", "subtitle": "播放原片1", "original_sound": True},
    ]
    assert snapshot["render_config"]["background_music"]["volume"] == 64
    assert snapshot["render_config"]["background_music"]["audio_url"] == "https://cdn.example/bgm.mp3"
    assert snapshot["render_config"] | {"background_music": None} == {
        "video_ratio": "9:16",
        "subtitle_style": "经典白色",
        "voice_volume": 100,
        "voice_rate": 1.0,
        "original_sound_volume": 100,
        "source_subtitle_layouts": {},
        "narration_subtitle_position": {"y": 0.82, "font_scale": 0.9},
        "background_music": None,
    }


def test_original_sound_marker_restores_legacy_script_audio_semantics() -> None:
    assets = [Asset("a", "https://cdn.example/a.mp4", 30)]
    draft = editor_draft_from_script(
        timeline=[
            {
                "source_asset_id": "a",
                "start": 0,
                "end": 3,
                "narration": "普通解说",
            },
            {
                "source_asset_id": "a",
                "start": 3,
                "end": 6,
                "narration": "播放原片_1",
                "original_sound": False,
            },
        ],
        assets=assets,
        voice_id="voice-1",
    )

    script_clips = [clip for clip in draft["clips"] if clip["track_id"] == "script"]
    assert script_clips[1]["original_sound"] is True

    # 同时覆盖已经落库、但 original_sound=false 的历史编辑草稿。
    script_clips[1]["original_sound"] = False
    snapshot = render_snapshot_from_draft(
        content=draft,
        assets=assets,
        narration_settings={"voice_id": "voice-1"},
    )

    assert snapshot["timeline"][1]["original_sound"] is True
    assert snapshot["render_config"]["original_sound_volume"] == 100


def test_render_snapshot_uses_edited_first_seen_source_order_and_only_used_assets() -> None:
    assets = [
        Asset("a", "https://cdn.example/a.mp4", 30),
        Asset("b", "https://cdn.example/b.mp4", 20),
        Asset("unused", "https://cdn.example/unused.mp4", 10),
    ]
    draft = editor_draft_from_script(
        timeline=[
            {"source_asset_id": "a", "start": 2, "end": 8, "narration": "A"},
            {"source_asset_id": "b", "start": 1, "end": 5, "narration": "B"},
        ],
        assets=assets,
        voice_id="voice-1",
    )
    draft["subtitles"][0]["text"] = "A 的人工字幕"
    draft["subtitles"][1]["text"] = "B 的人工字幕"
    # 模拟多轨编辑器只移动 video clip；字幕数组仍保持原始顺序。
    for clip in draft["clips"]:
        if clip.get("track_id") != "video":
            continue
        if clip.get("region_id") == "script-0001":
            clip["start"] = 4
        elif clip.get("region_id") == "script-0002":
            clip["start"] = 0

    snapshot = render_snapshot_from_draft(
        content=draft,
        assets=assets,
        narration_settings={"voice_id": "voice-1"},
    )

    assert [item["source_asset_id"] for item in snapshot["sources"]] == ["b", "a"]
    assert [item["source_asset_id"] for item in snapshot["timeline"]] == ["b", "a"]
    assert [item["subtitle"] for item in snapshot["timeline"]] == [
        "B 的人工字幕",
        "A 的人工字幕",
    ]
    assert draft["settings"]["video_ratio"] == "16:9"
    assert draft["settings"]["subtitle_style"] == "经典白色"


def test_legacy_subtitles_fall_back_to_clip_start_then_sorted_position() -> None:
    assets = [
        Asset("a", "https://cdn.example/a.mp4", 30),
        Asset("b", "https://cdn.example/b.mp4", 20),
    ]
    content = {
        "clips": [
            {
                "track_id": "video",
                "start": 3,
                "duration": 3,
                "source_start": 0,
                "asset_id": "a",
                "region_id": "a-region",
            },
            {
                "track_id": "script",
                "start": 0,
                "duration": 3,
                "text": "A 解说",
                "region_id": "a-region",
            },
            {
                "track_id": "video",
                "start": 0,
                "duration": 3,
                "source_start": 0,
                "asset_id": "b",
                "region_id": "b-region",
            },
            {
                "track_id": "script",
                "start": 3,
                "duration": 3,
                "text": "B 解说",
                "region_id": "b-region",
            },
        ],
        # 旧草稿没有 region_id；先按 start 对齐当前 clip，不能直接沿数组下标串行。
        "subtitles": [
            {"start": 3, "end": 6, "text": "位置三字幕"},
            {"start": 0, "end": 3, "text": "位置零字幕"},
        ],
    }

    snapshot = render_snapshot_from_draft(
        content=content,
        assets=assets,
        narration_settings={"voice_id": "voice-1"},
    )

    assert [item["subtitle"] for item in snapshot["timeline"]] == [
        "位置零字幕",
        "位置三字幕",
    ]


def test_legacy_draft_defaults_metadata_and_explicit_original_volume_is_respected() -> None:
    content = {
        "clips": [
            {
                "track_id": "video",
                "start": 0,
                "duration": 3,
                "source_start": 0,
                "asset_id": "a",
                "region_id": "r",
            },
            {
                "track_id": "script",
                "start": 0,
                "duration": 3,
                "text": "旧草稿解说",
                "region_id": "r",
            },
        ],
        # 旧版生成器曾把缺省配置写成空串；冻结时必须收敛为 Core 合法默认值。
        "settings": {"video_ratio": "", "subtitle_style": ""},
    }
    snapshot = render_snapshot_from_draft(
        content=content,
        assets=[Asset("a", "https://cdn.example/a.mp4", 30)],
        narration_settings={"voice_id": "voice-1", "original_sound_volume": 23},
    )
    assert snapshot["timeline"][0]["original_sound"] is False
    assert snapshot["render_config"]["original_sound_volume"] == 23
    assert snapshot["render_config"]["video_ratio"] == "16:9"
    assert snapshot["render_config"]["subtitle_style"] == "经典白色"

    content["clips"][1]["original_sound"] = True
    original_snapshot = render_snapshot_from_draft(
        content=content,
        assets=[Asset("a", "https://cdn.example/a.mp4", 30)],
        narration_settings={"voice_id": "voice-1", "original_sound_volume": 23},
    )
    assert original_snapshot["timeline"][0]["original_sound"] is True
    assert original_snapshot["render_config"]["original_sound_volume"] == 23


def test_render_snapshot_rejects_blank_script_text() -> None:
    with pytest.raises(RenderSnapshotError, match="requires narration"):
        render_snapshot_from_draft(
            content={"clips": [{"track_id": "video", "start": 0, "duration": 3, "source_start": 0, "asset_id": "a", "region_id": "r"}]},
            assets=[Asset("a", "https://cdn.example/a.mp4", 30)],
            narration_settings={"voice_id": "voice-1"},
        )


def test_render_snapshot_preserves_valid_alignment_and_drops_stale_trimmed_anchor() -> None:
    assets = [Asset("a", "https://cdn.example/a.mp4", 30)]
    draft = editor_draft_from_script(
        timeline=[
            {
                "source_asset_id": "a",
                "start": 2,
                "end": 8,
                "narration": "他推门后发现了真相",
                "event_id": "a:event-1",
                "visual_anchor": 6,
                "narration_anchor_text": "发现了真相",
                "match_confidence": 0.92,
                "visual_lead": 0.3,
                "narration_start_offset": 1.2,
            }
        ],
        assets=assets,
        voice_id="voice-1",
    )

    snapshot = render_snapshot_from_draft(
        content=draft,
        assets=assets,
        narration_settings={"voice_id": "voice-1"},
    )
    assert snapshot["timeline"][0] | {"subtitle": None} == {
        "source_asset_id": "a",
        "start": 2.0,
        "end": 8.0,
        "narration": "他推门后发现了真相",
        "subtitle": None,
        "original_sound": False,
        "event_id": "a:event-1",
        "visual_anchor": 6.0,
        "narration_anchor_text": "发现了真相",
        "match_confidence": 0.92,
        "visual_lead": 0.3,
        "narration_start_offset": 1.2,
    }

    # 用户修剪画面后旧视觉锚点落在区间外：冻结快照应整体降级，不阻断渲染。
    video_clip = next(clip for clip in draft["clips"] if clip["track_id"] == "video")
    video_clip["source_start"] = 2
    video_clip["duration"] = 3
    stale_snapshot = render_snapshot_from_draft(
        content=draft,
        assets=assets,
        narration_settings={"voice_id": "voice-1"},
    )
    for key in (
        "event_id",
        "visual_anchor",
        "narration_anchor_text",
        "match_confidence",
        "visual_lead",
        "narration_start_offset",
    ):
        assert key not in stale_snapshot["timeline"][0]
