from __future__ import annotations

import pytest

from narrato_api.billing.pricing import (
    VOICE_REPLACEMENT_SURCHARGE_CREDITS_PER_MINUTE,
    estimate_short_drama_cost,
    estimate_short_drama_output_seconds,
    estimate_video_translation_cost,
)


@pytest.mark.parametrize(
    ("seconds", "cost"), [(1, 20), (60, 20), (61, 40), (3000, 1000)]
)
def test_short_drama_pricing_rounds_total_duration_up_once(
    seconds: int, cost: int
) -> None:
    assert estimate_short_drama_cost(seconds, credits_per_minute=20) == cost


def test_short_drama_pricing_rejects_negative_duration() -> None:
    with pytest.raises(ValueError, match="total_seconds"):
        estimate_short_drama_cost(-1, credits_per_minute=20)


@pytest.mark.parametrize(
    ("seconds", "estimated_output"), [(0, 0), (1, 1), (60, 10), (61, 10), (522, 84)]
)
def test_short_drama_output_duration_uses_sixteen_percent_compression(
    seconds: int, estimated_output: int
) -> None:
    assert estimate_short_drama_output_seconds(seconds) == estimated_output


@pytest.mark.parametrize(
    ("seconds", "base", "surcharge", "total"),
    [(1, 30, 10, 40), (60, 30, 10, 40), (61, 60, 20, 80), (121, 90, 30, 120)],
)
def test_video_translation_voice_replacement_charges_surcharge_once_per_total_minute(
    seconds: int, base: int, surcharge: int, total: int
) -> None:
    assert estimate_video_translation_cost(
        seconds,
        credits_per_minute=30,
        original_sound_mode="voice_replacement",
    ) == (base, surcharge, total)


def test_video_translation_translated_voice_only_has_no_voice_separation_surcharge():
    assert estimate_video_translation_cost(
        61,
        credits_per_minute=30,
        original_sound_mode="translated_voice_only",
    ) == (60, 0, 60)
    assert VOICE_REPLACEMENT_SURCHARGE_CREDITS_PER_MINUTE == 10


def test_video_translation_pricing_rejects_unknown_audio_mode():
    with pytest.raises(ValueError, match="original_sound_mode"):
        estimate_video_translation_cost(
            60,
            credits_per_minute=30,
            original_sound_mode="unknown",
        )
