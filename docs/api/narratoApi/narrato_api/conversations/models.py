from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from narrato_api.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


CONVERSATION_MODES = (
    "chat",
    "short_drama_narration",
    "video_translation",
    "video_generation",
)


class ConversationThread(Base):
    __tablename__ = "conversation_threads"
    __table_args__ = (
        CheckConstraint(
            "mode IN ('chat', 'short_drama_narration', 'video_translation', 'video_generation')",
            name="ck_conversation_threads_mode",
        ),
        Index("ix_conversation_threads_user_updated", "user_id", "updated_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    mode: Mapped[str] = mapped_column(String(32), nullable=False, default="chat")
    title: Mapped[str | None] = mapped_column(String(200))
    chat_summary: Mapped[str | None] = mapped_column(Text)
    chat_memory: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    chat_memory_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)


class ConversationMessage(Base):
    __tablename__ = "conversation_messages"
    __table_args__ = (
        CheckConstraint("role IN ('user', 'assistant', 'system')", name="ck_conversation_messages_role"),
        CheckConstraint(
            "mode IN ('chat', 'short_drama_narration', 'video_translation', 'video_generation')",
            name="ck_conversation_messages_mode",
        ),
        UniqueConstraint("thread_id", "idempotency_key", name="uq_conversation_messages_idempotency"),
        Index("ix_conversation_messages_thread_created", "thread_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    thread_id: Mapped[str] = mapped_column(String(64), ForeignKey("conversation_threads.id", ondelete="RESTRICT"), nullable=False)
    user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    mode: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    attachments: Mapped[list[dict]] = mapped_column(JSON, nullable=False, default=list)
    idempotency_key: Mapped[str | None] = mapped_column(String(256))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class AgentRun(Base):
    __tablename__ = "agent_runs"
    __table_args__ = (
        CheckConstraint(
            "mode IN ('short_drama_narration', 'video_translation', 'video_generation')",
            name="ck_agent_runs_mode",
        ),
        CheckConstraint("status IN ('pending', 'queued', 'running', 'completed', 'failed')", name="ck_agent_runs_status"),
        UniqueConstraint("user_id", "idempotency_key", name="uq_agent_runs_user_idempotency"),
        Index("ix_agent_runs_thread_created", "thread_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    thread_id: Mapped[str] = mapped_column(String(64), ForeignKey("conversation_threads.id", ondelete="RESTRICT"), nullable=False)
    message_id: Mapped[str] = mapped_column(String(64), ForeignKey("conversation_messages.id", ondelete="RESTRICT"), nullable=False)
    user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    mode: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    idempotency_key: Mapped[str] = mapped_column(String(256), nullable=False)
    input_config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    resolved_config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    project_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("projects.id", ondelete="RESTRICT"))
    workflow_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("workflows.id", ondelete="RESTRICT"))
    model_task_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("model_tasks.id", ondelete="RESTRICT"))
    result: Mapped[dict | None] = mapped_column(JSON)
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)
