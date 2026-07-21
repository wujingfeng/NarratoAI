from __future__ import annotations

import pytest

from narrato_api.billing.pricing import estimate_short_drama_cost


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
