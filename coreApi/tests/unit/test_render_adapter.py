import json
from pathlib import Path

import pytest

from core_api.adapters.narrato.render import (
    FakeRenderBackend,
    FfmpegRenderBackend,
    RenderAdapter,
    RenderInputError,
)
from core_api.adapters.narrato.tts import FakeTtsProvider
from core_api.infrastructure.oss_client import DownloadReceipt, OssUploadResult
from core_api.runtime.artifact_store import ArtifactStore
from core_api.runtime.artifact_store import ArtifactSecurityError
from core_api.runtime.process_runner import ProcessResult
from core_api.runtime.workspace import CoreTaskWorkspace


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
                return ProcessResult(0, "10.0\n", "", False, False, False)
            if str(argv[-1]).endswith(".wav"):
                FakeTtsProvider().synthesize("x", Path(argv[-1]), voice_snapshot={})
            else:
                Path(argv[-1]).write_bytes(b"rendered")
            return ProcessResult(0, "", "", False, False, False)

    runner = Runner()
    source = tmp_path / "input.mp4"
    source.write_bytes(b"video")
    beats = []
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
                "narration": "A",
            }
        ],
        output_dir=tmp_path,
        heartbeat=lambda: beats.append(1),
    )
    assert len(runner.calls) == 4 and len(beats) == 4
    assert all(
        call[0][0] == "ffmpeg" and call[0][1] == "-nostdin" for call in runner.calls[1:]
    )
    assert all(call[1]["timeout_seconds"] == 1800 for call in runner.calls[1:])
    assert result["video"].read_bytes() == b"rendered"


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
