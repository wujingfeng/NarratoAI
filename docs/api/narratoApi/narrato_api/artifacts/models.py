from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from narrato_api.database import Base


def utc_now() -> datetime:
    """返回带时区的 UTC 当前时间。"""

    return datetime.now(timezone.utc)


class RegisteredArtifact(Base):
    """项目完成后明确登记、可供导出的产物。"""

    __tablename__ = "artifacts"
    __table_args__ = (Index("ix_artifacts_project_created", "project_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    cdn_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
