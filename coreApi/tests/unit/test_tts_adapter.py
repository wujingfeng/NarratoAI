import httpx
import pytest

from core_api.adapters.narrato.tts import (
    FakeTtsProvider,
    HttpTtsProvider,
    TtsAdapter,
    TtsInputError,
    create_tts_provider,
)
from core_api.infrastructure.oss_client import OssUploadResult
from core_api.runtime.artifact_store import ArtifactStore
from core_api.runtime.workspace import CoreTaskWorkspace


class MemoryOss:
    public_base_url = "https://cdn.example.test"

    def __init__(self):
        self.payloads = {}

    def upload_stream(self, stream, object_key, *, content_type, size):
        data = stream.read()
        assert len(data) == size
        self.payloads[object_key] = data
        return OssUploadResult(
            "fake", object_key, f"https://cdn.example.test/{object_key}"
        )


def test_tts_uses_frozen_voice_and_attempt_workspace(tmp_path):
    oss = MemoryOss()
    adapter = TtsAdapter(FakeTtsProvider(), ArtifactStore(oss))
    workspace = CoreTaskWorkspace.create(tmp_path, "ctask_tts", 1)
    result = adapter.run(
        workspace=workspace,
        core_task_id="ctask_tts",
        attempt_no=1,
        voice_id="voice_stable",
        voice_snapshot={"voice_id": "voice_stable", "provider_voice_code": "v1"},
        segments=[{"text": "第一句", "start": 0.0, "end": 1.0}],
    )
    assert result["artifacts"][0]["kind"] == "voice"
    assert result["artifacts"][0]["url"].startswith("https://")
    assert list(workspace.output_dir.glob("*.wav"))


def test_tts_rejects_voice_snapshot_mismatch(tmp_path):
    adapter = TtsAdapter(FakeTtsProvider(), ArtifactStore(MemoryOss()))
    workspace = CoreTaskWorkspace.create(tmp_path, "ctask_tts", 1)
    with pytest.raises(TtsInputError):
        adapter.run(
            workspace=workspace,
            core_task_id="ctask_tts",
            attempt_no=1,
            voice_id="voice_a",
            voice_snapshot={"voice_id": "voice_b"},
            segments=[{"text": "x", "start": 0, "end": 1}],
        )


def test_production_http_tts_uses_frozen_endpoint_secret_and_voice(tmp_path):
    observed = {}
    expected = tmp_path / "expected.wav"
    FakeTtsProvider().synthesize("x", expected, voice_snapshot={})

    def respond(request):
        observed["url"] = str(request.url)
        observed["authorization"] = request.headers["Authorization"]
        observed["body"] = request.content
        return httpx.Response(200, content=expected.read_bytes())

    provider = HttpTtsProvider(
        endpoint="https://tts.example.test/v1/speech",
        api_key="secret-a",
        transport=httpx.MockTransport(respond),
    )
    target = tmp_path / "actual.wav"
    provider.synthesize(
        "production text",
        target,
        voice_snapshot={
            "provider_voice_code": "voice-provider-a",
            "output_format": "wav",
            "sample_rate": 16_000,
        },
    )
    assert observed["url"] == "https://tts.example.test/v1/speech"
    assert observed["authorization"] == "Bearer secret-a"
    assert b"voice-provider-a" in observed["body"]
    assert b"sample_rate" in observed["body"]
    assert target.read_bytes() == expected.read_bytes()


def test_unknown_production_provider_does_not_fallback_fake(tmp_path):
    provider = create_tts_provider(
        "unknown", voice_snapshot={"provider_settings": {}}, api_key=""
    )
    with pytest.raises(TtsInputError, match="TTS_PROVIDER_UNAVAILABLE"):
        provider.synthesize("x", tmp_path / "voice.wav", voice_snapshot={})
