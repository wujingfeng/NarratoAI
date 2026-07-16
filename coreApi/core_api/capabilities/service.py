from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from core_api.api.errors import CapabilityUnavailableError
from core_api.adapters.narrato.short_drama import short_drama_provider_supported
from core_api.capabilities.models import CoreModel, CoreProvider, CoreVoice
from core_api.capabilities.schemas import (
    CapabilityCatalogDTO,
    ModelDTO,
    ProviderDTO,
    VoiceDTO,
)


class CapabilityService:
    """查询统一目录并严格校验稳定能力 ID。"""

    def __init__(self, session: Session, provider_secrets: Mapping[str, str]) -> None:
        """绑定数据库会话和仅驻留配置内存的密钥注册表。"""

        self.session = session
        self.provider_secrets = provider_secrets

    def _provider_is_callable(self, provider: CoreProvider | None) -> bool:
        """确认供应商已启用且密钥引用能解析到非空值。"""

        if provider is None:
            return False
        # 密钥缺失时隐藏整个供应商，不能把不可执行配置伪装成可用。
        secret = self.provider_secrets.get(provider.secret_ref)
        return provider.enabled and isinstance(secret, str) and bool(secret.strip())

    def catalog(self) -> CapabilityCatalogDTO:
        """返回排序稳定且不包含供应商私有字段的能力目录。"""

        providers = list(
            self.session.scalars(select(CoreProvider).order_by(CoreProvider.code)).all()
        )
        callable_providers = [
            item for item in providers if self._provider_is_callable(item)
        ]
        callable_ids = {item.id for item in callable_providers}
        models = (
            list(
                self.session.scalars(
                    select(CoreModel)
                    .options(joinedload(CoreModel.provider))
                    .where(
                        CoreModel.enabled.is_(True),
                        CoreModel.provider_id.in_(callable_ids),
                    )
                    .order_by(CoreModel.provider_id, CoreModel.id)
                ).all()
            )
            if callable_ids
            else []
        )
        voices = (
            list(
                self.session.scalars(
                    select(CoreVoice)
                    .options(joinedload(CoreVoice.provider))
                    .where(
                        CoreVoice.enabled.is_(True),
                        CoreVoice.provider_id.in_(callable_ids),
                    )
                    .order_by(CoreVoice.provider_id, CoreVoice.id)
                ).all()
            )
            if callable_ids
            else []
        )

        # 统一 DTO 是公开边界，原始模型/音色 code 与密钥引用不得越过此处。
        models = [
            item
            for item in models
            if not (
                {"video_analysis", "script_generation"} & set(item.capability_types)
            )
            or short_drama_provider_supported(item.provider.code)
        ]
        model_items = [
            ModelDTO(
                model_id=item.id,
                provider_code=item.provider.code,
                name=item.name,
                capability_types=sorted(item.capability_types),
                languages=sorted(item.languages),
                limits=item.limits,
            )
            for item in models
        ]
        voice_items = [
            VoiceDTO(
                voice_id=item.id,
                provider_code=item.provider.code,
                name=item.name,
                languages=sorted(item.languages),
                gender=item.gender,
                styles=sorted(item.styles),
                sample_url=item.sample_url,
                supported_formats=sorted(item.supported_formats),
                supported_sample_rates=sorted(item.supported_sample_rates),
            )
            for item in voices
        ]
        capability_types_by_provider: dict[str, set[str]] = {
            provider.code: set() for provider in callable_providers
        }
        for item in model_items:
            capability_types_by_provider[item.provider_code].update(
                item.capability_types
            )
        for item in voice_items:
            capability_types_by_provider[item.provider_code].add("tts")
        provider_items = [
            ProviderDTO(
                provider_code=provider.code,
                name=provider.name,
                capability_types=sorted(capability_types_by_provider[provider.code]),
            )
            for provider in callable_providers
        ]

        visible = {
            "providers": [item.model_dump(mode="json") for item in provider_items],
            "models": [item.model_dump(mode="json") for item in model_items],
            "voices": [item.model_dump(mode="json") for item in voice_items],
        }
        canonical = json.dumps(
            visible, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        version = f"catalog_{hashlib.sha256(canonical).hexdigest()}"
        return CapabilityCatalogDTO(version=version, **visible)

    def require_model(
        self,
        model_id: str,
        capability_type: str | None = None,
        *,
        language: str | None = None,
    ) -> CoreModel:
        """按稳定 ID 返回可调用模型，任何不匹配均使用统一错误。"""

        model = self.session.scalar(
            select(CoreModel)
            .options(joinedload(CoreModel.provider))
            .where(CoreModel.id == model_id)
        )
        if (
            model is None
            or not model.enabled
            or not self._provider_is_callable(model.provider)
            or (
                capability_type in {"video_analysis", "script_generation"}
                and not short_drama_provider_supported(model.provider.code)
            )
            or (
                capability_type is not None
                and capability_type not in model.capability_types
            )
            or (language is not None and language not in model.languages)
        ):
            # 未知、停用、供应商不可用和约束不符都禁止回退默认模型。
            raise CapabilityUnavailableError()
        return model

    def require_voice(
        self,
        voice_id: str,
        *,
        language: str | None = None,
        output_format: str | None = None,
        sample_rate: int | None = None,
    ) -> CoreVoice:
        """按稳定 ID 和统一约束返回可调用音色。"""

        voice = self.session.scalar(
            select(CoreVoice)
            .options(joinedload(CoreVoice.provider))
            .where(CoreVoice.id == voice_id)
        )
        if (
            voice is None
            or not voice.enabled
            or not self._provider_is_callable(voice.provider)
            or (language is not None and language not in voice.languages)
            or (
                output_format is not None
                and output_format not in voice.supported_formats
            )
            or (
                sample_rate is not None
                and sample_rate not in voice.supported_sample_rates
            )
        ):
            # 所有约束失败使用同一码，避免调用方猜测或静默切换供应商。
            raise CapabilityUnavailableError()
        return voice
