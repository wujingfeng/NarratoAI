import json
import wave
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from core_api.adapters.narrato.render import (
    FfmpegRenderBackend,
    _expanded_source_subtitle_blur_pixels,
    _output_dimensions,
    _voice_anchor_offset,
)
from core_api.adapters.narrato.tts import TtsSynthesisResult, TtsWordTimestamp
from core_api.runtime.process_runner import ProcessResult


class DurationTts:
    def synthesize(self, text, target, *, voice_snapshot):
        duration = 2.0 if text == "long" else 1.0
        with wave.open(str(target), "wb") as output:
            output.setparams((1, 2, 16_000, round(duration * 16_000), "NONE", "raw"))
            output.writeframes(b"\0\0" * round(duration * 16_000))


class RecordingRunner:
    def __init__(self):
        self.calls = []

    def run(self, argv, **kwargs):
        self.calls.append(list(argv))
        if argv[0] == "ffprobe":
            return ProcessResult(
                0,
                json.dumps(
                    {
                        "format": {"duration": "8.0"},
                        "streams": [{"codec_type": "video", "width": 1920, "height": 1080}],
                    }
                ),
                "",
                False,
                False,
                False,
            )
        target = Path(argv[-1])
        if target.suffix == ".wav":
            with wave.open(str(target), "wb") as output:
                output.setparams((1, 2, 16_000, 48_000, "NONE", "raw"))
                output.writeframes(b"\0\0" * 48_000)
        else:
            target.write_bytes(b"\x00\x00\x00\x18ftypmp42rendered")
        return ProcessResult(0, "", "", False, False, False)


def test_default_output_preserves_first_source_resolution():
    assert _output_dimensions(1920, 1080, "original") == (1920, 1080)
    assert _output_dimensions(1080, 1920, "original") == (1080, 1920)


def test_long_voice_extends_only_its_source_cut_and_keeps_following_start(tmp_path):
    runner = RecordingRunner()
    source = tmp_path / "source.mp4"
    source.write_bytes(b"video")
    result = FfmpegRenderBackend(
        provider=DurationTts(), voice_snapshot={}, runner=runner
    ).render(
        sources=[source],
        source_order=["video"],
        timeline=[
            {"source_asset_id": "video", "start": 0, "end": 1, "narration": "long"},
            {"source_asset_id": "video", "start": 1, "end": 2, "narration": "short"},
        ],
        output_dir=tmp_path,
        render_config={
            "video_ratio": "original",
            "source_subtitle_layouts": {
                "video": {
                    "status": "confirmed",
                    "region": {"x": 0, "y": 0.78, "width": 1, "height": 0.12},
                }
            },
        },
    )

    raw_video = runner.calls[1]
    input_pairs = [
        (raw_video[index + 1], raw_video[index + 3])
        for index, value in enumerate(raw_video)
        if value == "-ss"
    ]
    # 第一段因 2 秒配音扩到 0..2；第二段仍从原 1 秒起裁，允许画面重复。
    assert input_pairs == [("0", "2.000000"), ("1", "1.000000")]
    filters = raw_video[raw_video.index("-filter_complex") + 1]
    assert "scale=1920:1080" in filters
    assert "drawbox=" in filters
    assert "stop_duration=0.000000" in filters
    assert result["timeline"][0]["source_end"] == pytest.approx(2.0)
    assert result["timeline"][1]["source_start"] == pytest.approx(1.0)
    assert result["timeline"][1]["start"] == pytest.approx(2.0)
    assert "00:00:02,000" in result["subtitle"].read_text(encoding="utf-8")


def test_visual_anchor_delays_voice_and_caption_using_native_tts_words(tmp_path):
    class TimestampTts(DurationTts):
        def synthesize(self, text, target, *, voice_snapshot):
            super().synthesize("short", target, voice_snapshot=voice_snapshot)
            return TtsSynthesisResult(words=(
                TtsWordTimestamp("证", 0.4, 0.5),
                TtsWordTimestamp("据", 0.5, 0.6),
            ))

    runner = RecordingRunner()
    source = tmp_path / "source.mp4"
    source.write_bytes(b"video")
    result = FfmpegRenderBackend(
        provider=TimestampTts(), voice_snapshot={}, runner=runner
    ).render(
        sources=[source],
        source_order=["video"],
        timeline=[{
            "source_asset_id": "video",
            "start": 0,
            "end": 3,
            "narration": "证据出现",
            "visual_anchor": 2.0,
            "narration_anchor_text": "证据",
            "visual_lead": 0.1,
        }],
        output_dir=tmp_path,
        render_config={"video_ratio": "original"},
    )

    assert result["timeline"][0]["narration_start_offset"] == pytest.approx(1.7)
    assert result["timeline"][0]["narration_start"] == pytest.approx(1.7)
    voice_call = next(
        call for call in runner.calls if Path(call[-1]).name == "voice.wav"
    )
    filters = voice_call[voice_call.index("-filter_complex") + 1]
    assert "adelay=1700:all=1" in filters
    assert "00:00:01,700" in result["subtitle"].read_text(encoding="utf-8")


