from __future__ import annotations

import json
from contextlib import contextmanager
from urllib.error import HTTPError

import pytest

from narrato_api.integrations.core_client import (
    CoreClientRejectedError,
    HttpCoreClient,
    MediaProbeResult,
)


class FakeResponse:
    def __init__(self, *, status: int, payload: dict[str, object]) -> None:
        self.status = status
        self._payload = payload

    def read(self) -> bytes:
        return json.dumps(self._payload).encode()

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *_args: object) -> None:
        return None


def test_core_client_polls_real_task_endpoint_after_202(monkeypatch) -> None:
    requests = []

    @contextmanager
    def fake_urlopen(request, timeout: int):
        requests.append(request)
        if request.get_method() == "POST":
            yield FakeResponse(
                status=202,
                payload={"data": {"core_task_id": "core_1", "status": "queued"}},
            )
        else:
            yield FakeResponse(
                status=200,
                payload={
                    "data": {
                        "core_task_id": "core_1",
                        "status": "succeeded",
                        "result": {"media_type": "video", "duration_seconds": 90.5},
                    }
                },
            )

    monkeypatch.setattr("narrato_api.integrations.core_client.urlopen", fake_urlopen)
    client = HttpCoreClient(base_url="https://core.example.test", request_token="token")

    dispatched = client.probe_media(
        source_url="https://cdn.example.test/narrato/api/a.mp4",
        media_type="video",
        declared_extension=".mp4",
        caller_task_id="ast_1",
    )
    result = client.get_probe_result("core_1")

    assert dispatched == MediaProbeResult(valid=None, core_task_id="core_1")
    assert result == MediaProbeResult(
        valid=True, core_task_id="core_1", duration_seconds=90.5
    )
    assert [item.get_method() for item in requests] == ["POST", "GET"]
    assert requests[1].full_url.endswith("/api/v1/tasks/core_1")


def test_core_client_reports_core_validation_rejection_separately(monkeypatch) -> None:
    def reject(*_args: object, **_kwargs: object) -> None:
        raise HTTPError("https://core.example.test/api/v1/media-probe/tasks", 422, "", {}, None)

    monkeypatch.setattr("narrato_api.integrations.core_client.urlopen", reject)
    client = HttpCoreClient(base_url="https://core.example.test", request_token="token")

    with pytest.raises(CoreClientRejectedError):
        client.probe_media(
            source_url="https://cdn.example.test/narrato/api/theme.mp3",
            media_type="audio",
            declared_extension="mp3",
            caller_task_id="ast_audio",
        )
