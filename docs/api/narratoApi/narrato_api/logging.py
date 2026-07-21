from __future__ import annotations

import json
import logging
import threading
from contextvars import ContextVar, Token
from datetime import UTC, datetime
from urllib.parse import unquote, urlsplit

from narrato_api.config import Settings

_request_id_context: ContextVar[str | None] = ContextVar(
    "narrato_request_id", default=None
)


class RedactionRegistry:
    """按运行中应用引用计数管理进程内密钥。"""

    def __init__(self, secrets: tuple[str, ...] = ()) -> None:
        """创建初始密钥集合且不暴露其 repr。"""

        self._lock = threading.Lock()
        self._counts: dict[str, int] = {}
        self.acquire(secrets)

    def acquire(self, secrets: tuple[str, ...]) -> None:
        """为一个活动 lifespan 增加去重密钥引用。"""

        with self._lock:
            for secret in set(secrets):
                if secret:
                    self._counts[secret] = self._counts.get(secret, 0) + 1

    def release(self, secrets: tuple[str, ...]) -> None:
        """释放一个 lifespan，仅在最后 owner 退出时删除密钥。"""

        with self._lock:
            for secret in set(secrets):
                count = self._counts.get(secret, 0)
                if count <= 1:
                    self._counts.pop(secret, None)
                else:
                    self._counts[secret] = count - 1

    def redact(self, value: object) -> str:
        """使用当前快照脱敏任意待输出字段。"""

        rendered = str(value)
        with self._lock:
            secrets = tuple(sorted(self._counts, key=len, reverse=True))
        for secret in secrets:
            rendered = rendered.replace(secret, "[REDACTED]")
        return rendered

    def contains_secret(self, value: str) -> bool:
        """判断不可信字段是否包含任一已配置密钥。"""

        with self._lock:
            return any(secret in value for secret in self._counts)

    def value_count(self) -> int:
        """返回当前至少有一个活动 owner 的去重密钥数量。"""

        with self._lock:
            return len(self._counts)


_PROCESS_REDACTIONS = RedactionRegistry()
_LOGGING_LOCK = threading.Lock()
_ACTIVE_LOG_LEVELS: dict[int, int] = {}
_DEFAULT_LOG_LEVEL = logging.WARNING
_LOGGING_CONFIGURED = False

LoggingLease = tuple[tuple[str, ...], int]


def bind_request_id(request_id: str) -> Token[str | None]:
    """将已校验请求 ID 绑定到当前异步上下文。"""

    return _request_id_context.set(request_id)


def reset_request_id(token: Token[str | None]) -> None:
    """在请求结束后恢复此前日志上下文。"""

    _request_id_context.reset(token)


def current_request_id() -> str | None:
    """返回当前请求日志上下文中的关联 ID。"""

    return _request_id_context.get()


class RequestContextFilter(logging.Filter):
    """为所有经过业务根 Handler 的日志自动注入请求 ID。"""

    def filter(self, record: logging.LogRecord) -> bool:
        """覆盖不可信调用方值并只使用当前 ContextVar。"""

        contextual = current_request_id()
        if contextual is not None or not hasattr(record, "request_id"):
            record.request_id = contextual
        return True


def _redaction_values(settings: Settings) -> tuple[str, ...]:
    """收集全部 secret 字段及连接 URL 的 userinfo。"""

    values: set[str] = set()
    for name, field in type(settings).model_fields.items():
        if field.repr is not False:
            continue
        setting_value = getattr(settings, name)
        if hasattr(setting_value, "get_secret_value"):
            setting_value = setting_value.get_secret_value()
        raw = str(setting_value)
        if raw:
            values.add(raw)
        if name not in {"database_url", "redis_url", "celery_broker_url"}:
            continue
        try:
            parsed = urlsplit(raw)
            if parsed.username:
                values.add(parsed.username)
                values.add(unquote(parsed.username))
            if parsed.password:
                values.add(parsed.password)
                values.add(unquote(parsed.password))
        except ValueError:
            # 非法 URL 会在连接或后续配置校验处失败，日志仍会整串脱敏。
            pass
    return tuple(sorted(values, key=len, reverse=True))


