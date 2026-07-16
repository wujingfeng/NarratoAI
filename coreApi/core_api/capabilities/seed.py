from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from core_api.capabilities.models import CoreModel, CoreProvider, CoreVoice
from core_api.ids import new_time_ordered_id


@dataclass(frozen=True, slots=True)
class ModelSeed:
    """一个供应商模型的非密钥种子配置。"""

    provider_model_code: str
    name: str
    capability_types: tuple[str, ...]
    languages: tuple[str, ...]
    limits: dict[str, Any] = field(default_factory=dict)
    enabled: bool = True


@dataclass(frozen=True, slots=True)
class VoiceSeed:
    """一个供应商音色的统一种子配置。"""

    provider_voice_code: str
    name: str
    languages: tuple[str, ...]
    supported_formats: tuple[str, ...]
    supported_sample_rates: tuple[int, ...]
    gender: str | None = None
    styles: tuple[str, ...] = ()
    sample_url: str | None = None
    enabled: bool = True


@dataclass(frozen=True, slots=True)
class ProviderSeed:
    """供应商及其模型、音色的幂等种子配置。"""

    code: str
    name: str
    secret_ref: str
    settings: dict[str, Any] = field(default_factory=dict)
    limits: dict[str, Any] = field(default_factory=dict)
    enabled: bool = True
    models: tuple[ModelSeed, ...] = ()
    voices: tuple[VoiceSeed, ...] = ()


def _insert_or_read_winner(
    session: Session,
    model: type[CoreProvider] | type[CoreModel] | type[CoreVoice],
    values: dict[str, Any],
    conflict_columns: list[Any],
    winner_query: Any,
) -> tuple[CoreProvider | CoreModel | CoreVoice, bool]:
    """原子插入或忽略唯一键竞争，并在当前事务回读 winner。"""

    dialect_name = session.get_bind().dialect.name
    if dialect_name == "sqlite":
        statement = sqlite_insert(model).values(**values)
    elif dialect_name == "postgresql":
        statement = postgresql_insert(model).values(**values)
    else:
        raise RuntimeError(f"不支持能力 seed 方言: {dialect_name}")
    result = session.execute(
        statement.on_conflict_do_nothing(index_elements=conflict_columns)
    )
    winner = session.scalar(winner_query)
    if winner is None:
        raise RuntimeError("CAPABILITY_SEED_WINNER_NOT_FOUND")
    return winner, result.rowcount > 0


def seed_capabilities(
    session: Session,
    providers: tuple[ProviderSeed, ...],
    *,
    override_enabled: bool = False,
) -> None:
    """在调用方事务内幂等写入目录，且默认保留运维停用状态。"""

    for item in providers:
        provider_query = select(CoreProvider).where(CoreProvider.code == item.code)
        provider, provider_created = _insert_or_read_winner(
            session,
            CoreProvider,
            {
                "id": new_time_ordered_id("provider_"),
                "code": item.code,
                "name": item.name,
                "enabled": item.enabled,
                "secret_ref": item.secret_ref,
                "settings": item.settings,
                "limits": item.limits,
            },
            [CoreProvider.code],
            provider_query,
        )
        provider.name = item.name
        provider.secret_ref = item.secret_ref
        provider.settings = item.settings
        provider.limits = item.limits
        if override_enabled and not provider_created:
            provider.enabled = item.enabled

        for model_item in item.models:
            model_query = select(CoreModel).where(
                CoreModel.provider_id == provider.id,
                CoreModel.provider_model_code == model_item.provider_model_code,
            )
            model, model_created = _insert_or_read_winner(
                session,
                CoreModel,
                {
                    "id": new_time_ordered_id("model_"),
                    "provider_id": provider.id,
                    "provider_model_code": model_item.provider_model_code,
                    "name": model_item.name,
                    "capability_types": list(model_item.capability_types),
                    "languages": list(model_item.languages),
                    "limits": model_item.limits,
                    "enabled": model_item.enabled,
                },
                [CoreModel.provider_id, CoreModel.provider_model_code],
                model_query,
            )
            model.name = model_item.name
            model.capability_types = list(model_item.capability_types)
            model.languages = list(model_item.languages)
            model.limits = model_item.limits
            if override_enabled and not model_created:
                model.enabled = model_item.enabled

        for voice_item in item.voices:
            voice_query = select(CoreVoice).where(
                CoreVoice.provider_id == provider.id,
                CoreVoice.provider_voice_code == voice_item.provider_voice_code,
            )
            voice, voice_created = _insert_or_read_winner(
                session,
                CoreVoice,
                {
                    "id": new_time_ordered_id("voice_"),
                    "provider_id": provider.id,
                    "provider_voice_code": voice_item.provider_voice_code,
                    "name": voice_item.name,
                    "languages": list(voice_item.languages),
                    "gender": voice_item.gender,
                    "styles": list(voice_item.styles),
                    "sample_url": voice_item.sample_url,
                    "supported_formats": list(voice_item.supported_formats),
                    "supported_sample_rates": list(
                        voice_item.supported_sample_rates
                    ),
                    "enabled": voice_item.enabled,
                },
                [CoreVoice.provider_id, CoreVoice.provider_voice_code],
                voice_query,
            )
            voice.name = voice_item.name
            voice.languages = list(voice_item.languages)
            voice.gender = voice_item.gender
            voice.styles = list(voice_item.styles)
            voice.sample_url = voice_item.sample_url
            voice.supported_formats = list(voice_item.supported_formats)
            voice.supported_sample_rates = list(voice_item.supported_sample_rates)
            if override_enabled and not voice_created:
                voice.enabled = voice_item.enabled
