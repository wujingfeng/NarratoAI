from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from narrato_api.database import Base


def utc_now() -> datetime:
    """返回带时区的 UTC 当前时间。"""

    return datetime.now(timezone.utc)


class Asset(Base):
    """项目拥有的 OSS 对象、校验状态与公开 CDN 地址。"""

    __tablename__ = "assets"
    __table_args__ = (
        CheckConstraint("asset_type IN ('video', 'subtitle')", name="ck_assets_type"),
        CheckConstraint(
            "status IN ('validating', 'ready', 'invalid')", name="ck_assets_status"
        ),
        CheckConstraint(
            "length(filename) BETWEEN 1 AND 255", name="ck_assets_filename_length"
        ),
        CheckConstraint("size_bytes >= 0", name="ck_assets_size_bytes"),
        UniqueConstraint("bucket", "object_key", name="uq_assets_bucket_object_key"),
        Index("ix_assets_project_type", "project_id", "asset_type"),
        Index("ix_assets_user_created", "user_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False
    )
    asset_type: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="validating")
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    bucket: Mapped[str] = mapped_column(String(255), nullable=False)
    object_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    cdn_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )
