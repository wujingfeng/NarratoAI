import json
import wave
from pathlib import Path

import pytest
from PIL import Image

from core_api.adapters.narrato.render import (
    FakeRenderBackend,
    FfmpegRenderBackend,
    RenderAdapter,
    RenderInputError,
    RenderTemporaryError,
    _effective_video_content_region,
    _normalize_render_config,
    _source_subtitle_blur_pixels,
    _source_subtitle_blur_region,
    _voice_separation_client_token,
)
from core_api.adapters.narrato.tts import FakeTtsProvider
from core_api.adapters.narrato.mediakit_voice_separation import (
    MediaKitVoiceSeparationTemporaryError,
)
from core_api.infrastructure.oss_client import DownloadReceipt, OssUploadResult
from core_api.runtime.artifact_store import ArtifactStore
from core_api.runtime.artifact_store import ArtifactSecurityError
from core_api.runtime.checkpoint_store import FilesystemCheckpointStore
from core_api.runtime.process_runner import ProcessResult
from core_api.runtime.workspace import CoreTaskWorkspace
from core_api.tasks.checkpoints import TaskCheckpointService
from core_api.tasks.models import CoreTaskCheckpoint


class MemoryDownloader:
    def download(self, url, destination, *, max_bytes):
        destination.write_bytes(b"source-video")
        return DownloadReceipt(url, 12, "video/mp4")


class MemoryOss:
    public_base_url = "https://cdn.example.test"

    def __init__(self):
        self.uploaded = []
        self.deleted = []

    def upload_stream(self, stream, object_key, *, content_type, size):
        data = stream.read()
        assert len(data) == size
        self.uploaded.append(object_key)
        return OssUploadResult(
            "fake", object_key, f"https://cdn.example.test/{object_key}"
        )

    def delete_object(self, object_key):
        self.deleted.append(object_key)


def request():
    return dict(
        snapshot_id="revision_1",
        source_order=["asset_b", "asset_a"],
        sources=[
            {
                "source_asset_id": "asset_b",
                "video_url": "https://cdn.example.test/narrato/api/b.mp4",
            },
            {
                "source_asset_id": "asset_a",
                "video_url": "https://cdn.example.test/narrato/api/a.mp4",
            },
        ],
        timeline=[
            {"source_asset_id": "asset_b", "start": 0, "end": 1, "narration": "B"},
            {"source_asset_id": "asset_a", "start": 0, "end": 1, "narration": "A"},
        ],
        voice_id="voice_fake",
        voice_snapshot={"voice_id": "voice_fake"},
    )


def test_default_render_caption_scale_uses_ninety_percent_baseline():
    render_config = _normalize_render_config(None)

    assert render_config["narration_subtitle_position"] == {
        "y": 0.82,
        "font_scale": 0.9,
    }


def test_render_config_normalization_preserves_confirmed_source_subtitle_layouts():
    raw = {
        "source_subtitle_layouts": {
            "asset_a": {
                "status": "confirmed",
                "region": {"x": 0, "y": 0.78, "width": 1, "height": 0.12},
            }
        }
    }

    once = _normalize_render_config(raw)
    twice = _normalize_render_config(once)

    assert once["source_subtitle_layouts"] == {
        "asset_a": {"x": 0.0, "y": 0.78, "width": 1.0, "height": 0.12}
    }
    assert twice == once


def test_successful_render_registers_required_artifacts(tmp_path):
    adapter = RenderAdapter(
        MemoryDownloader(), FakeRenderBackend(), ArtifactStore(MemoryOss())
    )
    workspace = CoreTaskWorkspace.create(tmp_path, "ctask_render", 1)
    result = adapter.run(
        workspace=workspace, core_task_id="ctask_render", attempt_no=1, **request()
    )
    assert {item["kind"] for item in result["artifacts"]} >= {
        "video",
        "subtitle",
        "voice",
        "timeline",
    }
    assert all(item["url"].startswith("https://") for item in result["artifacts"])
    assert json.loads((workspace.output_dir / "timeline.json").read_text())[
        "source_order"
    ] == ["asset_b", "asset_a"]
    video = next(item for item in result["artifacts"] if item["kind"] == "video")
    assert (video["width"], video["height"], video["duration"]) == (1280, 720, 2.0)
    assert result["metadata"]["jianying_snapshot"] == {
        "timeline": [
            {"source_asset_id": "asset_b", "start": 0.0, "end": 1.0, "narration": "B"},
            {"source_asset_id": "asset_a", "start": 1.0, "end": 2.0, "narration": "A"},
        ],
        "video": {"width": 1280, "height": 720, "duration": 2.0},
    }


def test_render_jianying_snapshot_uses_edited_subtitles_and_skips_original_sound(
    tmp_path,
):
    adapter = RenderAdapter(
        MemoryDownloader(), FakeRenderBackend(), ArtifactStore(MemoryOss())
    )
    workspace = CoreTaskWorkspace.create(tmp_path, "ctask_jysnapshot", 1)
    payload = request()
    payload["timeline"] = [
        {
            "source_asset_id": "asset_b",
            "start": 0,
            "end": 1,
            "narration": "原始解说",
            "subtitle": "编辑后的字幕",
        },
        {
            "source_asset_id": "asset_a",
            "start": 0,
            "end": 1,
            "narration": "原声片段",
            "original_sound": True,
        },
    ]

    result = adapter.run(
        workspace=workspace,
        core_task_id="ctask_jysnapshot",
        attempt_no=1,
        **payload,
    )

    assert result["metadata"]["jianying_snapshot"]["timeline"] == [
        {
            "source_asset_id": "asset_b",
            "start": 0.0,
            "end": 1.0,
            "narration": "编辑后的字幕",
        }
    ]


