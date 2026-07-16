import json
import math

import pytest

from core_api.adapters.narrato.jianying import JianyingBuilder, JianyingInputError


def fixture():
    resources = []
    extensions = {"video": "mp4", "subtitle": "srt", "voice": "wav", "timeline": "json"}
    content_types = {
        "video": "video/mp4",
        "subtitle": "application/x-subrip",
        "voice": "audio/wav",
        "timeline": "application/json",
    }
    for kind, extension in extensions.items():
        resources.append(
            {
                "kind": kind,
                "zip_path": f"assets/{kind}/final.{extension}",
                "url": f"https://cdn.example.test/narrato/coreApi/{kind}.{extension}",
                "size": 10,
                "checksum": "sha256:" + "a" * 64,
                "content_type": content_types[kind],
                **(
                    {"width": 640, "height": 360, "duration": 1.0}
                    if kind == "video"
                    else {}
                ),
            }
        )
    return {
        "snapshot_id": "revision_1",
        "timeline": [
            {"source_asset_id": "asset_a", "start": 0, "end": 1, "narration": "A"}
        ],
        "resources": resources,
    }


def test_jianying_builder_generates_protected_base_files_without_zip(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    manifest = JianyingBuilder().build(**fixture())
    assert manifest.package_name == "NarratoAI_revision_1.zip"
    assert manifest.template_version == "10.6.0"
    base = {item.zip_path: item.content for item in manifest.files if item.content}
    assert {
        "draft_info.json",
        "draft_meta_info.json",
        "draft_settings",
        "template.tmp",
        "template-2.tmp",
        "attachment_editing.json",
        "common_attachment/attachment_pc_timeline.json",
    } <= set(base)
    content = json.loads(base["draft_info.json"])
    assert content["name"] == "NarratoAI_revision_1"
    assert len(content["materials"]) == 54
    assert [track["type"] for track in content["tracks"]] == [
        "video",
        "audio",
        "text",
    ]
    assert content["materials"]["videos"][0]["path"].endswith("/assets/video/final.mp4")
    assert content["tracks"][0]["segments"][0]["target_timerange"] == {
        "start": 0,
        "duration": 1_000_000,
    }
    assert any(
        item.zip_path == "draft_cover.jpg" and item.content_base64
        for item in manifest.files
    )
    assert list(tmp_path.rglob("*.zip")) == []


@pytest.mark.parametrize("zip_path", ["../x", "/x", "a\\b"])
def test_jianying_rejects_unsafe_zip_paths(zip_path):
    body = fixture()
    body["resources"][0]["zip_path"] = zip_path
    with pytest.raises(JianyingInputError):
        JianyingBuilder().build(**body)


def test_jianying_rejects_duplicates_private_urls_and_incomplete_resources():
    body = fixture()
    body["resources"][1]["zip_path"] = body["resources"][0]["zip_path"]
    with pytest.raises(JianyingInputError):
        JianyingBuilder().build(**body)
    body = fixture()
    body["resources"][0]["url"] = "http://127.0.0.1/x"
    with pytest.raises(JianyingInputError):
        JianyingBuilder().build(**body)
    body = fixture()
    body["resources"].pop()
    with pytest.raises(JianyingInputError):
        JianyingBuilder().build(**body)


@pytest.mark.parametrize(
    ("kind", "zip_path", "content_type"),
    [
        ("video", "draft_info.json", "video/mp4"),
        ("video", "assets/video/final.json", "video/mp4"),
        ("video", "assets/video/final.mp4", "application/json"),
        ("voice", "assets/video/voice.wav", "audio/wav"),
        ("subtitle", "assets/subtitle/final.txt", "application/x-subrip"),
        ("timeline", "assets/timeline/final.json", "text/plain"),
    ],
)
def test_jianying_rejects_protected_or_disguised_resource_paths(
    kind, zip_path, content_type
):
    body = fixture()
    resource = next(item for item in body["resources"] if item["kind"] == kind)
    resource["zip_path"] = zip_path
    resource["content_type"] = content_type
    with pytest.raises(JianyingInputError):
        JianyingBuilder().build(**body)


def test_jianying_requires_video_metadata_and_uses_it_for_canvas():
    body = fixture()
    video = next(item for item in body["resources"] if item["kind"] == "video")
    video.pop("width")
    with pytest.raises(JianyingInputError):
        JianyingBuilder().build(**body)

    body = fixture()
    video = next(item for item in body["resources"] if item["kind"] == "video")
    video.update(width=854, height=480, duration=3.25)
    manifest = JianyingBuilder().build(**body)
    draft = json.loads(
        next(
            item.content
            for item in manifest.files
            if item.zip_path == "draft_info.json"
        )
    )
    assert draft["canvas_config"]["width"] == 854
    assert draft["canvas_config"]["height"] == 480
    assert draft["materials"]["videos"][0]["duration"] == 3_250_000


def test_jianying_references_subtitle_timeline_and_has_real_text_track():
    manifest = JianyingBuilder().build(**fixture())
    inline = {
        item.zip_path: item.content
        for item in manifest.files
        if item.content is not None
    }
    draft = json.loads(inline["draft_info.json"])
    assert {track["type"] for track in draft["tracks"]} == {"video", "audio", "text"}
    assert draft["materials"]["texts"]
    attachment = json.loads(inline["common_attachment/attachment_script_video.json"])
    assert attachment["narrato_resources"] == {
        "subtitle": "assets/subtitle/final.srt",
        "timeline": "assets/timeline/final.json",
    }
    meta = json.loads(inline["draft_meta_info.json"])
    assert {item["metetype"] for item in meta["draft_materials"][0]["value"]} == {
        "video",
        "music",
    }


@pytest.mark.parametrize(
    "checksum", ["sha256:x", "sha256:" + "A" * 64, "sha256:" + "z" * 64, " md5:x"]
)
def test_jianying_rejects_invalid_checksum(checksum):
    body = fixture()
    body["resources"][0]["checksum"] = checksum
    with pytest.raises(JianyingInputError):
        JianyingBuilder().build(**body)


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_jianying_rejects_non_finite_timeline(value):
    body = fixture()
    body["timeline"][0]["start"] = value
    with pytest.raises(JianyingInputError):
        JianyingBuilder().build(**body)


def test_jianying_rejects_overlapping_or_unordered_timeline():
    body = fixture()
    body["timeline"].append(
        {"source_asset_id": "asset_b", "start": 0.5, "end": 2, "narration": "B"}
    )
    with pytest.raises(JianyingInputError):
        JianyingBuilder().build(**body)


def test_jianying_rejects_inline_template_over_five_mib():
    body = fixture()
    body["timeline"] = [
        {
            "source_asset_id": f"asset_{index}",
            "start": index,
            "end": index + 1,
            "narration": "字" * 10_000,
        }
        for index in range(600)
    ]
    with pytest.raises(JianyingInputError, match="TOO_LARGE"):
        JianyingBuilder().build(**body)
