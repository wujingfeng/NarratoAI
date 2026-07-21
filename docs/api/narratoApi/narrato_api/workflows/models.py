from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from narrato_api.database import Base


def utc_now() -> datetime:
    """返回带时区的 UTC 当前时间。"""

    return datetime.now(timezone.utc)


class WorkflowTemplateSnapshot(Base):
    """已发布工作流模板的不可变版本化 DAG 快照。"""

    __tablename__ = "workflow_template_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "template_name", "version", name="uq_workflow_templates_name_version"
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    template_name: Mapped[str] = mapped_column(String(128), nullable=False)
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    definition: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class Workflow(Base):
    """一个项目关联的工作流实例及其状态版本。"""

    __tablename__ = "workflows"
    __table_args__ = (
        CheckConstraint(
            "state IN ('draft', 'queued', 'running', 'waiting_for_edit', "
            "'render_queued', 'completed', 'failed')",
            name="ck_workflows_state",
        ),
        CheckConstraint("state_version >= 0", name="ck_workflows_state_version"),
        UniqueConstraint("project_id", name="uq_workflows_project_id"),
        Index("ix_workflows_user_created", "user_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False
    )
    template_snapshot_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("workflow_template_snapshots.id", ondelete="RESTRICT"),
        nullable=False,
    )
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    state_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class WorkflowNode(Base):
    """DAG 快照中的实例化节点和其依赖关系。"""

    __tablename__ = "workflow_nodes"
    __table_args__ = (
        CheckConstraint(
            "state IN ('queued', 'running', 'waiting_for_edit', 'completed', 'failed')",
            name="ck_workflow_nodes_state",
        ),
        CheckConstraint("max_attempts >= 1", name="ck_workflow_nodes_max_attempts"),
        UniqueConstraint("workflow_id", "name", name="uq_workflow_nodes_workflow_name"),
        Index("ix_workflow_nodes_workflow_state", "workflow_id", "state"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workflow_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("workflows.id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="queued")
    depends_on: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    retryable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    manual_gate: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class WorkflowNodeAttempt(Base):
    """单个节点的可审计尝试记录。"""

    __tablename__ = "workflow_node_attempts"
    __table_args__ = (
        CheckConstraint(
            "state IN ('queued', 'running', 'completed', 'failed')",
            name="ck_workflow_node_attempts_state",
        ),
        CheckConstraint("attempt_number >= 1", name="ck_workflow_node_attempts_number"),
        CheckConstraint(
            "state_version >= 0", name="ck_workflow_node_attempts_state_version"
        ),
        UniqueConstraint(
            "workflow_node_id",
            "attempt_number",
            name="uq_workflow_node_attempts_node_number",
        ),
        UniqueConstraint("core_task_id", name="uq_workflow_node_attempts_core_task_id"),
        Index("ix_workflow_node_attempts_node_state", "workflow_node_id", "state"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workflow_node_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("workflow_nodes.id", ondelete="RESTRICT"), nullable=False
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="queued")
    state_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    core_task_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class WorkflowReconciliationEvent(Base):
    """已进入统一收口事务的 Core 终态事件去重记录。"""

    __tablename__ = "workflow_reconciliation_events"
    __table_args__ = (
        CheckConstraint(
            "state_version >= 0", name="ck_workflow_reconciliation_events_state_version"
        ),
        UniqueConstraint(
            "workflow_node_attempt_id",
            "event_id",
            name="uq_workflow_reconciliation_events_attempt_event",
        ),
        UniqueConstraint(
            "workflow_node_attempt_id",
            "state_version",
            name="uq_workflow_reconciliation_events_attempt_state_version",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workflow_node_attempt_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("workflow_node_attempts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    event_id: Mapped[str] = mapped_column(String(128), nullable=False)
    state_version: Mapped[int] = mapped_column(Integer, nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class WorkflowOutbox(Base):
    """数据库事务内创建、由后续派发器可靠投递的工作流事件。"""

    __tablename__ = "workflow_outbox"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'sending', 'sent', 'dead')",
            name="ck_workflow_outbox_status",
        ),
        UniqueConstraint("idempotency_key", name="uq_workflow_outbox_idempotency_key"),
        Index("ix_workflow_outbox_status_created", "status", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workflow_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("workflows.id", ondelete="RESTRICT"), nullable=False
    )
    workflow_node_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("workflow_nodes.id", ondelete="RESTRICT"), nullable=True
    )
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
