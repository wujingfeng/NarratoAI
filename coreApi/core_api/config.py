from __future__ import annotations

import os
import tomllib
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Core API 的独立运行配置。"""

    model_config = SettingsConfigDict(
        env_prefix="CORE_API_",
        case_sensitive=False,
        # 运行配置可由新版能力模块扩展；旧版 Core 在未加载对应适配器时
        # 忽略这些字段，避免整个 API/Worker 因无关配置无法启动。
        extra="ignore",
    )

    database_url: str = "postgresql+psycopg://narrato_core@127.0.0.1/narrato_core"
    redis_url: str = "redis://127.0.0.1:6379/2"
    redis_key_prefix: str = "narrato:core:"
    celery_broker_url: str = "redis://127.0.0.1:6379/3"
    celery_queue_prefix: str = "narrato.core"
    service_token: str = Field(default="", repr=False)
    callback_token: str = Field(default="", repr=False)
    callback_url: str = ""
    callback_connect_timeout_seconds: float = Field(default=3.0, gt=0, le=30)
    callback_read_timeout_seconds: float = Field(default=10.0, gt=0, le=60)
    callback_total_timeout_seconds: float = Field(default=15.0, gt=0, le=120)
    provider_secrets: dict[str, str] = Field(default_factory=dict, repr=False)
    # 火山方舟 Chat Completions 凭据仅驻留在私有 TOML，不进入能力目录或任务快照。
    volcengine_ark_base_url: str = ""
    volcengine_ark_api_key: str = Field(default="", repr=False)
    # 方舟侧接收的 Endpoint ID / Model ID；禁止在代码或数据库中写死。
    volcengine_ark_model_id: str = ""
    oss_endpoint: str = ""
    oss_bucket: str = ""
    oss_access_key_id: str = Field(default="", repr=False)
    oss_access_key_secret: str = Field(default="", repr=False)
    oss_public_base_url: str = ""
    cdn_allowed_hosts: list[str] = Field(default_factory=list)
    # ASR 供应商必须显式选择；不允许在远程配置缺失时静默回退本地服务。
    asr_provider: Literal["local", "volcengine"] = "local"
    asr_local_api_url: str = "http://127.0.0.1:7860"
    volcengine_asr_appid: str = Field(default="", repr=False)
    volcengine_asr_token: str = Field(default="", repr=False)
    volcengine_asr_cluster: str = "volc_auc_video"
    volcengine_asr_poll_interval_seconds: float = Field(default=2.0, gt=0, le=60)
    volcengine_asr_total_timeout_seconds: float = Field(default=600.0, gt=0, le=3600)
    volcengine_asr_language: str = "zh-CN"
    volcengine_asr_use_itn: bool = True
    volcengine_asr_use_punc: bool = True
    volcengine_asr_with_speaker_info: bool = False
    # 火山从公网访问 Core 的基础地址；实际回调路径由 Core 按每条来源生成。
    volcengine_asr_callback_base_url: str = ""
    download_connect_timeout_seconds: float = Field(default=5.0, gt=0, le=30)
    download_read_timeout_seconds: float = Field(default=30.0, gt=0, le=300)
    download_total_timeout_seconds: float = Field(default=120.0, gt=0, le=1800)
    readiness_timeout_seconds: float = Field(default=3.0, gt=0, le=30)
    log_level: str = "INFO"
    work_root: Path = Path("/var/lib/narrato/core")

    @property
    def resolved_provider_secrets(self) -> dict[str, str]:
        """返回运行时可解析的密钥引用，不把私有配置写入数据库。"""

        secrets = dict(self.provider_secrets)
        # 方舟模型只有三项私有配置都完整时才会出现在能力目录中，避免用户选到
        # 一个 Worker 必然无法调用的模型。
        if (
            self.volcengine_ark_base_url.strip()
            and self.volcengine_ark_api_key.strip()
            and self.volcengine_ark_model_id.strip()
        ):
            secrets["volcengine_ark"] = self.volcengine_ark_api_key
        return secrets


def load_settings(config_path: str | Path | None = None) -> Settings:
    """从明确指定的 TOML 或环境变量加载配置。"""

    selected = config_path or os.getenv("CORE_API_CONFIG")
    if selected is None:
        return Settings()

    path = Path(selected).expanduser()
    with path.open("rb") as handle:
        values: dict[str, Any] = tomllib.load(handle)
    # 兼容新版配置名称，旧版 ArtifactStore 仍读取 oss_public_base_url。
    if "oss_public_base_url" not in values and "cdn_public_base_url" in values:
        values["oss_public_base_url"] = values["cdn_public_base_url"]
    return Settings(**values)


@lru_cache(maxsize=1)
def get_cached_settings() -> Settings:
    """为进程复用一次校验后的配置。"""

    return load_settings()
