from __future__ import annotations

import math


SHORT_DRAMA_OUTPUT_COMPRESSION_RATIO = 0.16
VOICE_REPLACEMENT_SURCHARGE_CREDITS_PER_MINUTE = 10


def estimate_short_drama_cost(
    total_seconds: int, *, credits_per_minute: int = 20
) -> int:
    """按全部已验证视频总秒数整体向上取整计算整数创作点。"""

    if total_seconds < 0:
        raise ValueError("total_seconds must not be negative")
    if credits_per_minute <= 0:
        raise ValueError("credits_per_minute must be positive")
    return ((total_seconds + 59) // 60) * credits_per_minute


def estimate_short_drama_output_seconds(total_seconds: int) -> int:
    """按当前短剧解说产品的 16% 压缩比例预估成片时长。"""

    if total_seconds < 0:
        raise ValueError("total_seconds must not be negative")
    if total_seconds == 0:
        return 0
    return math.ceil(total_seconds * SHORT_DRAMA_OUTPUT_COMPRESSION_RATIO)


def estimate_video_translation_cost(
    total_seconds: int,
    *,
    credits_per_minute: int,
    original_sound_mode: str,
    voice_replacement_surcharge_credits_per_minute: int = (
        VOICE_REPLACEMENT_SURCHARGE_CREDITS_PER_MINUTE
    ),
) -> tuple[int, int, int]:
    """返回翻译基础费、人声分离附加费及总费用。

    对传入的源视频总时长整体向上取整分钟。仅 ``voice_replacement`` 会
    调用人声分离，因此才产生保留环境音的附加费用。
    """

    if total_seconds < 0:
        raise ValueError("total_seconds must not be negative")
    if credits_per_minute <= 0:
        raise ValueError("credits_per_minute must be positive")
    if voice_replacement_surcharge_credits_per_minute < 0:
        raise ValueError("voice replacement surcharge must not be negative")
    if original_sound_mode not in {"voice_replacement", "translated_voice_only"}:
        raise ValueError("original_sound_mode must be canonical")

    billed_minutes = (total_seconds + 59) // 60
    base_credits = billed_minutes * credits_per_minute
    surcharge_credits = (
        billed_minutes * voice_replacement_surcharge_credits_per_minute
        if original_sound_mode == "voice_replacement"
        else 0
    )
    return base_credits, surcharge_credits, base_credits + surcharge_credits
