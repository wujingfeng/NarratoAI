from __future__ import annotations

import secrets
import time
from collections.abc import Callable
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from narrato_api.editor.models import EditorRevision
from narrato_api.projects.models import Project
from narrato_api.workflows.models import Workflow, WorkflowOutbox


class EditorLockedError(ValueError):
    """项目不再处于可编辑等待状态时抛出。"""


class EditorWorkflowNotFoundError(LookupError):
    """提交渲染时缺少项目工作流时抛出。"""


def _new_id(prefix: str) -> str:
    """生成编辑器持久化记录 ID。"""

    return f"{prefix}_{time.time_ns():016x}{secrets.token_hex(8)}"


class EditorService:
    """管理等待编辑阶段的草稿保存和不可逆锁定边界。"""

    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self.session_factory = session_factory

    def save_draft(
        self, *, user_id: str, project_id: str, content: dict[str, Any]
    ) -> str:
        """仅允许未锁定的 waiting_for_edit 项目追加一份草稿快照。"""

        with self.session_factory() as session:
            with session.begin():
                project = self._editable_project(
                    session, user_id=user_id, project_id=project_id
                )
                revision = EditorRevision(
                    id=_new_id("edr"), project_id=project.id, content=content
                )
                session.add(revision)
                return revision.id

    def submit_render(
        self, *, user_id: str, project_id: str, idempotency_key: str
    ) -> bool:
        """在一个事务中锁定编辑器、切换状态并追加渲染 Outbox 事件。"""

        if not idempotency_key:
            raise ValueError("idempotency_key must not be empty")
        with self.session_factory() as session:
            with session.begin():
                existing = session.scalar(
                    select(WorkflowOutbox).where(
                        WorkflowOutbox.idempotency_key == idempotency_key
                    )
                )
                if existing is not None:
                    return False
                project = self._editable_project(
                    session, user_id=user_id, project_id=project_id
                )
                workflow = session.scalar(
                    select(Workflow)
                    .where(Workflow.project_id == project.id)
                    .with_for_update()
                )
                if workflow is None:
                    raise EditorWorkflowNotFoundError("workflow not found")
                project.is_locked = True
                project.status = "render_queued"
                workflow.state = "render_queued"
                workflow.state_version += 1
                session.add(
                    WorkflowOutbox(
                        id=_new_id("obx"),
                        workflow_id=workflow.id,
                        workflow_node_id=None,
                        event_type="workflow.render_requested",
                        idempotency_key=idempotency_key,
                        payload={"state": "render_queued"},
                        status="pending",
                    )
                )
                return True

    @staticmethod
    def _editable_project(
        session: Session, *, user_id: str, project_id: str
    ) -> Project:
        """锁定并返回仍可编辑的等待编辑项目。"""

        project = session.scalar(
            select(Project)
            .where(Project.id == project_id, Project.user_id == user_id)
            .with_for_update()
        )
        if (
            project is None
            or project.status != "waiting_for_edit"
            or project.is_locked
        ):
            raise EditorLockedError("project editor is locked")
        return project
