from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    JSON,
    DateTime,
    Enum,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core_api.database import Base


def utc_now() -> datetime:
    """返回带时区的 UTC 当前时间。"""

    return datetime.now(timezone.utc)


class CoreTaskStatus(StrEnum):
    """Core Task 可持久化状态。"""

    QUEUED = "queued"
    RUNNING = "running"
    RETRY_WAIT = "retry_wait"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class AttemptStatus(StrEnum):
    """Core Task attempt 的执行状态。"""

    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    EXPIRED = "expired"


class CallbackStatus(StrEnum):
    """回调 Outbox 的投递状态。"""

    PENDING = "pending"
    SENT = "sent"


class DispatchStatus(StrEnum):
    """可靠任务唤醒 Outbox 的投递状态。"""

    PENDING = "pending"
    SENT = "sent"


def _string_enum(enum_type: type[StrEnum], name: str) -> Enum:
    return Enum(
        enum_type,
        name=name,
        native_enum=False,
        create_constraint=True,
        values_callable=lambda items: [item.value for item in items],
    )


class CoreTask(Base):
    """Core 原子能力任务的数据库事实记录。"""

    __tablename__ = "core_tasks"
    __table_args__ = (
        UniqueConstraint("idempotency_scope", name="uq_core_tasks_idempotency_scope"),
        Index("ix_core_tasks_status_created_at", "status", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    task_type: Mapped[str] = mapped_column(String(80), nullable=False)
    caller: Mapped[str] = mapped_column(String(120), nullable=False)
    caller_task_id: Mapped[str | None] = mapped_column(String(80))
    idempotency_scope: Mapped[str] = mapped_column(String(512), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    request_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    input_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    initial_response: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    status: Mapped[CoreTaskStatus] = mapped_column(
        _string_enum(CoreTaskStatus, "core_task_status"),
        nullable=False,
        default=CoreTaskStatus.QUEUED,
    )
    phase: Mapped[str | None] = mapped_column(String(80))
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    state_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    current_attempt_no: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    error: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    result: Mapped[list[dict[str, Any]] | dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    attempts: Mapped[list[CoreTaskAttempt]] = relationship(
        back_populates="core_task", cascade="all, delete-orphan"
    )
    artifacts: Mapped[list[CoreArtifact]] = relationship(
        back_populates="core_task", cascade="all, delete-orphan"
    )
    dispatches: Mapped[list[CoreDispatchOutbox]] = relationship(
        back_populates="core_task", cascade="all, delete-orphan"
    )


class CoreTaskAttempt(Base):
    """一次 Core Task Worker 执行及其版本化租约。"""

    __tablename__ = "core_task_attempts"
    __table_args__ = (
        UniqueConstraint(
            "core_task_id", "attempt_no", name="uq_core_task_attempts_task_no"
        ),
        Index("ix_core_task_attempts_lease_expiry", "status", "lease_expires_at"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    core_task_id: Mapped[str] = mapped_column(
        ForeignKey("core_tasks.id", ondelete="CASCADE"), nullable=False
    )
    attempt_no: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[AttemptStatus] = mapped_column(
        _string_enum(AttemptStatus, "core_attempt_status"), nullable=False
    )
    lease_token: Mapped[str] = mapped_column(String(128), nullable=False)
    lease_version: Mapped[int] = mapped_column(Integer, nullable=False)
    lease_expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    heartbeat_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    late_result_audit: Mapped[dict[str, Any] | None] = mapped_column(JSON)

    core_task: Mapped[CoreTask] = relationship(back_populates="attempts")


class CallbackOutbox(Base):
    """等待可靠投递的 Core 状态回调。"""

    __tablename__ = "callback_outbox"
    __table_args__ = (
        UniqueConstraint("event_id", name="uq_callback_outbox_event_id"),
        UniqueConstraint(
            "core_task_id",
            "state_version",
            name="uq_callback_outbox_task_state_version",
        ),
        Index("ix_callback_outbox_pending", "status", "next_attempt_at"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    event_id: Mapped[str] = mapped_column(String(80), nullable=False)
    core_task_id: Mapped[str] = mapped_column(
        ForeignKey("core_tasks.id", ondelete="CASCADE"), nullable=False
    )
    attempt_no: Mapped[int] = mapped_column(Integer, nullable=False)
    state_version: Mapped[int] = mapped_column(Integer, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    status: Mapped[CallbackStatus] = mapped_column(
        _string_enum(CallbackStatus, "callback_outbox_status"),
        nullable=False,
        default=CallbackStatus.PENDING,
    )
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class CoreArtifact(Base):
    """Core 任务上传到 OSS 后的统一产物登记。"""

    __tablename__ = "core_artifacts"
    __table_args__ = (
        UniqueConstraint("object_key", name="uq_core_artifacts_object_key"),
        ForeignKeyConstraint(
            ["core_task_id", "attempt_no"],
            ["core_task_attempts.core_task_id", "core_task_attempts.attempt_no"],
            name="fk_core_artifacts_task_attempt",
            ondelete="CASCADE",
        ),
        CheckConstraint("attempt_no > 0", name="ck_core_artifacts_attempt_positive"),
        CheckConstraint("size > 0", name="ck_core_artifacts_size_positive"),
        Index("ix_core_artifacts_task_attempt", "core_task_id", "attempt_no"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    core_task_id: Mapped[str] = mapped_column(
        ForeignKey("core_tasks.id", ondelete="CASCADE"), nullable=False
    )
    attempt_no: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(String(80), nullable=False)
    bucket: Mapped[str] = mapped_column(String(255), nullable=False)
    object_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    content_type: Mapped[str] = mapped_column(String(255), nullable=False)
    size: Mapped[int] = mapped_column(Integer, nullable=False)
    checksum: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    core_task: Mapped[CoreTask] = relationship(back_populates="artifacts")


class CoreDispatchOutbox(Base):
    """数据库事实源中的可靠 Core Task 唤醒事件。"""

    __tablename__ = "core_dispatch_outbox"
    __table_args__ = (
        UniqueConstraint(
            "core_task_id", "state_version", name="uq_core_dispatch_task_state"
        ),
        Index("ix_core_dispatch_pending", "status", "available_at"),
        Index("ix_core_dispatch_recovery", "status", "recover_after"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    core_task_id: Mapped[str] = mapped_column(
        ForeignKey("core_tasks.id", ondelete="CASCADE"), nullable=False
    )
    state_version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[DispatchStatus] = mapped_column(
        _string_enum(DispatchStatus, "core_dispatch_status"),
        nullable=False,
        default=DispatchStatus.PENDING,
    )
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(String(80))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    recover_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

    core_task: Mapped[CoreTask] = relationship(back_populates="dispatches")
