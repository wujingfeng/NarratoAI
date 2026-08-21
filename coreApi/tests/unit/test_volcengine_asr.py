from __future__ import annotations

from dataclasses import dataclass

import pytest

from core_api.adapters.narrato.volcengine_asr import (
    VolcengineAsrAuthError,
    VolcengineAsrInputError,
    VolcengineAsrTranscriber,
    volcengine_result_to_srt,
)


@dataclass
class FakeResponse:
    payload: dict

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self.payload


class FakeSession:
    def __init__(self, responses: list[dict]) -> None:
        self.responses = iter(responses)
        self.calls: list[tuple[str, dict, dict]] = []

    def post(self, url: str, *, json: dict, headers: dict, timeout: int) -> FakeResponse:
        self.calls.append((url, json, headers))
        return FakeResponse(next(self.responses))


def test_volcengine_result_to_srt_uses_utterance_timestamps():
    srt = volcengine_result_to_srt(
        {"resp": {"utterances": [{"text": "你好", "start_time": 1500, "end_time": 3000}]}}
    )
    assert srt == "1\n00:00:01,500 --> 00:00:03,000\n你好\n"


def test_volcengine_transcriber_submits_polls_and_writes_srt(tmp_path):
    session = FakeSession(
        [
            {"resp": {"code": 1000, "id": "task-1"}},
            {"resp": {"code": 2000, "message": "processing"}},
            {"resp": {"code": 1000, "utterances": [{"text": "字幕", "start_time": 0, "end_time": 500}]}},
        ]
    )
    transcriber = VolcengineAsrTranscriber(
        appid="app", token="token", cluster="cluster", poll_interval_seconds=0.0001, session=session
    )
    output = tmp_path / "output.srt"
    assert transcriber("https://cdn.example.test/video.mp4", "mp4", str(output)) == str(output)
    assert output.read_text(encoding="utf-8") == "1\n00:00:00,000 --> 00:00:00,500\n字幕\n"
    assert session.calls[0][1]["audio"] == {"url": "https://cdn.example.test/video.mp4", "format": "mp4"}
    assert session.calls[0][2]["Authorization"] == "Bearer; token"


@pytest.mark.parametrize(
    ("code", "exception"),
    [(1002, VolcengineAsrAuthError), (1012, VolcengineAsrInputError)],
)
def test_volcengine_transcriber_classifies_terminal_errors(tmp_path, code, exception):
    transcriber = VolcengineAsrTranscriber(
        appid="app", token="token", cluster="cluster", session=FakeSession([{"resp": {"code": code, "message": "failed"}}])
    )
    with pytest.raises(exception):
        transcriber("https://cdn.example.test/video.mp4", "mp4", str(tmp_path / "out.srt"))
