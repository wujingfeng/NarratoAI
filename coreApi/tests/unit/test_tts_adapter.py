import httpx
import base64
import json
import wave
import pytest

from core_api.adapters.narrato.tts import (
    FakeTtsProvider,
    HttpTtsProvider,
    TtsAdapter,
    TtsInputError,
    VolcengineTtsProvider,
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


def test_translation_tts_automatically_fits_audio_to_its_segment_and_reports_duration(
    tmp_path,
):
    class DurationProvider:
        def __init__(self):
            self.speeds = []

        def synthesize(self, text, target, *, voice_snapshot):
            speed = float(voice_snapshot["speed_ratio"])
            self.speeds.append(speed)
            frames = round(1.2 / speed * 16_000)
            with wave.open(str(target), "wb") as output:
                output.setparams((1, 2, 16_000, frames, "NONE", "not compressed"))
                output.writeframes(b"\0\0" * frames)

    provider = DurationProvider()
    workspace = CoreTaskWorkspace.create(tmp_path, "ctask_translationtts", 1)
    result = TtsAdapter(provider, ArtifactStore(MemoryOss())).run(
        workspace=workspace,
        core_task_id="ctask_translationtts",
        attempt_no=1,
        voice_id="voice_a",
        voice_snapshot={"voice_id": "voice_a", "sample_rate": 16_000},
        segments=[
            {
                "segment_id": "seg_1",
                "segment_index": 0,
                "text": "A translated sentence",
                "start": 0,
                "end": 1,
                "voice_id": "voice_a",
                "speed": 1.0,
                "volume": 80,
                "allowed_duration_ms": 1_000,
                "timing_tolerance_ms": 100,
            }
        ],
    )

    assert provider.speeds == pytest.approx([1.0])
    timing = result["metadata"]["segment_timings"][0]
    assert timing["segment_id"] == "seg_1"
    assert timing["segment_index"] == 0
    assert timing["start_ms"] == 0 and timing["end_ms"] == 1000
    assert timing["tts_duration_ms"] <= 1000
    assert timing["adapted_speed"] == pytest.approx(1.2)
    assert timing["timing_fit_status"] == "speed_adjusted"
    assert timing["timing_overflow_ms"] == 0


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


def test_tts_submits_each_subtitle_as_a_separate_provider_request(tmp_path):
    class RecordingProvider:
        def __init__(self):
            self.texts = []

        def synthesize(self, text, target, *, voice_snapshot):
            self.texts.append(text)
            FakeTtsProvider().synthesize(text, target, voice_snapshot=voice_snapshot)

    provider = RecordingProvider()
    adapter = TtsAdapter(provider, ArtifactStore(MemoryOss()))
    workspace = CoreTaskWorkspace.create(tmp_path, "ctask_tts", 1)

    result = adapter.run(
        workspace=workspace,
        core_task_id="ctask_tts",
        attempt_no=1,
        voice_id="voice_stable",
        voice_snapshot={"voice_id": "voice_stable", "provider_voice_code": "v1"},
        segments=[
            {"text": "短句", "start": 0.0, "end": 1.0},
            {"text": "这是长度不同的第二句字幕", "start": 1.0, "end": 2.0},
        ],
    )

    assert provider.texts == ["短句", "这是长度不同的第二句字幕"]
    assert result["metadata"] == {"segments": 2}


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


def test_volcengine_tts_uses_frozen_credentials_and_decodes_wav(tmp_path):
    expected = tmp_path / "expected.wav"
    FakeTtsProvider().synthesize("x", expected, voice_snapshot={})
    observed = {}

    def respond(request):
        observed["authorization"] = request.headers["Authorization"]
        observed["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={"code": 3000, "data": base64.b64encode(expected.read_bytes()).decode()},
        )

    provider = VolcengineTtsProvider(
        endpoint="https://openspeech.bytedance.com/api/v1/tts",
        appid="app-real",
        token="token-real",
        transport=httpx.MockTransport(respond),
    )
    target = tmp_path / "actual.wav"
    provider.synthesize(
        "真实配音",
        target,
        voice_snapshot={
            "provider_voice_code": "BV700_V2_streaming",
            "sample_rate": 16000,
            "speed_ratio": 1.25,
        },
    )

    assert observed["authorization"] == "Bearer;token-real"
    assert observed["payload"]["app"] == {
        "appid": "app-real",
        "token": "token-real",
        "cluster": "volcano_tts",
    }
    assert observed["payload"]["audio"]["encoding"] == "wav"
    assert observed["payload"]["audio"]["speed_ratio"] == 1.25
    assert target.read_bytes() == expected.read_bytes()


def test_volcengine_factory_accepts_private_json_credential(tmp_path):
    provider = create_tts_provider(
        "volcengine",
        voice_snapshot={
            "provider_settings": {
                "tts_endpoint": "https://openspeech.bytedance.com/api/v1/tts",
                "cluster": "volcano_tts",
            }
        },
        api_key='{"appid":"app-id","token":"token-value"}',
    )
    assert isinstance(provider, VolcengineTtsProvider)
    assert provider.appid == "app-id"
    assert provider.token == "token-value"
