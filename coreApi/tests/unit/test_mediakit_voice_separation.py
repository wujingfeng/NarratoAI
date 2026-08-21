from __future__ import annotations

import pytest

from core_api.adapters.narrato.mediakit_voice_separation import (
    MediaKitVoiceSeparator,
    MediaKitVoiceSeparationAuthError,
    MediaKitVoiceSeparationInputError,
    MediaKitVoiceSeparationTaskError,
    MediaKitVoiceSeparationTimeoutError,
)


class FakeResponse:
    def __init__(self, status_code: int, payload: object, *, chunks=(), headers=None):
        self.status_code = status_code
        self._payload = payload
        self._chunks = list(chunks)
        self.headers = headers or {}

    def json(self):
        if isinstance(self._payload, BaseException):
            raise self._payload
        return self._payload

    def iter_content(self, *, chunk_size: int):
        assert chunk_size == 64 * 1024
        yield from self._chunks

    def close(self):
        return None


class FakeSession:
    def __init__(self, *, post_responses, get_responses):
        self.post_responses = list(post_responses)
        self.get_responses = list(get_responses)
        self.post_calls = []
        self.get_calls = []

    def post(self, url, **kwargs):
        self.post_calls.append((url, kwargs))
        return self.post_responses.pop(0)

    def get(self, url, **kwargs):
        self.get_calls.append((url, kwargs))
        return self.get_responses.pop(0)


class Clock:
    def __init__(self):
        self.now = 0.0

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


def _client(session: FakeSession, clock: Clock | None = None) -> MediaKitVoiceSeparator:
    clock = clock or Clock()
    return MediaKitVoiceSeparator(
        api_key="test-mediakit-secret",
        poll_interval_seconds=2,
        total_timeout_seconds=20,
        queue_id="queue-1",
        session=session,
        monotonic=clock.monotonic,
        sleep=clock.sleep,
    )


def test_submits_polls_and_downloads_wav_background_audio(tmp_path):
    session = FakeSession(
        post_responses=[
            FakeResponse(
                200,
                {
                    "success": True,
                    "task_id": "amk-tool-separate-voice-1",
                    "request_id": "submit-request-1",
                },
            )
        ],
        get_responses=[
            FakeResponse(
                200,
                {
                    "success": True,
                    "task_id": "amk-tool-separate-voice-1",
                    "status": "running",
                    "request_id": "poll-request-1",
                },
            ),
            FakeResponse(
                200,
                {
                    "success": True,
                    "task_id": "amk-tool-separate-voice-1",
                    "status": "completed",
                    "request_id": "poll-request-2",
                    "expires_at": "1777464650",
                    "result": {
                        "background_audio_url": "https://media.volcvideo.com/background.wav?auth_key=1"
                    },
                },
            ),
            FakeResponse(200, {}, chunks=[b"wave", b"-audio"]),
        ],
    )
    heartbeats = []
    client = _client(session)

    result = client.separate(
        video_url="https://cdn.example.test/narrato/api/source.mp4",
        client_token="narrato-vs-stable-token",
        heartbeat=lambda: heartbeats.append("tick"),
    )
    target = client.download_background_audio(
        result.background_audio_url,
        tmp_path / "background.wav",
        heartbeat=lambda: heartbeats.append("download"),
    )

    submit_url, submit_kwargs = session.post_calls[0]
    assert submit_url.endswith("/tools/separate-voice")
    assert submit_kwargs["json"] == {
        "video_url": "https://cdn.example.test/narrato/api/source.mp4",
        "output_format": "wav",
        "client_token": "narrato-vs-stable-token",
        "queue_id": "queue-1",
    }
    assert submit_kwargs["headers"]["Authorization"] == "Bearer test-mediakit-secret"
    assert result.task_id == "amk-tool-separate-voice-1"
    assert result.request_id == "poll-request-2"
    assert result.expires_at == 1777464650
    assert target.read_bytes() == b"wave-audio"
    assert len(heartbeats) >= 5
    # 临时下载 URL 不携带 API Key，避免把凭据转发给结果存储 Host。
    assert "headers" not in session.get_calls[-1][1]


def test_failed_task_preserves_provider_diagnostics_without_api_key():
    session = FakeSession(
        post_responses=[
            FakeResponse(
                200,
                {"success": True, "task_id": "task-1", "request_id": "request-submit"},
            )
        ],
        get_responses=[
            FakeResponse(
                200,
                {
                    "success": True,
                    "task_id": "task-1",
                    "status": "failed",
                    "request_id": "request-poll",
                    "error": {
                        "code": "DownloadFailed",
                        "message": "download failed: https://cdn.example.test/source.mp4?auth_key=secret",
                        "param": "video_url",
                        "type": "TaskError",
                    },
                },
            )
        ],
    )

    with pytest.raises(MediaKitVoiceSeparationTaskError) as error:
        _client(session).separate(
            video_url="https://cdn.example.test/narrato/api/source.mp4",
            client_token="narrato-vs-stable-token",
        )

    assert error.value.details == {
        "request_id": "request-poll",
        "provider_error_code": "DownloadFailed",
        "provider_error_param": "video_url",
        "provider_error_type": "TaskError",
        "task_id": "task-1",
    }
    assert "test-mediakit-secret" not in repr(error.value.details)
    assert "auth_key" not in repr(error.value.details)


