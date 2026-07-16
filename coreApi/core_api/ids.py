from __future__ import annotations

import secrets
import time

_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def new_time_ordered_id(prefix: str) -> str:
    """生成带前缀、时间有序且不可解析业务语义的 ULID 风格 ID。"""

    timestamp_ms = time.time_ns() // 1_000_000
    value = (timestamp_ms << 80) | secrets.randbits(80)
    encoded = ["0"] * 26
    for index in range(25, -1, -1):
        encoded[index] = _CROCKFORD[value & 31]
        value >>= 5
    return f"{prefix}{''.join(encoded)}"
