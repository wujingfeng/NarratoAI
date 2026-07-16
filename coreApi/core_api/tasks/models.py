from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    JSON,
    DateTime,
    Enum,
    ForeignKey,
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
    lease_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    heartbeat_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
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