def test_auth_error_and_poll_timeout_are_classified():
    auth_session = FakeSession(
        post_responses=[
            FakeResponse(
                401,
                {
                    "success": False,
                    "request_id": "request-auth",
                    "error": {"code": "InvalidApiKey", "message": "denied"},
                },
            )
        ],
        get_responses=[],
    )
    with pytest.raises(MediaKitVoiceSeparationAuthError):
        _client(auth_session).separate(
            video_url="https://cdn.example.test/narrato/api/source.mp4",
            client_token="narrato-vs-stable-token",
        )

    clock = Clock()
    timeout_session = FakeSession(
        post_responses=[
            FakeResponse(
                200,
                {
                    "success": True,
                    "task_id": "task-timeout",
                    "request_id": "request-submit",
                },
            )
        ],
        get_responses=[
            FakeResponse(
                200,
                {
                    "success": True,
                    "task_id": "task-timeout",
                    "status": "running",
                    "request_id": "request-poll",
                },
            )
        ],
    )
    client = _client(timeout_session, clock)
    client.total_timeout_seconds = 1
    with pytest.raises(MediaKitVoiceSeparationTimeoutError) as error:
        client.separate(
            video_url="https://cdn.example.test/narrato/api/source.mp4",
            client_token="narrato-vs-stable-token",
        )
    assert error.value.details == {
        "task_id": "task-timeout",
        "request_id": "request-poll",
    }


def test_non_json_401_is_still_classified_as_auth_failure():
    session = FakeSession(
        post_responses=[FakeResponse(401, ValueError("html response"))],
        get_responses=[],
    )

    with pytest.raises(MediaKitVoiceSeparationAuthError):
        _client(session).submit(
            video_url="https://cdn.example.test/source.mp4",
            client_token="stable-token",
        )


def test_unsupported_persistent_output_destination_fails_before_submit():
    session = FakeSession(post_responses=[FakeResponse(200, {})], get_responses=[])
    client = _client(session)
    client.media_output_destination = "tos://private-bucket"

    with pytest.raises(
        MediaKitVoiceSeparationInputError, match="OUTPUT_DESTINATION_UNSUPPORTED"
    ):
        client.submit(
            video_url="https://cdn.example.test/source.mp4",
            client_token="stable-token",
        )

    assert session.post_calls == []


def test_rejects_non_https_or_non_allowlisted_result_url(tmp_path):
    session = FakeSession(
        post_responses=[
            FakeResponse(
                200, {"success": True, "task_id": "task-1", "request_id": "submit"}
            )
        ],
        get_responses=[
            FakeResponse(
                200,
                {
                    "success": True,
                    "task_id": "task-1",
                    "status": "completed",
                    "request_id": "poll",
                    "result": {"background_audio_url": "tos://bucket/background.wav"},
                },
            )
        ],
    )
    with pytest.raises(Exception, match="RESULT_URL_UNSUPPORTED"):
        _client(session).separate(
            video_url="https://cdn.example.test/narrato/api/source.mp4",
            client_token="narrato-vs-stable-token",
        )
    assert not (tmp_path / "background.wav").exists()

    untrusted_session = FakeSession(
        post_responses=[
            FakeResponse(
                200, {"success": True, "task_id": "task-2", "request_id": "submit"}
            )
        ],
        get_responses=[
            FakeResponse(
                200,
                {
                    "success": True,
                    "task_id": "task-2",
                    "status": "completed",
                    "request_id": "poll",
                    "result": {
                        "background_audio_url": "https://127.0.0.1/internal.wav"
                    },
                },
            )
        ],
    )
    with pytest.raises(Exception, match="RESULT_HOST_REJECTED"):
        _client(untrusted_session).separate(
            video_url="https://cdn.example.test/narrato/api/source.mp4",
            client_token="narrato-vs-stable-token",
        )


def test_download_revalidates_result_host_before_network_access(tmp_path):
    session = FakeSession(
        post_responses=[],
        get_responses=[FakeResponse(200, {}, chunks=[b"not-used"])],
    )

    with pytest.raises(MediaKitVoiceSeparationInputError, match="HOST_REJECTED"):
        _client(session).download_background_audio(
            "https://metadata.internal.example/background.wav",
            tmp_path / "background.wav",
        )

    assert session.get_calls == []
    assert not (tmp_path / "background.wav").exists()


def test_resume_polls_existing_task_without_resubmission():
    session = FakeSession(
        post_responses=[],
        get_responses=[
            FakeResponse(
                200,
                {
                    "success": True,
                    "task_id": "existing-task",
                    "status": "completed",
                    "request_id": "poll-request",
                    "result": {
                        "background_audio_url": "https://result.volces.com/background.wav"
                    },
                },
            )
        ],
    )

    result = _client(session).poll(
        task_id="existing-task", submit_request_id="submit-request"
    )

    assert result.task_id == "existing-task"
    assert result.request_id == "poll-request"
    assert session.post_calls == []


def test_poll_rejects_task_id_path_injection_before_network_access():
    session = FakeSession(post_responses=[], get_responses=[FakeResponse(200, {})])

    with pytest.raises(
        MediaKitVoiceSeparationInputError, match="TASK_REFERENCE_INVALID"
    ):
        _client(session).poll(
            task_id="../tools/separate-voice?leak=1",
            submit_request_id="submit-request",
        )

    assert session.get_calls == []
