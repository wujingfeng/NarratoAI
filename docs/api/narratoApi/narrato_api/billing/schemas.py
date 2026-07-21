from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PriceQuote:
    """服务端返回和任务创建共同使用的价格快照。"""

    product: str
    price_version: int
    credits_per_minute: int
    total_seconds: int
    credits: int
