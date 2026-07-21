from __future__ import annotations

import json
import logging
import re
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from core_api.config import Settings

_BEARER_PATTERN = re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/-]+")
_URI_USERINFO_PATTERN = re.compile(r"(?i)([a-z][a-z0-9+.-]*://)[^/@\s]+@")
_NAMED_VALUE_PATTERN = re.compile(
    r"(?i)(?P<prefix>[\"']?(?P<name>[a-z][a-z0-9_.-]{0,63})"
    r"[\"']?\s*[=:]\s*)"
    r"(?P<value>\"[^\"]*\"|'[^']*'|[^\s,;}\]]+)"
)
_STANDARD_RECORD_FIELDS = frozenset(logging.makeLogRecord({}).__dict__) | {
    "message",
    "asctime",
}
_SENSITIVE_TERMS = {
    "authorization",
    "credential",
    "credentials",
    "passwd",
    "password",
    "pwd",
    "secret",
    "token",
}
_KEY_NAMESPACES = {"access", "api", "client", "encryption", "private", "signing"}


def _normalize_field_name(name: str) -> tuple[tuple[str, ...], str]:
    """把大小写、连字符和 camelCase 键名统一为可判断的词元。"""

    snake = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", name)
    parts = tuple(
        part for part in re.sub(r"[^a-z0-9]+", "_", snake.lower()).split("_") if part
    )
    return parts, "".join(parts)


def _is_sensitive_field(name: str) -> bool:
    """保守识别凭据键，同时不把普通资源 ID 当作密钥。"""

    parts, compact = _normalize_field_name(name)
    if any(part in _SENSITIVE_TERMS for part in parts):
        return True
    if compact.endswith(
        ("password", "passwd", "credential", "credentials", "token", "secret")
    ):
        return True
    part_set = set(parts)
    if "key" in part_set and part_set.intersection(_KEY_NAMESPACES):
        return True
    return any(
        compact.startswith(namespace) and "key" in compact
        for namespace in _KEY_NAMESPACES
    )


class JsonFormatter(logging.Formatter):
    """输出可关联请求与 Core attempt 的脱敏 JSON 日志。"""

    def __init__(self, *, secrets: tuple[str, ...] = ()) -> None:
        super().__init__()
        self.secrets = tuple(value for value in secrets if value)

    def _redact(self, value: str) -> str:
        """屏蔽已配置密钥和 Bearer Token。"""

        result = _URI_USERINFO_PATTERN.sub(r"\1***@", value)
        result = _BEARER_PATTERN.sub(r"\1***", result)

        def redact_named_value(match: re.Match[str]) -> str:
            # 使用与 structured extra 相同的键名判定，避免两套别名漂移。
            if _is_sensitive_field(match.group("name")):
                return f"{match.group('prefix')}***"
            return match.group(0)

        result = _NAMED_VALUE_PATTERN.sub(redact_named_value, result)
        for secret in self.secrets:
            result = result.replace(secret, "***")
        return result

    def _safe_value(self, name: str, value: Any) -> Any:
        """递归清理日志 extra 中的凭据和连接 URI。"""

        if _is_sensitive_field(name):
            return "***"
        if isinstance(value, str):
            return self._redact(value)
        if isinstance(value, Mapping):
            return {
                str(key): self._safe_value(str(key), item)
                for key, item in value.items()
            }
        if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
            return [self._safe_value(name, item) for item in value]
        if value is None or isinstance(value, (bool, int, float)):
            return value
        return self._redact(str(value))

    def format(self, record: logging.LogRecord) -> str:
        """将日志记录序列化为脱敏 JSON。"""

        payload = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": self._redact(record.getMessage()),
        }
        for field in ("request_id", "core_task_id", "attempt_no"):
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = self._safe_value(field, value)
        for field, value in record.__dict__.items():
            if field not in _STANDARD_RECORD_FIELDS and field not in payload:
                payload[field] = self._safe_value(field, value)
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(settings: Settings) -> None:
    """为 Core 进程安装统一 JSON 日志处理器。"""

    handler = logging.StreamHandler()
    handler.setFormatter(
        JsonFormatter(
            secrets=(
                settings.service_token,
                settings.callback_token,
                settings.oss_access_key_id,
                settings.oss_access_key_secret,
                *settings.provider_secrets.values(),
            )
        )
    )
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(settings.log_level.upper())
