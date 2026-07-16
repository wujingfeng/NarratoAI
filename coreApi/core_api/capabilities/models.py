from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core_api.database import Base


def utc_now() -> datetime:
    """返回带时区的 UTC 当前时间。"""

    return datetime.now(timezone.utc)


class CoreProvider(Base):
    """供应商稳定标识、可用状态和密钥引用。"""

    __tablename__ = "core_providers"
    __table_args__ = (UniqueConstraint("code", name="uq_core_providers_code"),)

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    code: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    secret_ref: Mapped[str] = mapped_column(String(160), nullable=False)
    settings: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    limits: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

    models: Mapped[list[CoreModel]] = relationship(
        back_populates="provider", cascade="all, delete-orphan"
    )
    voices: Mapped[list[CoreVoice]] = relationship(
        back_populates="provider", cascade="all, delete-orphan"
    )


class CoreModel(Base):
    """供应商模型到统一稳定模型 ID 的映射。"""

    __tablename__ = "core_models"
    __table_args__ = (
        UniqueConstraint(
            "provider_id", "provider_model_code", name="uq_core_models_provider_code"
        ),
        Index("ix_core_models_provider_enabled", "provider_id", "enabled"),
    )

    id: Mapped[str] = mapped_column("model_id", String(40), primary_key=True)
    provider_id: Mapped[str] = mapped_column(
        ForeignKey("core_providers.id", ondelete="CASCADE"), nullable=False
    )
    provider_model_code: Mapped[str] = mapped_column(String(160), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    capability_types: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    languages: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    limits: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

    provider: Mapped[CoreProvider] = relationship(back_populates="models")


class CoreVoice(Base):
    """供应商音色到统一稳定音色 ID 的映射。"""

    __tablename__ = "core_voices"
    __table_args__ = (
        UniqueConstraint(
            "provider_id", "provider_voice_code", name="uq_core_voices_provider_code"
        ),
        Index("ix_core_voices_provider_enabled", "provider_id", "enabled"),
    )

    id: Mapped[str] = mapped_column("voice_id", String(40), primary_key=True)
    provider_id: Mapped[str] = mapped_column(
        ForeignKey("core_providers.id", ondelete="CASCADE"), nullable=False
    )
    provider_voice_code: Mapped[str] = mapped_column(String(160), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    languages: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    gender: Mapped[str | None] = mapped_column(String(32))
    styles: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    sample_url: Mapped[str | None] = mapped_column(String(2048))
    supported_formats: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    supported_sample_rates: Mapped[list[int]] = mapped_column(JSON, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

    provider: Mapped[CoreProvider] = relationship(back_populates="voices")
