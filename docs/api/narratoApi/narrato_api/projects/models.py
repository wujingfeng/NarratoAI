from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    JSON,
)
from sqlalchemy.orm import Mapped, mapped_column

from narrato_api.database import Base


def utc_now() -> datetime:
    """返回带时区的 UTC 当前时间。"""

    return datetime.now(timezone.utc)


class Project(Base):
    """用户拥有的短剧解说项目及其持久化状态。"""

    __tablename__ = "projects"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'uploading', 'validating', 'ready', 'queued', "
            "'analyzing', 'waiting_for_edit', 'render_queued', 'rendering', "
            "'completed', 'failed', 'cancelled', 'deleting', 'deleted')",
            name="ck_projects_status",
        ),
        CheckConstraint(
            "current_stage IN ('created', 'settings', 'analysis', 'edit', 'generate', 'export')",
            name="ck_projects_current_stage",
        ),
        Index("ix_projects_user_created", "user_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    product: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    is_locked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # 生命周期阶段是用户可见的不可逆状态机；status 保留给执行器运行态。
    current_stage: Mapped[str] = mapped_column(String(16), nullable=False, default="created")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class ProjectNarrationSettings(Base):
    """当前可编辑的短剧解说参数；进入分析时复制为不可变阶段快照。"""

    __tablename__ = "project_narration_settings"

    project_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("projects.id", ondelete="RESTRICT"), primary_key=True
    )
    settings: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class ProjectStageHistory(Base):
    """阶段迁移审计及进入阶段时冻结的参数快照。"""

    __tablename__ = "project_stage_history"
    __table_args__ = (
        UniqueConstraint("project_id", "to_stage", name="uq_project_stage_history_stage"),
        Index("ix_project_stage_history_project_created", "project_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False
    )
    from_stage: Mapped[str | None] = mapped_column(String(16), nullable=True)
    to_stage: Mapped[str] = mapped_column(String(16), nullable=False)
    settings_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class ProjectBackgroundMusic(Base):
    """短剧解说项目选择的背景音乐及其混音音量。"""

    __tablename__ = "project_background_music"
    __table_args__ = (
        CheckConstraint("volume BETWEEN 0 AND 100", name="ck_project_bgm_volume"),
    )

    project_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("projects.id", ondelete="RESTRICT"), primary_key=True
    )
    asset_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("assets.id", ondelete="RESTRICT"), nullable=False
    )
    volume: Mapped[int] = mapped_column(nullable=False, default=50)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class DeletionJob(Base):
    """符合删除资格的项目所对应的可恢复审计记录。"""

    __tablename__ = "deletion_jobs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'retryable_failed', 'completed')",
            name="ck_deletion_jobs_status",
        ),
        UniqueConstraint("project_id", name="uq_deletion_jobs_project_id"),
        Index("ix_deletion_jobs_user_created", "user_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False
    )
    user_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    attempt_count: Mapped[int] = mapped_column(nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


# ProjectBackgroundMusic 通过字符串外键指向 assets；导入该模型保证仅导入项目
# 模型的维护脚本/单元测试也能在同一 metadata 中建出目标表。
from narrato_api.assets.models import Asset as _Asset  # noqa: E402, F401