class JsonFormatter(logging.Formatter):
    """输出不包含请求正文和凭据的稳定 JSON 日志。"""

    def __init__(self, secrets: tuple[str, ...] = ()) -> None:
        """保存需要从所有消息中自动移除的非空密钥。"""

        super().__init__()
        self._redactions = RedactionRegistry(secrets)

    @classmethod
    def for_process(cls) -> JsonFormatter:
        """创建读取进程级单调密钥集合的 Formatter。"""

        formatter = cls()
        formatter._redactions = _PROCESS_REDACTIONS
        return formatter

    def _redact(self, value: object) -> str:
        """对格式化消息和允许输出的 metadata 使用同一脱敏器。"""

        return self._redactions.redact(value)

    def format(self, record: logging.LogRecord) -> str:
        """将允许字段编码为单行 JSON。"""

        message = self._redact(record.getMessage())
        payload: dict[str, object | None] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "service": "narratoApi",
            "request_id": getattr(record, "request_id", current_request_id()),
            "message": message,
        }
        for field in (
            "user_id",
            "project_id",
            "job_id",
            "node_id",
            "core_task_id",
            "attempt_no",
            "error_type",
            "error_code",
        ):
            if hasattr(record, field):
                payload[field] = self._redact(getattr(record, field))
        if record.exc_info and record.exc_info[0] is not None:
            payload["exception_type"] = record.exc_info[0].__name__
        safe_payload = {
            key: None if value is None else self._redact(value)
            for key, value in payload.items()
        }
        return json.dumps(safe_payload, ensure_ascii=False, separators=(",", ":"))


def contains_configured_secret(value: str) -> bool:
    """供请求边界拒绝将任一配置密钥复用为关联 ID。"""

    return _PROCESS_REDACTIONS.contains_secret(value)


def active_redaction_value_count() -> int:
    """返回当前活动应用持有的去重脱敏值数量。"""

    return _PROCESS_REDACTIONS.value_count()


def acquire_logging_redactions(settings: Settings) -> tuple[str, ...]:
    """在 lifespan 启动时持有当前应用的全部脱敏值。"""

    values = _redaction_values(settings)
    _PROCESS_REDACTIONS.acquire(values)
    return values


def release_logging_redactions(values: tuple[str, ...]) -> None:
    """在 lifespan 退出时释放当前应用的脱敏值。"""

    _PROCESS_REDACTIONS.release(values)


def _configured_level(settings: Settings) -> int:
    """解析已经过配置校验的标准日志级别。"""

    level = logging.getLevelNamesMapping().get(settings.log_level.upper())
    if not isinstance(level, int):
        raise ValueError("invalid log level")
    return level


def _apply_active_level(namespace: logging.Logger) -> None:
    """应用所有活动 lifespan 中最详细的级别。"""

    namespace.setLevel(min(_ACTIVE_LOG_LEVELS, default=_DEFAULT_LOG_LEVEL))


def acquire_logging(settings: Settings) -> LoggingLease:
    """持有活动应用的脱敏值和日志级别。"""

    values = _redaction_values(settings)
    level = _configured_level(settings)
    with _LOGGING_LOCK:
        _PROCESS_REDACTIONS.acquire(values)
        _ACTIVE_LOG_LEVELS[level] = _ACTIVE_LOG_LEVELS.get(level, 0) + 1
        _apply_active_level(logging.getLogger("narrato_api"))
    return values, level


def release_logging(lease: LoggingLease) -> None:
    """释放活动应用日志所有权并重算有效级别。"""

    values, level = lease
    with _LOGGING_LOCK:
        _PROCESS_REDACTIONS.release(values)
        owners = _ACTIVE_LOG_LEVELS.get(level, 0)
        if owners <= 1:
            _ACTIVE_LOG_LEVELS.pop(level, None)
        else:
            _ACTIVE_LOG_LEVELS[level] = owners - 1
        _apply_active_level(logging.getLogger("narrato_api"))


def configure_logging(settings: Settings | None = None) -> None:
    """初始化业务服务 JSON 日志并避免序列化配置密钥。"""

    global _LOGGING_CONFIGURED
    del settings
    with _LOGGING_LOCK:
        namespace = logging.getLogger("narrato_api")
        handlers = [
            handler
            for handler in namespace.handlers
            if getattr(handler, "_narrato_managed", False)
        ]
        if handlers:
            handler = handlers[0]
        else:
            handler = logging.StreamHandler()
            setattr(handler, "_narrato_managed", True)
            handler.addFilter(RequestContextFilter())
            handler.setFormatter(JsonFormatter.for_process())
        namespace.handlers = [handler]
        namespace.propagate = False
        if not _LOGGING_CONFIGURED:
            namespace.setLevel(_DEFAULT_LOG_LEVEL)
            _LOGGING_CONFIGURED = True
