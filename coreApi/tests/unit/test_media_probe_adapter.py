from __future__ import annotations


import pytest

from core_api.adapters.narrato.media_probe import (
    MediaConstraintError,
    SrtConstraintError,
    parse_srt,
    validate_video,
)


class FakeProbe:
    duration_seconds = 600.0
    container = "mp4"
    video_codec = "h264"
    audio_codec = "aac"
    width = 1280
    height = 720
    has_video = True
    has_audio = True


def test_probe_rejects_video_over_ten_minutes():
    probe = FakeProbe()
    probe.duration_seconds = 600.001
    with pytest.raises(MediaConstraintError, match="MEDIA_TOO_LONG"):
        validate_video(probe, declared_extension="mp4")


@pytest.mark.parametrize(
    "changes",
    [
        {"duration_seconds": 0},
        {"has_video": False},
        {"video_codec": None},
        {"width": 0},
        {"container": "matroska"},
    ],
)
def test_probe_rejects_invalid_video_metadata(changes):
    probe = FakeProbe()
    for name, value in changes.items():
        setattr(probe, name, value)
    with pytest.raises(MediaConstraintError):
        validate_video(probe, declared_extension="mp4")


def test_probe_normalizes_valid_video_metadata():
    result = validate_video(FakeProbe(), declared_extension=".MP4")
    assert result == {
        "media_type": "video",
        "duration_seconds": 600.0,
        "container": "mp4",
        "video_codec": "h264",
        "audio_codec": "aac",
        "width": 1280,
        "height": 720,
        "has_audio": True,
    }


def test_srt_parser_returns_normalized_metadata():
    content = "1\n00:00:00,000 --> 00:00:01,250\n第一句\n\n2\n00:00:01,250 --> 00:00:02,000\nSecond\n"
    result = parse_srt(content.encode("utf-8"))
    assert result == {
        "media_type": "subtitle",
        "cue_count": 2,
        "duration_seconds": 2.0,
        "encoding": "utf-8",
    }


@pytest.mark.parametrize(
    "content",
    [
        b"",
        b"not srt",
        b"1\n00:00:02,000 --> 00:00:01,000\nbad\n",
        b"1\n00:00:00,000 --> 00:00:02,000\na\n\n2\n00:00:01,000 --> 00:00:03,000\nb\n",
    ],
)
def test_srt_parser_rejects_empty_or_damaged_timeline(content):
    with pytest.raises(SrtConstraintError):
        parse_srt(content)


def test_srt_parser_rejects_payload_over_five_mibibytes():
    with pytest.raises(SrtConstraintError, match="SRT_SIZE_INVALID"):
        parse_srt(b"x" * (5 * 1024 * 1024 + 1))
