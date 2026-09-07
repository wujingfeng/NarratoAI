from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace

import pytest
import requests

from core_api.adapters.narrato.asr import AsrAdapter
from core_api.adapters.narrato.volcengine_asr import (
    VolcengineAsrAuthError,
    VolcengineAsrInputError,
    VolcengineAsrQuotaError,
    VolcengineAsrRequestError,
    VolcengineAsrTemporaryError,
    VolcengineAsrTranscriber,
    volcengine_result_to_srt,
)
from core_api.infrastructure.oss_client import OssUploadResult
from core_api.runtime.artifact_store import ArtifactStore
from core_api.runtime.process_runner import ProcessResult
from core_api.runtime.workspace import CoreTaskWorkspace


@dataclass
class FakeResponse:
    payload: dict
    status_code: int = 200
    headers: dict[str, str] = field(default_factory=dict)

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(response=self)

    def json(self) -> dict:
        return self.payload


class FakeSession:
    def __init__(self, responses: list[dict | FakeResponse]) -> None:
        self.responses = iter(responses)
        self.calls: list[tuple[str, dict, dict]] = []

    def post(
        self, url: str, *, json: dict, headers: dict, timeout: int
    ) -> FakeResponse:
        self.calls.append((url, json, headers))
        response = next(self.responses)
        return (
            response if isinstance(response, FakeResponse) else FakeResponse(response)
        )


class FakeJobStore:
    def __init__(self) -> None:
        self.job = SimpleNamespace(
            id="asrj-test",
            callback_key="c" * 40,
            provider_task_id=None,
            prepared_audio_url=None,
            status="preparing",
            response_payload=None,
            error=None,
        )

    def get_or_create(self, **_kwargs):
        return self.job

    def mark_submitted(self, _job_id, provider_task_id):
        self.job.provider_task_id = provider_task_id
        self.job.status = "submitted"
        return self.job

    def get(self, _job_id):
        return self.job

    def record_provider_response(self, _job_id, *, payload, status, error=None):
        self.job.response_payload = payload
        self.job.status = status
        self.job.error = error
        return self.job

    def set_prepared_audio(self, _job_id, *, artifact, attempt_no):
        assert attempt_no == 1
        self.job.prepared_audio_url = artifact["url"]
        return self.job


def make_transcriber(session, **kwargs):
    callback_base_url = kwargs.pop(
        "callback_base_url", "https://core.example.test"
    )
    return VolcengineAsrTranscriber(
        appid="app",
        token="token",
        cluster="cluster",
        session=session,
        callback_base_url=callback_base_url,
        job_store=FakeJobStore(),
        **kwargs,
    )


def test_volcengine_transcriber_accepts_documented_http_callback():
    """火山文档明确将 callback 定义为业务方 HTTP 回调地址。"""

    transcriber = make_transcriber(
        FakeSession([]), callback_base_url="http://core.example.test"
    )

    assert transcriber.callback_base_url == "http://core.example.test/"


def run_transcriber(transcriber, source_url, fmt, output):
    return transcriber(
        source_url,
        fmt,
        str(output),
        core_task_id="ctask_test",
        source_index=0,
        source_asset_id="asset_test",
    )


def test_volcengine_result_to_srt_uses_utterance_timestamps():
    srt = volcengine_result_to_srt(
        {
            "resp": {
                "utterances": [{"text": "你好", "start_time": 1500, "end_time": 3000}]
            }
        }
    )
    assert srt == "1\n00:00:01,500 --> 00:00:03,000\n你好\n"


def test_volcengine_transcriber_accepts_documented_string_codes_and_logs_paths(
    tmp_path, caplog
):
    session = FakeSession(
        [
            {"resp": {"code": "1000", "id": "task-1"}},
            {"resp": {"code": "2000", "message": "processing"}},
            {"resp": {"code": "2001", "message": "queued"}},
            {
                "resp": {
                    "code": "1000",
                    "utterances": [{"text": "字幕", "start_time": 0, "end_time": 500}],
                }
            },
        ]
    )
    transcriber = make_transcriber(
        session,
        poll_interval_seconds=0.0001,
    )
    output = tmp_path / "output.srt"
    assert run_transcriber(
        transcriber, "https://cdn.example.test/video.mp4", "mp4", output
    ) == str(output)
    assert (
        output.read_text(encoding="utf-8") == "1\n00:00:00,000 --> 00:00:00,500\n字幕\n"
    )
    assert session.calls[0][1] == {
        "app": {"appid": "app", "token": "token", "cluster": "cluster"},
        "user": {"uid": "narrato-core"},
        "audio": {
            "url": "https://cdn.example.test/video.mp4",
            "format": "mp4",
        },
        "request": {
            "callback": "https://core.example.test/api/v1/asr/callbacks/"
            + "c" * 40
        },
        "additions": {
            "language": "zh-CN",
            "use_itn": "True",
            "use_punc": "True",
            "with_speaker_info": "False",
            "enable_query": "True",
        },
    }
    assert session.calls[1][1] == {
        "appid": "app",
        "token": "token",
        "cluster": "cluster",
        "id": "task-1",
    }
    assert session.calls[2][1] == session.calls[1][1]
    assert session.calls[0][2]["Authorization"] == "Bearer; token"
    assert "endpoint_path=/api/v1/auc/submit" in caplog.text
    assert "endpoint_path=/api/v1/auc/query" in caplog.text
    assert "source_path=/video.mp4" in caplog.text