def test_render_rejects_implicit_or_mutable_input(tmp_path):
    adapter = RenderAdapter(
        MemoryDownloader(), FakeRenderBackend(), ArtifactStore(MemoryOss())
    )
    workspace = CoreTaskWorkspace.create(tmp_path, "ctask_render", 1)
    bad = request()
    bad["source_order"] = ["asset_a", "asset_b"]
    with pytest.raises(RenderInputError):
        adapter.run(
            workspace=workspace, core_task_id="ctask_render", attempt_no=1, **bad
        )


def test_render_rejects_declared_source_that_timeline_never_uses(tmp_path):
    adapter = RenderAdapter(
        MemoryDownloader(), FakeRenderBackend(), ArtifactStore(MemoryOss())
    )
    workspace = CoreTaskWorkspace.create(tmp_path, "ctask_unused", 1)
    bad = request()
    bad["timeline"] = bad["timeline"][:1]

    with pytest.raises(RenderInputError, match="RENDER_TIMELINE_INVALID"):
        adapter.run(
            workspace=workspace,
            core_task_id="ctask_unused",
            attempt_no=1,
            **bad,
        )


def test_render_compensates_partial_upload_when_lease_is_lost(tmp_path):
    oss = MemoryOss()
    adapter = RenderAdapter(MemoryDownloader(), FakeRenderBackend(), ArtifactStore(oss))
    workspace = CoreTaskWorkspace.create(tmp_path, "ctask_render", 1)
    calls = 0

    def guard():
        nonlocal calls
        calls += 1
        if calls == 3:
            raise RuntimeError("stale")

    with pytest.raises(RuntimeError):
        adapter.run(
            workspace=workspace,
            core_task_id="ctask_render",
            attempt_no=1,
            lease_guard=guard,
            **request(),
        )
    assert len(oss.uploaded) == 1
    assert oss.deleted == oss.uploaded


@pytest.mark.parametrize(
    "url",
    [
        "https://127.0.0.1/narrato/coreApi/x.mp4",
        "https://localhost/narrato/coreApi/x.mp4",
        "https://user@cdn.example.test/narrato/coreApi/x.mp4",
        "https://evil.example.test/narrato/coreApi/x.mp4",
        "https://cdn.example.test/private/x.mp4",
        "https://cdn.example.test/narrato/coreApi/x.mp4?secret=1",
        "https://cdn.example.test/narrato/coreApi/x.mp4#fragment",
    ],
)
def test_artifact_store_rejects_unsafe_output_url(tmp_path, url):
    class UnsafeOss(MemoryOss):
        def upload_stream(self, stream, object_key, *, content_type, size):
            stream.read()
            return OssUploadResult("fake", object_key, url)

    workspace = CoreTaskWorkspace.create(tmp_path, "ctask_url", 1)
    target = workspace.controlled_path("output", "video", "mp4")
    target.write_bytes(b"\x00\x00\x00\x18ftypmp42")
    with pytest.raises(ArtifactSecurityError, match="ARTIFACT_URL_REJECTED"):
        ArtifactStore(UnsafeOss()).upload(
            workspace=workspace,
            local_path=target,
            core_task_id="ctask_url",
            attempt_no=1,
            kind="video",
            content_type="video/mp4",
        )


def test_production_render_backend_uses_governed_ffmpeg_and_heartbeat(tmp_path):
    class Runner:
        def __init__(self):
            self.calls = []

        def run(self, argv, **kwargs):
            self.calls.append((argv, kwargs))
            kwargs["heartbeat"]()
            if argv[0] == "ffprobe":
                return ProcessResult(
                    0,
                    '{"format":{"duration":"10.0"},"streams":[{"codec_type":"video"}]}',
                    "",
                    False,
                    False,
                    False,
                )
            if str(argv[-1]).endswith(".wav"):
                FakeTtsProvider().synthesize("x", Path(argv[-1]), voice_snapshot={})
            else:
                Path(argv[-1]).write_bytes(b"rendered")
            return ProcessResult(0, "", "", False, False, False)

    runner = Runner()
    source = tmp_path / "input.mp4"
    source.write_bytes(b"video")
    beats = []
    progress = []
    result = FfmpegRenderBackend(
        provider=FakeTtsProvider(),
        voice_snapshot={"voice_id": "voice_fake"},
        runner=runner,
    ).render(
        sources=[source],
        source_order=["asset_a"],
        timeline=[
            {
                "source_asset_id": "asset_a",
                "start": 0,
                "end": 1,
                "narration": "这一段解说需要在合成前按标点优先拆分，确保每个字幕提示保持可读并且完整。",
            },
            {
                "source_asset_id": "asset_a",
                "start": 1,
                "end": 2,
                "narration": "B",
            },
        ],
        output_dir=tmp_path,
        heartbeat=lambda: beats.append(1),
        progress=lambda value: progress.append(value),
    )
    assert len(runner.calls) == 4 and len(beats) == 4
    assert all(
        call[0][0] == "ffmpeg" and call[0][1] == "-nostdin" for call in runner.calls[1:]
    )
    assert all(call[1]["timeout_seconds"] == 1800 for call in runner.calls[1:])
    raw_video_argv = runner.calls[2][0]
    final_argv = runner.calls[3][0]
    assert raw_video_argv[raw_video_argv.index("-preset") + 1] == "veryfast"
    assert final_argv[final_argv.index("-preset") + 1] == "veryfast"
    assert final_argv.count("-i") == 3
    assert "-loop" not in final_argv
    final_filters = final_argv[final_argv.index("-filter_complex") + 1]
    assert final_filters.count("overlay=") == 1
    manifest = (tmp_path / "captions.ffconcat").read_text(encoding="utf-8")
    srt = result["subtitle"].read_text(encoding="utf-8")
    # 分段后的同一份 cue 同时驱动 SRT、图片和 concat 时间线。
    assert manifest.count("duration ") > 2
    assert manifest.count("duration ") == srt.count(" --> ")
    assert manifest.count("file '") == srt.count(" --> ") + 1
    with Image.open(tmp_path / "caption_0000.png") as caption:
        assert caption.width == 1280
        assert caption.height == 720
    assert progress == [25, 40, 50, 65, 72, 90]
    assert result["video"].read_bytes() == b"rendered"


