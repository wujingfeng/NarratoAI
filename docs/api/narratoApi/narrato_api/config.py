from __future__ import annotations

import os
import tomllib
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import Field, HttpUrl, field_validator, model_validator
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
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_username: str = Field(default="", repr=False)
    smtp_password: str = Field(default="", repr=False)
    smtp_sender: str = "noreply@example.com"
    smtp_timeout_seconds: float = Field(default=10.0, gt=0, le=60)
    smtp_total_deadline_seconds: float = Field(default=20.0, gt=1, le=120)
    smtp_use_ssl: bool = False
    smtp_use_starttls: bool = True
    verification_code_hmac_secret: str = Field(default="", repr=False)
    verification_code_ttl_seconds: int = Field(default=600, ge=60, le=3600)
    verification_code_send_lease_seconds: int = Field(default=30, ge=5, le=300)
    session_ttl_seconds: int = Field(default=2_592_000, ge=300, le=7_776_000)
    auth_redis_timeout_seconds: float = Field(default=3.0, gt=0, le=30)
    password_argon2_time_cost: int = Field(default=3, ge=1, le=10)
    password_argon2_memory_cost_kib: int = Field(default=65_536, ge=8_192, le=262_144)
    password_argon2_parallelism: int = Field(default=2, ge=1, le=8)
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

    @field_validator("redis_key_prefix")
    @classmethod
    def reject_redis_hash_tag_in_prefix(cls, value: str) -> str:
        """认证适配器独占固定 Cluster hash tag，配置前缀不得注入 tag。"""

        if not value or "{" in value or "}" in value:
            raise ValueError("redis_key_prefix must not contain Redis hash tags")
        return value

    @field_validator("smtp_host", "smtp_sender")
    @classmethod
    def reject_smtp_control_characters(cls, value: str) -> str:
        """拒绝 SMTP 主机和发件人字段中的控制字符。"""

        if any(ord(char) < 32 or ord(char) == 127 for char in value):
            raise ValueError("SMTP configuration contains control characters")
        return value

    @model_validator(mode="after")
    def validate_verification_delivery_timeouts(self) -> Settings:
        """校验验证码发送超时与 SMTP TLS 模式。"""

        if self.smtp_use_ssl and self.smtp_use_starttls:
            raise ValueError("smtp_use_ssl and smtp_use_starttls cannot both be true")

        if (
            self.smtp_timeout_seconds >= self.verification_code_send_lease_seconds
            or self.smtp_timeout_seconds >= self.smtp_total_deadline_seconds
            or self.smtp_total_deadline_seconds + 5
            >= self.verification_code_send_lease_seconds
            or self.auth_redis_timeout_seconds
            >= self.verification_code_send_lease_seconds
            or self.verification_code_send_lease_seconds
            >= self.verification_code_ttl_seconds
        ):
            raise ValueError(
                "verification delivery timeouts must fit inside code lease and TTL"
            )
        return self


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
