from __future__ import annotations


def estimate_short_drama_cost(
    total_seconds: int, *, credits_per_minute: int = 20
) -> int:
    """按全部已验证视频总秒数整体向上取整计算整数创作点。"""

    if total_seconds < 0:
        raise ValueError("total_seconds must not be negative")
    if credits_per_minute <= 0:
        raise ValueError("credits_per_minute must be positive")
    return ((total_seconds + 59) // 60) * credits_per_minute
