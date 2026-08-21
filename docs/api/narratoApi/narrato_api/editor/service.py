from __future__ import annotations

import secrets
import time
from collections.abc import Callable
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from narrato_api.editor.models import EditorDraft
from narrato_api.projects.models import Project
from narrato_api.projects.service import (
    ProjectLifecycleConflict,
    materialize_editor_draft,
    queue_project_render,
)
from narrato_api.workflows.models import Workflow, WorkflowOutbox


class EditorLockedError(ValueError):
    """项目不再处于可编辑等待状态时抛出。"""


class EditorWorkflowNotFoundError(LookupError):
    """提交渲染时缺少项目工作流时抛出。"""


class EditorDraftNotFoundError(LookupError):
    """提交渲染时没有可快照化草稿时抛出。"""


class EditorProjectNotFoundError(LookupError):
    """编辑器读取时项目不存在或不属于当前用户。"""


class EditorRenderSnapshotError(ValueError):
    """当前编辑草稿无法生成合法的 Core Render 请求。"""


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
        """仅允许未锁定的 waiting_for_edit 项目覆盖当前可变草稿。"""

        with self.session_factory() as session:
            with session.begin():
                project = self._editable_project(
                    session, user_id=user_id, project_id=project_id
                )
                draft = session.get(EditorDraft, project.id)
                if draft is None:
                    draft = EditorDraft(
                        id=_new_id("edr"), project_id=project.id, content=content
                    )
                    session.add(draft)
                else:
                    draft.content = content
                return draft.id

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
                try:
                    queue_project_render(
                        session,
                        project=project,
                        workflow=workflow,
                        idempotency_key=idempotency_key,
                    )
                except ProjectLifecycleConflict as error:
                    if error.code == "PROJECT_SCRIPT_UNAVAILABLE":
                        raise EditorDraftNotFoundError(str(error)) from error
                    if error.code == "PROJECT_RENDER_INVALID":
                        raise EditorRenderSnapshotError(str(error)) from error
                    raise EditorWorkflowNotFoundError(str(error)) from error
                return True

    def get_draft(self, *, user_id: str, project_id: str) -> tuple[EditorDraft, bool]:
        """读取当前用户项目草稿；提交渲染后仍可只读访问。"""

        with self.session_factory() as session:
            materialized = False
            project = session.scalar(
                select(Project).where(
                    Project.id == project_id, Project.user_id == user_id
                )
            )
            if project is None:
                raise EditorProjectNotFoundError("project was not found")
            draft = session.get(EditorDraft, project.id)
            legacy_demo_draft = draft is not None and _contains_legacy_demo_media(draft.content)
            if draft is None or legacy_demo_draft:
                # 兼容已进入 edit 阶段、但在初始化机制上线前遗漏草稿的旧项目。
                # 使用同一事务内已验证的项目素材回填，绝不引入本地演示数据。
                if project.current_stage != "edit" or project.is_locked:
                    raise EditorDraftNotFoundError("editor draft not found")
                materialize_editor_draft(session, project=project)
                session.flush()
                materialized = True
                draft = session.get(EditorDraft, project.id)
                if draft is None:
                    raise EditorDraftNotFoundError("editor draft not found")
            locked = project.is_locked
            if materialized:
                session.commit()
                session.refresh(draft)
            session.expunge(draft)
            return draft, locked
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
        if project is None:
            raise EditorProjectNotFoundError("project was not found")
        if project.status != "waiting_for_edit" or project.current_stage != "edit" or project.is_locked:
            raise EditorLockedError("project editor is locked")
        return project


def _contains_legacy_demo_media(content: object) -> bool:
    """仅识别历史演示路径，避免覆盖已经由真实 API 写入的用户草稿。"""

    if not isinstance(content, dict) or not isinstance(content.get("clips"), list):
        return False
    return any(
        isinstance(clip, dict)
        and isinstance(clip.get("asset_id"), str)
        and clip["asset_id"].startswith("/media/narration-editor/")
        for clip in content["clips"]
    )
