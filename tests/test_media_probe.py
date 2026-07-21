import subprocess
import sys
from types import SimpleNamespace

import pytest

from app.services.media_probe import MediaProbeError, probe_media


@pytest.fixture
def sample_mp4(tmp_path):
    output = tmp_path / "sample.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=black:s=64x48:d=0.2",
            "-an",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-y",
            str(output),
        ],
        check=True,
    )
    return output


def test_probe_media_returns_normalized_metadata(sample_mp4):
    info = probe_media(str(sample_mp4))

    assert info.duration_seconds > 0
    assert info.container == "mp4"
    assert info.width > 0 and info.height > 0
    assert info.video_codec == "h264"
    assert info.has_video is True
    assert info.has_audio is False


def test_probe_media_raises_clear_error_for_missing_file(tmp_path):
    with pytest.raises(MediaProbeError, match="媒体文件不存在"):
        probe_media(str(tmp_path / "missing.mp4"))


def test_probe_media_accepts_https_source_without_local_file(monkeypatch):
    from app.services import media_probe

    captured: list[str] = []
    monkeypatch.setattr(
        media_probe.subprocess,
        "run",
        lambda argv, **_kwargs: (
            captured.append(argv[-1])
            or SimpleNamespace(
                returncode=0,
                stdout='{"streams":[{"codec_type":"video","codec_name":"h264","width":64,"height":48}],"format":{"duration":"1.0","format_name":"mp4"}}',
                stderr="",
            )
        ),
    )

    info = probe_media("https://cdn.example.test/narrato/api/video.mp4")

    assert captured == ["https://cdn.example.test/narrato/api/video.mp4"]
    assert info.container == "mp4"


def test_ffprobe_reuses_configured_ffmpeg_sibling(monkeypatch, tmp_path):
    from app.services import media_probe

    ffmpeg = tmp_path / "ffmpeg"
    ffprobe = tmp_path / "ffprobe"
    ffmpeg.touch()
    ffprobe.touch()
    monkeypatch.setenv("NARRATO_FFMPEG_EXE", str(ffmpeg))

    assert media_probe._ffprobe_binary() == str(ffprobe)


def test_ffprobe_missing_explicit_path_falls_back_to_imageio_sibling(
    monkeypatch, tmp_path
):
    from app.services import media_probe

    ffmpeg = tmp_path / "imageio-ffmpeg"
    ffprobe = tmp_path / "ffprobe"
    ffmpeg.touch()
    ffprobe.touch()
    monkeypatch.setenv("NARRATO_FFPROBE_EXE", str(tmp_path / "missing-ffprobe"))
    monkeypatch.delenv("NARRATO_FFMPEG_EXE", raising=False)
    monkeypatch.delenv("IMAGEIO_FFMPEG_EXE", raising=False)
    monkeypatch.setitem(
        sys.modules,
        "imageio_ffmpeg",
        SimpleNamespace(get_ffmpeg_exe=lambda: str(ffmpeg)),
    )

    assert media_probe._ffprobe_binary() == str(ffprobe)


@pytest.mark.parametrize(
    "payload",
    [
        {"streams": "not-a-list", "format": {"duration": "1"}},
        {"streams": [123], "format": {"duration": "1"}},
        {"streams": [], "format": []},
        {
            "streams": [{"codec_type": "video", "width": "bad", "height": 10}],
            "format": {"duration": "1"},
        },
    ],
)
def test_probe_media_wraps_invalid_ffprobe_schema(monkeypatch, tmp_path, payload):
    import json

    from app.services import media_probe

    media_file = tmp_path / "sample.mp4"
    media_file.touch()
    monkeypatch.setattr(
        media_probe.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0,
            stdout=json.dumps(payload),
            stderr="",
        ),
    )

    with pytest.raises(MediaProbeError, match="FFprobe 返回结构无效"):
        probe_media(str(media_file))