def test_portrait_source_caption_is_drawn_only_in_contained_content_region(tmp_path):
    region = _effective_video_content_region(1280, 720, 720, 1280)
    assert region == _effective_video_content_region(1280, 720, 720, 1280)
    assert (region.x, region.y, region.width, region.height) == (437, 0, 405, 720)

    backend = FfmpegRenderBackend(
        provider=FakeTtsProvider(),
        voice_snapshot={"voice_id": "voice_fake"},
        runner=None,
    )
    image_path = backend._render_caption_images(
        timeline=[{"narration": "A caption that must wrap inside portrait video"}],
        width=1280,
        height=720,
        style="classic_white",
        source_regions=[region],
        output_dir=tmp_path,
    )[0]
    with Image.open(image_path) as caption:
        bbox = caption.getbbox()
    assert bbox is not None
    left, top, right, bottom = bbox
    assert region.x <= left < right <= region.x + region.width
    assert region.y <= top < bottom <= region.y + region.height


def test_source_subtitle_blur_region_uses_confirmed_detection_bounds_exactly():
    region = {"x": 0, "y": 0.78, "width": 1, "height": 0.12}
    top, height = _source_subtitle_blur_region(region)

    assert top == pytest.approx(0.78)
    assert height == pytest.approx(0.12)
    assert _source_subtitle_blur_pixels(region, 720, 1280) == (0, 998, 720, 154)


def test_source_subtitle_blur_pixels_always_covers_the_full_subtitle_line():
    assert _source_subtitle_blur_pixels(
        {"x": 0.1, "y": 0.78, "width": 0.8, "height": 0.12},
        720,
        1280,
    ) == (0, 998, 720, 154)


def test_semantic_caption_segments_keep_text_and_prefer_punctuation(tmp_path):
    backend = FfmpegRenderBackend(
        provider=FakeTtsProvider(),
        voice_snapshot={"voice_id": "voice_fake"},
        runner=None,
    )
    image = Image.new("RGBA", (320, 180), (0, 0, 0, 0))
    draw = __import__("PIL.ImageDraw", fromlist=["ImageDraw"]).Draw(image)
    text = "第一句话很重要，第二句话也要保留。第三句话不能丢失！"
    font = backend._caption_font(text, 18)
    segments = backend._semantic_caption_segments(
        text=text,
        draw=draw,
        font=font,
        max_width=120,
        stroke_width=2,
    )

    assert segments is not None
    assert "".join(segments) == text
    assert any(segment.endswith(("，", "。", "！")) for segment in segments[:-1])


def test_english_caption_never_splits_words_and_limits_each_cue_to_two_lines(
    tmp_path,
):
    backend = FfmpegRenderBackend(
        provider=FakeTtsProvider(),
        voice_snapshot={"voice_id": "voice_fake"},
        runner=None,
    )
    image = Image.new("RGBA", (320, 180), (0, 0, 0, 0))
    draw = __import__("PIL.ImageDraw", fromlist=["ImageDraw"]).Draw(image)
    text = (
        "Ancient explorers discovered a transformation mechanism beneath the "
        "underground labyrinth."
    )
    font = backend._caption_font(text, 18)
    segments = backend._semantic_caption_segments(
        text=text, draw=draw, font=font, max_width=150, stroke_width=2
    )

    assert segments is not None
    assert all(len(segment.splitlines()) <= 2 for segment in segments)
    assert " ".join(" ".join(segments).split()) == text
    assert any("transformation" in segment for segment in segments)


def test_video_translation_uses_one_continuous_source_and_non_vocal_stem(tmp_path):
    class Runner:
        def __init__(self):
            self.calls = []

        def run(self, argv, **kwargs):
            self.calls.append(argv)
            if argv[0] == "ffprobe":
                return ProcessResult(
                    0,
                    '{"format":{"duration":"3.0"},"streams":['
                    '{"codec_type":"video","width":320,"height":180,'
                    '"avg_frame_rate":"24000/1001"},{"codec_type":"audio"}]}',
                    "",
                    False,
                    False,
                    False,
                )
            target = Path(argv[-1])
            if target.suffix == ".wav":
                with wave.open(str(target), "wb") as output:
                    output.setparams((1, 2, 16_000, 48_000, "NONE", "not compressed"))
                    output.writeframes(b"\0\0" * 48_000)
            else:
                target.write_bytes(b"rendered")
            return ProcessResult(0, "", "", False, False, False)

    source = tmp_path / "source.mp4"
    stem = tmp_path / "non-vocal.wav"
    source.write_bytes(b"video")
    stem.write_bytes(b"stem")
    runner = Runner()
    result = FfmpegRenderBackend(
        provider=FakeTtsProvider(),
        voice_snapshot={"voice_id": "voice_fake"},
        runner=runner,
    ).render(
        sources=[source],
        source_order=["asset_a"],
        timeline=[
            {
                "source_asset_id": "asset_a",
                "start": 0.5,
                "end": 1.5,
                "narration": "Ancient explorers discovered the labyrinth.",
                "voice_id": "voice_fake",
                "speed": 1.0,
                "volume": 80,
            }
        ],
        render_config={
            "render_mode": "video_translation",
            "translation_audio_mode": "voice_replacement",
            "video_ratio": "original",
        },
        non_vocal_audio=stem,
        output_dir=tmp_path,
    )

    final_argv = runner.calls[-1]
    filters = final_argv[final_argv.index("-filter_complex") + 1]
    assert "-ss" not in final_argv and "-t" in final_argv
    assert "concat=n=" not in filters
    assert str(source) in final_argv and str(stem) in final_argv
    assert "[2:a]aresample=48000" in filters
    assert "loudnorm=I=-16:TP=-1.5:LRA=11" in " ".join(
        call[call.index("-filter_complex") + 1]
        for call in runner.calls
        if "-filter_complex" in call
    )
    assert "anullsrc=r=16000:cl=mono:d=3.000000[voice_silence]" in " ".join(
        call[call.index("-filter_complex") + 1]
        for call in runner.calls
        if "-filter_complex" in call
    )
    assert "sidechaincompress=threshold=0.025:ratio=4" in filters
    assert final_argv[final_argv.index("-t") + 1] == "3.000000"
    voice_track_argv = next(
        call for call in runner.calls if call[-1].endswith("voice.wav")
    )
    assert voice_track_argv[voice_track_argv.index("-t") + 1] == "3.000000"
    assert result["video_duration"] == pytest.approx(3.0)
    assert result["frame_rate"] == "24000/1001"
    assert result["timeline"][0]["start"] == pytest.approx(0.5)