@pytest.mark.parametrize(
    ("code", "exception", "retryable"),
    [
        (1001, VolcengineAsrRequestError, False),
        (1002, VolcengineAsrAuthError, False),
        (1003, VolcengineAsrTemporaryError, True),
        (1004, VolcengineAsrQuotaError, False),
        (1012, VolcengineAsrInputError, False),
        (1021, VolcengineAsrTemporaryError, True),
    ],
)
def test_volcengine_transcriber_classifies_terminal_errors(
    tmp_path, code, exception, retryable
):
    transcriber = make_transcriber(
        FakeSession([{"resp": {"code": code, "message": "failed"}}])
    )
    with pytest.raises(exception) as caught:
        run_transcriber(
            transcriber,
            "https://cdn.example.test/video.mp4",
            "mp4",
            tmp_path / "out.srt",
        )
    assert caught.value.retryable is retryable


def test_volcengine_transcriber_classifies_json_error_body_on_http_400(tmp_path):
    response = FakeResponse(
        {"resp": {"code": 1001, "message": "invalid query"}},
        status_code=400,
        headers={"X-Tt-Logid": "log-id"},
    )
    transcriber = make_transcriber(
        FakeSession([{"resp": {"code": 1000, "id": "task-1"}}, response])
    )

    with pytest.raises(VolcengineAsrRequestError):
        run_transcriber(
            transcriber,
            "https://cdn.example.test/video.mp4",
            "mp4",
            tmp_path / "out.srt",
        )


@pytest.mark.parametrize(
    ("status", "exception", "retryable"),
    [
        (400, VolcengineAsrRequestError, False),
        (401, VolcengineAsrAuthError, False),
        (403, VolcengineAsrAuthError, False),
        (429, VolcengineAsrTemporaryError, True),
        (503, VolcengineAsrTemporaryError, True),
    ],
)
def test_volcengine_transcriber_classifies_http_status_without_provider_code(
    tmp_path, status, exception, retryable
):
    transcriber = make_transcriber(
        FakeSession([FakeResponse({}, status_code=status)])
    )
    with pytest.raises(exception) as caught:
        run_transcriber(
            transcriber,
            "https://cdn.example.test/audio.mp3",
            "mp3",
            tmp_path / "out.srt",
        )
    assert caught.value.retryable is retryable


def test_source_transcriber_uses_validated_cdn_url_without_local_download(tmp_path):
    class NeverDownload:
        def download(self, *_args, **_kwargs):
            raise AssertionError("远程 ASR 不应下载媒体到本地")

    class FakeOss:
        public_base_url = "https://cdn.example.test"

        def upload_stream(self, _stream, object_key, *, content_type, size):
            assert content_type == "application/x-subrip; charset=utf-8"
            assert size > 0
            return OssUploadResult(
                bucket="test",
                object_key=object_key,
                url=f"https://cdn.example.test/{object_key}",
            )

        def delete_object(self, _object_key):
            return None

    received: list[tuple[str, str]] = []

    def transcribe(source_url: str, fmt: str, subtitle_file: str, **_kwargs) -> str:
        received.append((source_url, fmt))
        Path(subtitle_file).write_text(
            "1\n00:00:00,000 --> 00:00:00,500\n字幕\n", encoding="utf-8"
        )
        return subtitle_file

    adapter = AsrAdapter(
        downloader=NeverDownload(),
        transcriber=None,
        source_transcriber=transcribe,
        source_url_validator=lambda url: f"validated:{url}",
        artifact_store=ArtifactStore(FakeOss()),
    )
    result = adapter.run(
        sources=[
            {
                "source_asset_id": "asset_test",
                "source_url": "https://cdn.example.test/narrato/api/audio.mp3",
                "declared_extension": "mp3",
            }
        ],
        core_task_id="ctask_test",
        attempt_no=1,
        workspace=CoreTaskWorkspace.create(tmp_path, "ctask_test", 1),
    )

    assert received == [
        ("validated:https://cdn.example.test/narrato/api/audio.mp3", "mp3")
    ]
    assert result["artifacts"][0]["kind"] == "subtitle"


def test_video_source_is_extracted_to_mp3_uploaded_then_submitted(tmp_path):
    class Downloader:
        def download(self, _url, destination, *, max_bytes):
            assert max_bytes > 0
            destination.write_bytes(b"video")

    class Runner:
        def run(self, argv, **_kwargs):
            assert argv[0] == "ffmpeg" and "-vn" in argv
            Path(argv[-1]).write_bytes(b"mp3")
            return ProcessResult(0, "", "", False, False, False)

    class Oss:
        public_base_url = "https://cdn.example.test"

        def upload_stream(self, stream, object_key, *, content_type, size):
            assert size > 0
            stream.read()
            return OssUploadResult(
                "bucket", object_key, f"https://cdn.example.test/{object_key}"
            )

        def delete_object(self, _object_key):
            return None

    received = []

    def transcribe(url, fmt, target, **_kwargs):
        received.append((url, fmt))
        Path(target).write_text(
            "1\n00:00:00,000 --> 00:00:00,500\n字幕\n", encoding="utf-8"
        )
        return target

    jobs = FakeJobStore()
    adapter = AsrAdapter(
        downloader=Downloader(),
        transcriber=None,
        artifact_store=ArtifactStore(Oss()),
        source_transcriber=transcribe,
        source_url_validator=lambda url: url,
        process_runner=Runner(),
        provider_job_store=jobs,
    )
    result = adapter.run(
        sources=[
            {
                "source_asset_id": "asset_video",
                "source_url": "https://cdn.example.test/narrato/api/video.mov",
                "declared_extension": "mov",
            }
        ],
        core_task_id="ctask_video",
        attempt_no=1,
        workspace=CoreTaskWorkspace.create(tmp_path, "ctask_video", 1),
    )
    assert received == [(jobs.job.prepared_audio_url, "mp3")]
    assert jobs.job.prepared_audio_url.endswith(".mp3")
    assert result["subtitles"][0]["source_asset_id"] == "asset_video"
