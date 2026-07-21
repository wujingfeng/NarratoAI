from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class ProviderDTO(BaseModel):
    """不含密钥引用和内部配置的供应商公开结构。"""

    model_config = ConfigDict(frozen=True)

    provider_code: str
    name: str
    capability_types: list[str]


class ModelDTO(BaseModel):
    """供应商无关的模型公开结构。"""

    model_config = ConfigDict(frozen=True)

    model_id: str
    provider_code: str
    name: str
    capability_types: list[str]
    languages: list[str]
    limits: dict[str, Any]


class VoiceDTO(BaseModel):
    """供应商无关的音色公开结构。"""

    model_config = ConfigDict(frozen=True)

    voice_id: str
    provider_code: str
    name: str
    languages: list[str]
    gender: str | None
    styles: list[str]
    sample_url: str | None
    supported_formats: list[str]
    supported_sample_rates: list[int]


class CapabilityCatalogDTO(BaseModel):
    """带确定性版本的当前可调用能力目录。"""

    model_config = ConfigDict(frozen=True)

    version: str
    providers: list[ProviderDTO]
    models: list[ModelDTO]
    voices: list[VoiceDTO]
