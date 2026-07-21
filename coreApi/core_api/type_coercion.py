from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, cast


def as_float(value: object) -> float:
    """在已完成业务校验的 JSON 边界收窄为浮点数。"""

    return float(cast(Any, value))


def as_int(value: object) -> int:
    """在已完成业务校验的 JSON 边界收窄为整数。"""

    return int(cast(Any, value))


def as_mapping(value: object) -> Mapping[str, Any]:
    """在已验证字典边界提供稳定只读 Mapping 类型。"""

    if not isinstance(value, dict):
        raise TypeError("EXPECTED_MAPPING")
    return cast(Mapping[str, Any], value)


def as_sequence(value: object) -> Sequence[Any]:
    """在已验证数组边界提供稳定只读 Sequence 类型。"""

    if not isinstance(value, (list, tuple)):
        raise TypeError("EXPECTED_SEQUENCE")
    return cast(Sequence[Any], value)