def test_voice_anchor_requires_unique_phrase_in_narration_and_tts_words():
    unique_words = (
        TtsWordTimestamp("证", 0.4, 0.5),
        TtsWordTimestamp("据", 0.5, 0.6),
    )
    repeated_words = unique_words + (
        TtsWordTimestamp("证", 1.1, 1.2),
        TtsWordTimestamp("据", 1.2, 1.3),
    )

    assert _voice_anchor_offset("证据出现，证据消失", "证 据", unique_words) is None
    assert _voice_anchor_offset("证据出现", "证据", repeated_words) is None
    assert _voice_anchor_offset("哈哈哈", "哈哈", unique_words) is None
    assert _voice_anchor_offset(
        "哈哈", "哈哈", (TtsWordTimestamp("哈哈哈", 0.2, 0.5),)
    ) is None
    assert _voice_anchor_offset("证据出现", "证 据", unique_words) == pytest.approx(0.4)


def test_narration_masks_with_padded_gaussian_blur_and_original_row_keeps_audio(
    tmp_path,
):
    class CountingTts(DurationTts):
        def __init__(self):
            self.calls = []

        def synthesize(self, text, target, *, voice_snapshot):
            self.calls.append(text)
            return super().synthesize(text, target, voice_snapshot=voice_snapshot)

    class AudioRunner(RecordingRunner):
        def run(self, argv, **kwargs):
            if argv[0] == "ffprobe":
                self.calls.append(list(argv))
                return ProcessResult(
                    0,
                    json.dumps(
                        {
                            "format": {"duration": "8.0"},
                            "streams": [
                                {
                                    "codec_type": "video",
                                    "width": 720,
                                    "height": 1280,
                                },
                                {"codec_type": "audio"},
                            ],
                        }
                    ),
                    "",
                    False,
                    False,
                    False,
                )
            return super().run(argv, **kwargs)

    runner = AudioRunner()
    provider = CountingTts()
    source = tmp_path / "source.mp4"
    source.write_bytes(b"video")
    result = FfmpegRenderBackend(
        provider=provider, voice_snapshot={}, runner=runner
    ).render(
        sources=[source],
        source_order=["video"],
        timeline=[
            {
                "source_asset_id": "video",
                "start": 0,
                "end": 1,
                "narration": "short",
                "original_sound": False,
            },
            {
                "source_asset_id": "video",
                "start": 1,
                "end": 2,
                "narration": "播放原片_2",
                "original_sound": True,
            },
        ],
        output_dir=tmp_path,
        render_config={
            "source_subtitle_layouts": {
                "video": {
                    "status": "confirmed",
                    "region": {"x": 0, "y": 0.836, "width": 1, "height": 0.029},
                }
            }
        },
    )

    assert provider.calls == ["short"]
    raw = next(call for call in runner.calls if Path(call[-1]).name == "video_raw.mp4")
    filters = raw[raw.index("-filter_complex") + 1]
    assert "[0:v:0]split=2[src0][masksrc0]" in filters
    assert "[1:v:0]split=2[src1][masksrc1]" not in filters
    assert "gblur=sigma=18:steps=2" in filters
    assert "drawbox=" in filters
    assert "[1:a:0]aresample=48000" in filters
    assert "[0:a:0]aresample=48000" not in filters
    _, padded_y, _, padded_height = _expanded_source_subtitle_blur_pixels(
        {"x": 0, "y": 0.836, "width": 1, "height": 0.029}, 720, 1280
    )
    assert padded_y < round(0.836 * 1280)
    assert padded_height > round(0.029 * 1280)
    assert "播放原片_2" not in result["subtitle"].read_text(encoding="utf-8")
    with Image.open(tmp_path / "caption_0001.png") as original_caption:
        assert original_caption.getbbox() is None


def test_semantic_caption_splits_to_two_lines_without_changing_font_size(tmp_path):
    backend = FfmpegRenderBackend(provider=DurationTts(), voice_snapshot={}, runner=None)
    text = "第一句先抛出谜团，第二句继续推进线索。第三句揭示反转，但仍然留下悬念！"
    canvas = Image.new("RGBA", (720, 1280), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    font = backend._caption_font(text, 48)
    segments = backend._semantic_caption_segments(
        text=text,
        draw=draw,
        font=font,
        max_width=620,
        stroke_width=4,
    )
    assert segments is not None
    assert "".join(segments) == text
    assert len(segments) >= 2
    assert all(
        len(
            backend._caption_lines(
                segment,
                draw=draw,
                font=font,
                max_width=620,
                stroke_width=4,
            )
        )
        <= 2
        for segment in segments
    )
