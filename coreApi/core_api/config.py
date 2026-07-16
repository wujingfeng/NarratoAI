from __future__ import annotations

import os
import tomllib
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Core API 的独立运行配置。"""

    model_config = SettingsConfigDict(
        env_prefix="CORE_API_",
        case_sensitive=False,
        extra="forbid",
    )

    database_url: str = "postgresql+psycopg://narrato_core@127.0.0.1/narrato_core"
    redis_url: str = "redis://127.0.0.1:6379/2"
    redis_key_prefix: str = "narrato:core:"
    celery_broker_url: str = "redis://127.0.0.1:6379/3"
    celery_queue_prefix: str = "narrato.core"
    service_token: str = Field(default="", repr=False)
    callback_token: str = Field(default="", repr=False)
    provider_secrets: dict[str, str] = Field(default_factory=dict, repr=False)
    oss_endpoint: str = ""
    oss_bucket: str = ""
    oss_access_key_id: str = Field(default="", repr=False)
    oss_access_key_secret: str = Field(default="", repr=False)
    readiness_timeout_seconds: float = Field(default=3.0, gt=0, le=30)
    log_level: str = "INFO"
    work_root: Path = Path("/var/lib/narrato/core")


def load_settings(config_path: str | Path | None = None) -> Settings:
    """从明确指定的 TOML 或环境变量加载配置。"""

    selected = config_path or os.getenv("CORE_API_CONFIG")
    if selected is None:
        return Settings()

    path = Path(selected).expanduser()
    with path.open("rb") as handle:
        values: dict[str, Any] = tomllib.load(handle)
    return Settings(**values)


@lru_cache(maxsize=1)
def get_cached_settings() -> Settings:
    """为进程复用一次校验后的配置。"""

    return load_settings()