def test_voice_replacement_without_stem_or_separator_fails_explicitly(tmp_path):
    class Runner:
        def run(self, argv, **kwargs):
            if argv[0] == "ffprobe":
                return ProcessResult(
                    0,
                    '{"format":{"duration":"2"},"streams":['
                    '{"codec_type":"video","width":320,"height":180}]}',
                    "",
                    False,
                    False,
                    False,
                )
            target = Path(argv[-1])
            if target.suffix == ".wav":
                FakeTtsProvider().synthesize("x", target, voice_snapshot={})
            return ProcessResult(0, "", "", False, False, False)

    source = tmp_path / "source.mp4"
    source.write_bytes(b"video")
    with pytest.raises(RenderInputError, match="RENDER_VOICE_SEPARATION_UNAVAILABLE"):
        FfmpegRenderBackend(
            provider=FakeTtsProvider(),
            voice_snapshot={"voice_id": "voice_fake"},
            runner=Runner(),
        ).render(
            sources=[source],
            source_order=["asset_a"],
            timeline=[
                {"source_asset_id": "asset_a", "start": 0, "end": 1, "narration": "A"}
            ],
            render_config={
                "render_mode": "video_translation",
                "translation_audio_mode": "voice_replacement",
                "video_ratio": "original",
            },
            output_dir=tmp_path,
        )


def test_voice_separation_backend_uses_public_source_url_and_stable_token(tmp_path):
    class Separator:
        def __init__(self):
            self.separate_calls = []
            self.download_calls = []

        def separate(self, *, video_url, client_token, heartbeat, on_submitted):
            self.separate_calls.append((video_url, client_token, heartbeat))
            on_submitted("task-submitted", "request-submitted")
            return type(
                "Result",
                (),
                {
                    "task_id": "task-completed",
                    "request_id": "request-completed",
                    "background_audio_url": "https://mediakit-result.example.test/bg.wav",
                },
            )()

        def download_background_audio(self, url, target, *, max_bytes, heartbeat):
            self.download_calls.append((url, target, max_bytes, heartbeat))
            with wave.open(str(target), "wb") as output:
                output.setparams((1, 2, 16_000, 16_000, "NONE", "not compressed"))
                output.writeframes(b"\0\0" * 16_000)
            return target

    separator = Separator()
    backend = FfmpegRenderBackend(
        provider=FakeTtsProvider(),
        voice_snapshot={"voice_id": "voice_fake"},
        runner=None,
        voice_separator=separator,
    )

    def heartbeat():
        return None

    token = _voice_separation_client_token("core-task-1")
    checkpointed = []
    target, audit = backend._separate_non_vocal_audio(
        "https://cdn.example.test/narrato/api/source.mp4",
        output_dir=tmp_path,
        heartbeat=heartbeat,
        client_token=token,
        existing_task=None,
        checkpoint_task=lambda task_id, request_id: checkpointed.append(
            (task_id, request_id)
        ),
    )

    assert target.stat().st_size > 0
    assert separator.separate_calls == [
        ("https://cdn.example.test/narrato/api/source.mp4", token, heartbeat)
    ]
    assert separator.download_calls[0][:3] == (
        "https://mediakit-result.example.test/bg.wav",
        target,
        300 * 1024 * 1024,
    )
    assert checkpointed == [("task-submitted", "request-submitted")]
    assert audit == {"task_id": "task-completed", "request_id": "request-completed"}
    assert token == _voice_separation_client_token("core-task-1")
    assert len(token) <= 64 and token.isascii()


def test_voice_separation_task_checkpoint_resumes_polling_without_resubmit(
    tmp_path, task_service, session
):
    """第三方已提交任务跨 attempt 只允许恢复轮询，不能再次 POST。"""

    class Backend(FakeRenderBackend):
        def __init__(self):
            self.tasks = []

        def render(self, **kwargs):
            task = kwargs.get("voice_separation_task")
            self.tasks.append(dict(task) if isinstance(task, dict) else None)
            if task is None:
                callback = kwargs["checkpoint_voice_separation_task"]
                assert callback is not None
                callback("amk-task-1", "submit-request-1")
                raise RenderTemporaryError("RENDER_VOICE_SEPARATION_TIMEOUT")
            return super().render(**kwargs)

    payload = request()
    payload["sources"] = payload["sources"][:1]
    payload["source_order"] = payload["source_order"][:1]
    payload["timeline"] = payload["timeline"][:1]
    payload["render_config"] = {
        "render_mode": "video_translation",
        "translation_audio_mode": "voice_replacement",
        "video_ratio": "16:9",
    }
    task = task_service.create_core_task(
        caller="narrato-api",
        route="/api/v1/video-render/tasks",
        task_type="video_render",
        idempotency_key="voice-separation-checkpoint",
        input_snapshot=payload,
    )
    manager = TaskCheckpointService(session, FilesystemCheckpointStore(tmp_path))
    backend = Backend()
    adapter = RenderAdapter(
        MemoryDownloader(),
        backend,
        ArtifactStore(MemoryOss()),
        checkpoint_manager=manager,
    )

    with pytest.raises(RenderTemporaryError, match="VOICE_SEPARATION_TIMEOUT"):
        adapter.run(
            workspace=CoreTaskWorkspace.create(tmp_path, task.id, 1),
            core_task_id=task.id,
            attempt_no=1,
            **payload,
        )
    result = adapter.run(
        workspace=CoreTaskWorkspace.create(tmp_path, task.id, 2),
        core_task_id=task.id,
        attempt_no=2,
        **payload,
    )

    assert backend.tasks == [
        None,
        {"task_id": "amk-task-1", "request_id": "submit-request-1"},
    ]
    assert {item.stage for item in session.query(CoreTaskCheckpoint).all()} >= {
        "render_voice_separation_task"
    }
    assert {item["kind"] for item in result["artifacts"]} >= {"video", "voice"}


