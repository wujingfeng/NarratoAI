from __future__ import annotations

import os
import tomllib
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import Field, HttpUrl, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """narratoApi 独立业务服务配置。"""

    model_config = SettingsConfigDict(
        env_prefix="NARRATO_API_",
        case_sensitive=False,
        extra="forbid",
    )

    database_url: str = Field(
        default="postgresql+psycopg://narrato_business@127.0.0.1/narrato_business",
        repr=False,
    )
    database_connect_timeout_seconds: float = Field(default=3.0, ge=1, le=30)
    database_read_timeout_seconds: float = Field(default=3.0, gt=0, le=30)
    redis_url: str = Field(default="redis://127.0.0.1:6379/4", repr=False)
    redis_key_prefix: str = "narrato:business:"
    celery_broker_url: str = Field(default="redis://127.0.0.1:6379/5", repr=False)
    celery_queue_prefix: str = "narrato.business"
    core_base_url: HttpUrl = HttpUrl("https://core.example.com")
    core_request_token: str = Field(default="", repr=False)
    core_callback_token: str = Field(default="", repr=False)
    readiness_timeout_seconds: float = Field(default=3.0, ge=1, le=30)
    smtp_host: str = ""
    smtp_username: str = Field(default="", repr=False)
    smtp_password: str = Field(default="", repr=False)
    oss_endpoint: str = ""
    oss_bucket: str = ""
    oss_access_key_id: str = Field(default="", repr=False)
    oss_access_key_secret: str = Field(default="", repr=False)
    log_level: str = "INFO"

    @field_validator("core_base_url")
    @classmethod
    def require_https_core_url(cls, value: HttpUrl) -> HttpUrl:
        """Core 服务地址必须使用无用户凭据的 HTTPS URL。"""

        if value.scheme != "https" or value.username or value.password:
            raise ValueError("core_base_url must be a credential-free HTTPS URL")
        return value


def load_settings(config_path: str | Path | None = None) -> Settings:
    """从明确 TOML 路径或带前缀的环境变量加载配置。"""

    selected = config_path or os.getenv("NARRATO_API_CONFIG")
    if selected is None:
        return Settings()
    path = Path(selected).expanduser()
    with path.open("rb") as handle:
        values: dict[str, Any] = tomllib.load(handle)
    return Settings(**values)


@lru_cache(maxsize=1)
def get_cached_settings() -> Settings:
    """返回进程内一次校验后的业务配置。"""

    return load_settings()
