from __future__ import annotations

import subprocess

import pytest

from app.services import media_probe


def _ffprobe_payload() -> str:
    return """{
      "streams": [{
        "codec_type": "video",
        "codec_name": "h264",
        "width": 1920,
        "height": 1080
      }],
      "format": {"format_name": "mov,mp4,m4a,3gp,3g2,mj2", "duration": "12.345"}
    }"""


def test_probe_media_passes_https_source_directly_to_ffprobe(monkeypatch):
    source_url = "https://cdn.example.test/narrato/api/video.mp4?signature=abc"
    calls: list[list[str]] = []

    monkeypatch.setattr(media_probe, "_ffprobe_binary", lambda: "ffprobe")

    def fake_run(
        command: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, _ffprobe_payload(), "")

    monkeypatch.setattr(media_probe.subprocess, "run", fake_run)

    result = media_probe.probe_media(source_url)

    assert len(calls) == 1
    assert calls[0][0] == "ffprobe"
    assert calls[0][calls[0].index("-probesize") + 1] == "1048576"
    assert calls[0][calls[0].index("-analyzeduration") + 1] == "5000000"
    assert "-show_streams" in calls[0]
    assert "-show_format" in calls[0]
    assert calls[0][-1] == source_url
    assert result.duration_seconds == 12.345
    assert result.container == "mp4"
    assert result.video_codec == "h264"


def test_probe_media_still_rejects_missing_local_file():
    with pytest.raises(media_probe.MediaProbeError, match="媒体文件不存在"):
        media_probe.probe_media("/tmp/narrato-media-probe-does-not-exist.mp4")