def test_resumed_voice_separation_failure_keeps_persisted_task_diagnostics(tmp_path):
    class Separator:
        def poll(self, **_kwargs):
            raise MediaKitVoiceSeparationTemporaryError(
                "RENDER_VOICE_SEPARATION_NETWORK_FAILURE"
            )

    backend = FfmpegRenderBackend(
        provider=FakeTtsProvider(),
        voice_snapshot={"voice_id": "voice_fake"},
        runner=None,
        voice_separator=Separator(),
    )
    with pytest.raises(MediaKitVoiceSeparationTemporaryError) as error:
        backend._separate_non_vocal_audio(
            "https://cdn.example.test/narrato/api/source.mp4",
            output_dir=tmp_path,
            heartbeat=None,
            client_token=_voice_separation_client_token("core-task-1"),
            existing_task={"task_id": "amk-task-1", "request_id": "submit-request-1"},
            checkpoint_task=None,
        )
    assert error.value.details == {
        "task_id": "amk-task-1",
        "request_id": "submit-request-1",
    }


def test_semantic_caption_failure_falls_back_to_original_cue(tmp_path):
    backend = FfmpegRenderBackend(
        provider=FakeTtsProvider(),
        voice_snapshot={"voice_id": "voice_fake"},
        runner=None,
    )
    text = "不能被省略或截断的原始字幕"
    cues, regions = backend._expand_caption_timeline(
        timeline=[{"start": 1.0, "end": 2.0, "narration": text}],
        source_regions=[_effective_video_content_region(1280, 720, None, None)],
        width=1280,
        height=720,
        style="classic_white",
        position_y=0.82,
        font_scale=0.9,
    )
    # 窄到单个汉字也放不下时，整条 cue 原样回退。
    # 用极窄内容区触发该分支，而不是测试实现细节。
    tiny_cues, _ = backend._expand_caption_timeline(
        timeline=[{"start": 1.0, "end": 2.0, "narration": text}],
        source_regions=[type(regions[0])(0, 0, 1, 1)],
        width=1280,
        height=720,
        style="classic_white",
        position_y=0.82,
        font_scale=0.9,
    )

    assert cues[0]["subtitle"] in text
    assert tiny_cues == [{"start": 1.0, "end": 2.0, "narration": text}]


def test_narration_duration_trims_short_voice_and_loops_long_voice_segment(tmp_path):
    """解说时间线以 TTS 为准，且长配音循环所选片段而非冻结末帧。"""

    class FixedDurationProvider:
        durations = {"short": 0.5, "long": 2.0}

        def synthesize(self, text, target, *, voice_snapshot):
            duration = self.durations[text]
            frames = int(duration * 16_000)
            with wave.open(str(target), "wb") as output:
                output.setparams((1, 2, 16_000, frames, "NONE", "not compressed"))
                output.writeframes(b"\0\0" * frames)

    class Runner:
        def __init__(self):
            self.calls = []

        def run(self, argv, **kwargs):
            self.calls.append((argv, kwargs))
            if argv[0] == "ffprobe":
                return ProcessResult(
                    0,
                    '{"format":{"duration":"10.0"},"streams":[{"codec_type":"video"}]}',
                    "",
                    False,
                    False,
                    False,
                )
            target = Path(argv[-1])
            if target.suffix == ".wav":
                # 合并输出仅需是可校验 WAV；时间线断言来自逐段 TTS 的实际时长。
                with wave.open(str(target), "wb") as output:
                    output.setparams((1, 2, 16_000, 40_000, "NONE", "not compressed"))
                    output.writeframes(b"\0\0" * 40_000)
            else:
                target.write_bytes(b"rendered")
            return ProcessResult(0, "", "", False, False, False)

    runner = Runner()
    source = tmp_path / "input.mp4"
    source.write_bytes(b"video")
    result = FfmpegRenderBackend(
        provider=FixedDurationProvider(),
        voice_snapshot={"voice_id": "voice_fake"},
        runner=runner,
    ).render(
        sources=[source],
        source_order=["asset_a"],
        timeline=[
            {"source_asset_id": "asset_a", "start": 0, "end": 1, "narration": "short"},
            {"source_asset_id": "asset_a", "start": 1, "end": 2, "narration": "long"},
        ],
        output_dir=tmp_path,
    )

    assert [
        item["end"] - item["start"] for item in result["timeline"]
    ] == pytest.approx([0.8, 2.0])
    raw_video_argv = next(
        argv for argv, _kwargs in runner.calls if Path(argv[-1]).name == "video_raw.mp4"
    )
    raw_filters = raw_video_argv[raw_video_argv.index("-filter_complex") + 1]
    assert "trim=duration=0.800000" in raw_filters
    assert "loop=loop=-1:size=0:start=0,trim=duration=2.000000" in raw_filters
    assert "tpad=stop_mode=clone" not in raw_filters
    assert "00:00:00,800 --> 00:00:02,800" in result["subtitle"].read_text(
        encoding="utf-8"
    )
    final_argv = next(
        argv for argv, _kwargs in runner.calls if Path(argv[-1]).name == "final.mp4"
    )
    final_filters = final_argv[final_argv.index("-filter_complex") + 1]
    assert "volume=1.300000" in final_filters


