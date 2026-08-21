from __future__ import annotations

import os
import tomllib
from ipaddress import ip_address
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

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
    allow_insecure_core_loopback: bool = False
    core_request_token: str = Field(default="", repr=False)
    core_callback_token: str = Field(default="", repr=False)
    video_translation_model_id: str = Field(
        default="model_qwen_plus", min_length=1, max_length=40
    )
    workflow_poll_interval_seconds: float = Field(default=15.0, ge=1, le=300)
    workflow_outbox_replay_interval_seconds: float = Field(default=5.0, ge=1, le=300)
    workflow_outbox_lease_seconds: float = Field(default=60.0, ge=5, le=3600)
    project_deletion_sweep_interval_seconds: float = Field(default=10.0, ge=1, le=300)
    # AI 视频供应商状态由 Celery beat/worker 主动收敛；Web refresh 仅作手动兜底。
    ai_video_poll_interval_seconds: float = Field(default=15.0, ge=1, le=300)
    ai_video_poll_batch_size: int = Field(default=100, ge=1, le=1000)
    # Provider adapter caps one HTTP call at 30s; keep the DB lease above it.
    ai_video_poll_lease_seconds: float = Field(default=60.0, ge=35, le=3600)
    ai_video_poll_max_backoff_seconds: float = Field(default=300.0, ge=1, le=3600)
    ai_video_poll_max_errors: int = Field(default=12, ge=1, le=100)
    ai_video_submission_recovery_delay_seconds: float = Field(
        default=60.0, ge=5, le=3600
    )
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
    admin_session_ttl_seconds: int = Field(default=28_800, ge=300, le=86_400)
    admin_session_hmac_secret: str = Field(default="", repr=False)
    admin_bootstrap_username: str = "Admin"
    admin_bootstrap_password: str = Field(default="", repr=False)
    admin_bootstrap_display_name: str = "Admin"
    admin_cors_origins: str = ""
    auth_redis_timeout_seconds: float = Field(default=3.0, gt=0, le=30)
    password_argon2_time_cost: int = Field(default=3, ge=1, le=10)
    password_argon2_memory_cost_kib: int = Field(default=65_536, ge=8_192, le=262_144)
    password_argon2_parallelism: int = Field(default=2, ge=1, le=8)
    oss_endpoint: str = ""
    # Browser uploads still go directly to OSS; persisted asset URLs must use CDN.
    oss_url: str = ""
    cdn_public_base_url: str = ""
    oss_bucket: str = ""
    oss_access_key_id: str = Field(default="", repr=False)
    oss_access_key_secret: str = Field(default="", repr=False)
    log_level: str = "INFO"

    @field_validator("core_base_url")
    @classmethod
    def require_supported_core_url(cls, value: HttpUrl) -> HttpUrl:
        """Core 服务地址仅接受无用户凭据的 HTTP(S) URL。"""

        if value.scheme not in {"http", "https"} or value.username or value.password:
            raise ValueError("core_base_url must be a credential-free HTTP(S) URL")
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

    @field_validator("oss_endpoint")
    @classmethod
    def require_oss_endpoint_host(cls, value: str) -> str:
        """OSS Endpoint 仅保存不含协议的域名，由客户端按 Bucket 组成地址。"""

        if not value:
            return value
        if any(token in value for token in ("://", "/", "?", "#", "@")):
            raise ValueError("OSS endpoint must be a hostname without a scheme")
        return value.rstrip(".")

    @field_validator("oss_url")
    @classmethod
    def require_absolute_https_oss_upload_url(cls, value: str) -> str:
        """H5 直传地址必须是完整的无凭据 HTTPS URL。"""

        if not value:
            return value
        parsed = urlsplit(value)
        if (
            parsed.scheme != "https"
            or not parsed.netloc
            or parsed.username
            or parsed.password
        ):
            raise ValueError("OSS URL must be a credential-free HTTPS URL")
        return value.rstrip("/")

    @field_validator("cdn_public_base_url")
    @classmethod
    def require_absolute_https_cdn_url(cls, value: str) -> str:
        """CDN 公网基地址必须是无凭据 HTTPS URL。"""

        if not value:
            return value
        parsed = urlsplit(value)
        if (
            parsed.scheme != "https"
            or not parsed.netloc
            or parsed.username
            or parsed.password
        ):
            raise ValueError("CDN public base URL must be a credential-free HTTPS URL")
        return value.rstrip("/")

    @model_validator(mode="after")
    def validate_verification_delivery_timeouts(self) -> Settings:
        """校验 Core 传输边界、验证码发送超时与 SMTP TLS 模式。"""

        if self.core_base_url.scheme == "http":
            host = self.core_base_url.host
            try:
                is_loopback = host == "localhost" or ip_address(host).is_loopback
            except ValueError:
                is_loopback = False
            if not self.allow_insecure_core_loopback or not is_loopback:
                raise ValueError(
                    "HTTP core_base_url requires allow_insecure_core_loopback on a loopback host"
                )

        if self.oss_url and not self.cdn_public_base_url:
            raise ValueError(
                "cdn_public_base_url is required when oss_url is configured"
            )

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
