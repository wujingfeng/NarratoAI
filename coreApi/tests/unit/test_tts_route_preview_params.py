from core_api.api.routes.tts import TtsTaskRequest


def test_tts_request_accepts_translation_preview_speed_and_volume() -> None:
    payload = TtsTaskRequest.model_validate(
        {
            "voice_id": "voice_1",
            "language": "en",
            "segments": [{"text": "hello", "start": 0, "end": 3}],
            "speed": 1.1,
            "volume": 80,
            "caller_task_id": "translation-preview:abc",
        }
    )

    assert payload.speed == 1.1
    assert payload.volume == 80


def test_tts_request_still_rejects_legacy_preview_wrapper() -> None:
    try:
        TtsTaskRequest.model_validate(
            {
                "voice_id": "voice_1",
                "segments": [{"text": "hello", "start": 0, "end": 3}],
                "translation_preview": {"speed": 1.1, "volume": 80},
            }
        )
    except ValueError:
        pass
    else:
        raise AssertionError("legacy preview wrapper must be rejected")