def test_original_sound_skips_tts_mutes_other_rows_and_renders_no_placeholder(
    tmp_path,
):
    class CountingProvider:
        def __init__(self):
            self.calls = []

        def synthesize(self, text, destination, *, voice_snapshot):
            self.calls.append(text)
            FakeTtsProvider().synthesize(
                text, destination, voice_snapshot=voice_snapshot
            )

    class Runner:
        def __init__(self):
            self.calls = []

        def run(self, argv, **kwargs):
            self.calls.append((argv, kwargs))
            if argv[0] == "ffprobe":
                return ProcessResult(
                    0,
                    '{"format":{"duration":"10.0"},"streams":'
                    '[{"codec_type":"video","width":720,"height":1280},'
                    '{"codec_type":"audio"}]}',
                    "",
                    False,
                    False,
                    False,
                )
            target = Path(argv[-1])
            if target.suffix == ".wav":
                FakeTtsProvider().synthesize("merged", target, voice_snapshot={})
            else:
                target.write_bytes(b"rendered")
            return ProcessResult(0, "", "", False, False, False)

    provider = CountingProvider()
    runner = Runner()
    source = tmp_path / "input.mp4"
    source.write_bytes(b"video")
    result = FfmpegRenderBackend(
        provider=provider,
        voice_snapshot={"voice_id": "voice_fake"},
        runner=runner,
    ).render(
        sources=[source],
        source_order=["asset_a"],
        timeline=[
            {
                "source_asset_id": "asset_a",
                "start": 0,
                "end": 1,
                "narration": "正常解说",
                "original_sound": False,
            },
            {
                "source_asset_id": "asset_a",
                "start": 1,
                "end": 2,
                "narration": "播放原片1",
                "original_sound": True,
            },
        ],
        render_config=_normalize_render_config(
            {
                "source_subtitle_layouts": {
                    "asset_a": {
                        "status": "confirmed",
                        "region": {
                            "x": 0,
                            "y": 0.78,
                            "width": 1,
                            "height": 0.12,
                        },
                    }
                }
            },
            has_original_sound=True,
        ),
        output_dir=tmp_path,
    )

    assert provider.calls == ["正常解说"]
    raw_video_argv = next(
        argv for argv, _kwargs in runner.calls if Path(argv[-1]).name == "video_raw.mp4"
    )
    raw_filters = raw_video_argv[raw_video_argv.index("-filter_complex") + 1]
    assert "[0:a:0]" not in raw_filters
    assert "[1:a:0]" in raw_filters
    assert "volume=1.000000" in raw_filters
    assert "[0:v:0]split=2[src0][masksrc0]" in raw_filters
    assert "[1:v:0]split=2[src1][masksrc1]" not in raw_filters
    assert "crop=720:154:0:998" in raw_filters
    assert "scale=30:6:flags=bilinear,scale=720:154:flags=bilinear" in raw_filters
    assert "overlay=0:998:eval=init[masked0]" in raw_filters
    assert "trunc(ih" not in raw_filters
    assert "播放原片1" not in result["subtitle"].read_text(encoding="utf-8")
    assert "正常解说" in result["subtitle"].read_text(encoding="utf-8")
    with Image.open(tmp_path / "caption_0001.png") as caption:
        assert caption.getbbox() is None
    assert result["timeline"][1]["original_sound"] is True
    assert result["timeline"][1]["end"] - result["timeline"][1][
        "start"
    ] == pytest.approx(1)


def test_all_original_sound_timeline_can_publish_empty_subtitle(tmp_path):
    payload = request()
    payload["sources"] = payload["sources"][:1]
    payload["source_order"] = payload["source_order"][:1]
    payload["timeline"] = [
        {
            "source_asset_id": "asset_b",
            "start": 0,
            "end": 1,
            "narration": "播放原片1",
            "original_sound": True,
        }
    ]
    adapter = RenderAdapter(
        MemoryDownloader(), FakeRenderBackend(), ArtifactStore(MemoryOss())
    )
    workspace = CoreTaskWorkspace.create(tmp_path, "ctask_originalonly", 1)

    result = adapter.run(
        workspace=workspace,
        core_task_id="ctask_originalonly",
        attempt_no=1,
        **payload,
    )

    assert {item["kind"] for item in result["artifacts"]} >= {"video", "subtitle"}
    assert (workspace.output_dir / "subtitle.srt").read_text(
        encoding="utf-8"
    ).strip() == ""
    assert (
        json.loads((workspace.output_dir / "timeline.json").read_text())[
            "render_config"
        ]["original_sound_volume"]
        == 100
    )


def test_voice_checkpoint_restore_rejects_original_sound_mismatch(tmp_path):
    voice = tmp_path / "voice.wav"
    with wave.open(str(voice), "wb") as output:
        output.setparams((1, 2, 16_000, 16_000, "NONE", "not compressed"))
        output.writeframes(b"\0\0" * 16_000)
    backend = FfmpegRenderBackend(
        provider=FakeTtsProvider(),
        voice_snapshot={"voice_id": "voice_fake"},
        runner=object(),  # type: ignore[arg-type]
    )
    checkpoint = {
        "voice": voice,
        "timeline": [
            {
                "source_asset_id": "asset_a",
                "source_start": 0,
                "source_end": 1,
                "start": 0,
                "end": 1,
                "narration": "播放原片1",
                "original_sound": False,
            }
        ],
    }
    with pytest.raises(RenderInputError, match="RENDER_VOICE_CHECKPOINT_INVALID"):
        backend._restore_voice_bundle(
            checkpoint,
            timeline=[
                {
                    "source_asset_id": "asset_a",
                    "start": 0,
                    "end": 1,
                    "narration": "播放原片1",
                    "original_sound": True,
                }
            ],
            output_dir=tmp_path,
        )


def test_ffmpeg_nonzero_is_deterministic_but_timeout_is_retryable(tmp_path):
    class Runner:
        def __init__(self, timed_out):
            self.timed_out = timed_out

        def run(self, argv, **kwargs):
            return ProcessResult(
                1, "", "sensitive path /private/x", self.timed_out, False, False
            )

    source = tmp_path / "input.mp4"
    source.write_bytes(b"video")
    request = dict(
        sources=[source],
        source_order=["asset_a"],
        timeline=[
            {"source_asset_id": "asset_a", "start": 0, "end": 1, "narration": "A"}
        ],
        output_dir=tmp_path,
    )
    from core_api.adapters.narrato.render import RenderTemporaryError

    with pytest.raises(RenderInputError):
        FfmpegRenderBackend(FakeTtsProvider(), {}, Runner(False)).render(**request)
    with pytest.raises(RenderTemporaryError):
        FfmpegRenderBackend(FakeTtsProvider(), {}, Runner(True)).render(**request)


def test_render_reuses_completed_voice_bundle_across_attempts(
    tmp_path, task_service, session
):
    """字幕等最终合成参数变化或进程重启都不得重复生成已完成配音。"""

    class CountingBackend(FakeRenderBackend):
        def __init__(self):
            self.voice_builds = 0

        def render(self, **kwargs):
            if kwargs.get("voice_checkpoint") is None:
                self.voice_builds += 1
            return super().render(**kwargs)

    task = task_service.create_core_task(
        caller="narrato-api",
        route="/api/v1/video-render/tasks",
        task_type="video_render",
        idempotency_key="checkpoint-bundle",
        input_snapshot=request(),
    )
    backend = CountingBackend()
    manager = TaskCheckpointService(session, FilesystemCheckpointStore(tmp_path))
    adapter = RenderAdapter(
        MemoryDownloader(),
        backend,
        ArtifactStore(MemoryOss()),
        checkpoint_manager=manager,
    )
    first_workspace = CoreTaskWorkspace.create(tmp_path, task.id, 1)
    adapter.run(
        workspace=first_workspace,
        core_task_id=task.id,
        attempt_no=1,
        **request(),
    )

    changed = request()
    changed["timeline"][0]["subtitle"] = "只修改字幕"
    second_workspace = CoreTaskWorkspace.create(tmp_path, task.id, 2)
    adapter.run(
        workspace=second_workspace,
        core_task_id=task.id,
        attempt_no=2,
        **changed,
    )

    assert backend.voice_builds == 1
    checkpoints = session.query(CoreTaskCheckpoint).all()
    assert {item.stage for item in checkpoints} == {
        "render_voice_bundle",
        "render_final_bundle",
    }
    assert (second_workspace.output_dir / "voice.wav").is_file()


def test_original_sound_flag_change_does_not_reuse_old_voice_bundle(
    tmp_path, task_service, session
):
    class CountingBackend(FakeRenderBackend):
        def __init__(self):
            self.voice_builds = 0

        def render(self, **kwargs):
            if kwargs.get("voice_checkpoint") is None:
                self.voice_builds += 1
            return super().render(**kwargs)

    payload = request()
    task = task_service.create_core_task(
        caller="narrato-api",
        route="/api/v1/video-render/tasks",
        task_type="video_render",
        idempotency_key="checkpoint-original-sound",
        input_snapshot=payload,
    )
    backend = CountingBackend()
    adapter = RenderAdapter(
        MemoryDownloader(),
        backend,
        ArtifactStore(MemoryOss()),
        checkpoint_manager=TaskCheckpointService(
            session, FilesystemCheckpointStore(tmp_path)
        ),
    )
    adapter.run(
        workspace=CoreTaskWorkspace.create(tmp_path, task.id, 1),
        core_task_id=task.id,
        attempt_no=1,
        **payload,
    )
    changed = request()
    changed["timeline"][0]["original_sound"] = True
    adapter.run(
        workspace=CoreTaskWorkspace.create(tmp_path, task.id, 2),
        core_task_id=task.id,
        attempt_no=2,
        **changed,
    )

    assert backend.voice_builds == 2


def test_render_reuses_final_bundle_when_publish_was_interrupted(
    tmp_path, task_service, session
):
    """最终编码成功但发布异常时，新 attempt 只重试产物发布。"""

    class CountingBackend(FakeRenderBackend):
        def __init__(self):
            self.calls = 0

        def render(self, **kwargs):
            self.calls += 1
            return super().render(**kwargs)

    class FailUploadOnceOss(MemoryOss):
        def __init__(self):
            super().__init__()
            self.fail = True

        def upload_stream(self, stream, object_key, *, content_type, size):
            if self.fail:
                self.fail = False
                raise RuntimeError("publish interrupted")
            return super().upload_stream(
                stream, object_key, content_type=content_type, size=size
            )

    payload = request()
    task = task_service.create_core_task(
        caller="narrato-api",
        route="/api/v1/video-render/tasks",
        task_type="video_render",
        idempotency_key="checkpoint-final-publish",
        input_snapshot=payload,
    )
    backend = CountingBackend()
    oss = FailUploadOnceOss()
    adapter = RenderAdapter(
        MemoryDownloader(),
        backend,
        ArtifactStore(oss),
        checkpoint_manager=TaskCheckpointService(
            session, FilesystemCheckpointStore(tmp_path)
        ),
    )
    first_workspace = CoreTaskWorkspace.create(tmp_path, task.id, 1)
    with pytest.raises(RuntimeError, match="publish interrupted"):
        adapter.run(
            workspace=first_workspace,
            core_task_id=task.id,
            attempt_no=1,
            **payload,
        )

    second_workspace = CoreTaskWorkspace.create(tmp_path, task.id, 2)
    result = adapter.run(
        workspace=second_workspace,
        core_task_id=task.id,
        attempt_no=2,
        **payload,
    )
    assert backend.calls == 1
    assert {item["kind"] for item in result["artifacts"]} == {
        "video",
        "subtitle",
        "voice",
        "timeline",
    }


def test_render_resumes_only_missing_tts_segments_after_process_loss(
    tmp_path, task_service, session
):
    """配音节点中断后复用已落盘片段，仅请求尚未完成的文案。"""

    class FailSecondOnceProvider:
        def __init__(self):
            self.calls = []
            self.failed = False

        def synthesize(self, text, destination, *, voice_snapshot):
            self.calls.append(text)
            if text == "A" and not self.failed:
                self.failed = True
                raise RuntimeError("provider interrupted")
            FakeTtsProvider().synthesize(
                text, destination, voice_snapshot=voice_snapshot
            )

    class Runner:
        def run(self, argv, **_kwargs):
            if argv[0] == "ffprobe":
                return ProcessResult(
                    0,
                    '{"format":{"duration":"10.0"},"streams":[{"codec_type":"video"}]}',
                    "",
                    False,
                    False,
                    False,
                )
            target = Path(argv[-1])
            if target.suffix == ".wav":
                FakeTtsProvider().synthesize("merged", target, voice_snapshot={})
            else:
                target.write_bytes(b"\x00\x00\x00\x18ftypmp42rendered")
            return ProcessResult(0, "", "", False, False, False)

    payload = request()
    task = task_service.create_core_task(
        caller="narrato-api",
        route="/api/v1/video-render/tasks",
        task_type="video_render",
        idempotency_key="checkpoint-segments",
        input_snapshot=payload,
    )
    provider = FailSecondOnceProvider()
    manager = TaskCheckpointService(session, FilesystemCheckpointStore(tmp_path))

    def adapter():
        return RenderAdapter(
            MemoryDownloader(),
            FfmpegRenderBackend(
                provider=provider,
                voice_snapshot=payload["voice_snapshot"],
                runner=Runner(),
            ),
            ArtifactStore(MemoryOss()),
            checkpoint_manager=manager,
        )

    first_workspace = CoreTaskWorkspace.create(tmp_path, task.id, 1)
    with pytest.raises(RenderTemporaryError):
        adapter().run(
            workspace=first_workspace,
            core_task_id=task.id,
            attempt_no=1,
            **payload,
        )
    assert provider.calls == ["B", "A"]

    second_workspace = CoreTaskWorkspace.create(tmp_path, task.id, 2)
    adapter().run(
        workspace=second_workspace,
        core_task_id=task.id,
        attempt_no=2,
        **payload,
    )
    assert provider.calls.count("B") == 1
    assert provider.calls.count("A") == 2


def test_final_compose_retry_does_not_call_tts_again(tmp_path, task_service, session):
    """配音 bundle 已提交后合成超时，新 attempt 仅重新执行视频合成。"""

    class CountingProvider:
        def __init__(self):
            self.calls = []

        def synthesize(self, text, destination, *, voice_snapshot):
            self.calls.append(text)
            FakeTtsProvider().synthesize(
                text, destination, voice_snapshot=voice_snapshot
            )

    class FailFirstComposeRunner:
        def __init__(self):
            self.fail_compose = True

        @staticmethod
        def write_voice(path):
            with wave.open(str(path), "wb") as output:
                output.setparams((1, 2, 16_000, 32_000, "NONE", "not compressed"))
                output.writeframes(b"\0\0" * 32_000)

        def run(self, argv, **_kwargs):
            if argv[0] == "ffprobe":
                return ProcessResult(
                    0,
                    '{"format":{"duration":"10.0"},"streams":[{"codec_type":"video"}]}',
                    "",
                    False,
                    False,
                    False,
                )
            target = Path(argv[-1])
            if target.name == "voice.wav":
                self.write_voice(target)
                return ProcessResult(0, "", "", False, False, False)
            if target.name == "video_raw.mp4" and self.fail_compose:
                self.fail_compose = False
                return ProcessResult(1, "", "timeout", True, False, False)
            target.write_bytes(b"\x00\x00\x00\x18ftypmp42rendered")
            return ProcessResult(0, "", "", False, False, False)

    payload = request()
    task = task_service.create_core_task(
        caller="narrato-api",
        route="/api/v1/video-render/tasks",
        task_type="video_render",
        idempotency_key="checkpoint-compose-timeout",
        input_snapshot=payload,
    )
    provider = CountingProvider()
    runner = FailFirstComposeRunner()
    manager = TaskCheckpointService(session, FilesystemCheckpointStore(tmp_path))

    def adapter():
        return RenderAdapter(
            MemoryDownloader(),
            FfmpegRenderBackend(
                provider=provider,
                voice_snapshot=payload["voice_snapshot"],
                runner=runner,
            ),
            ArtifactStore(MemoryOss()),
            checkpoint_manager=manager,
        )

    first = CoreTaskWorkspace.create(tmp_path, task.id, 1)
    with pytest.raises(RenderTemporaryError):
        adapter().run(
            workspace=first,
            core_task_id=task.id,
            attempt_no=1,
            **payload,
        )
    assert provider.calls == ["B", "A"]

    second = CoreTaskWorkspace.create(tmp_path, task.id, 2)
    result = adapter().run(
        workspace=second,
        core_task_id=task.id,
        attempt_no=2,
        **payload,
    )
    assert provider.calls == ["B", "A"]
    assert {item["kind"] for item in result["artifacts"]} >= {"video", "voice"}
