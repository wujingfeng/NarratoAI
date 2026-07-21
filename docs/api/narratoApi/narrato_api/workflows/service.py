from __future__ import annotations

import secrets
import time
from collections.abc import Callable
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from narrato_api.projects.models import Project
from narrato_api.workflows.models import (
    Workflow,
    WorkflowNode,
    WorkflowOutbox,
    WorkflowTemplateSnapshot,
)
from narrato_api.workflows.state_machine import transition_workflow_state


class WorkflowNotFoundError(LookupError):
    """工作流或其关联快照不存在时抛出。"""


def _new_id(prefix: str) -> str:
    """生成服务端工作流记录 ID。"""

    return f"{prefix}_{time.time_ns():016x}{secrets.token_hex(8)}"


def _snapshot_nodes(definition: dict[str, Any]) -> list[dict[str, Any]]:
    """校验并提取持久化快照中的节点定义。"""

    nodes = definition.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        raise ValueError("workflow template snapshot must define nodes")
    names: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for node in nodes:
        if not isinstance(node, dict) or not isinstance(node.get("name"), str):
            raise ValueError("workflow template node must define a name")
        name = node["name"]
        depends_on = node.get("depends_on", [])
        if not name or name in names or not isinstance(depends_on, list):
            raise ValueError("workflow template node is invalid")
        if not all(isinstance(dependency, str) for dependency in depends_on):
            raise ValueError("workflow template dependencies must be strings")
        max_attempts = node.get("max_attempts", 3)
        if not isinstance(max_attempts, int) or max_attempts < 1:
            raise ValueError("workflow template max_attempts must be positive")
        names.add(name)
        normalized.append(
            {
                "name": name,
                "depends_on": depends_on,
                "retryable": bool(node.get("retryable", True)),
                "manual_gate": bool(node.get("manual_gate", False)),
                "max_attempts": max_attempts,
            }
        )
    if any(
        dependency not in names
        for node in normalized
        for dependency in node["depends_on"]
    ):
        raise ValueError("workflow template dependency is missing")
    return normalized


class WorkflowService:
    """以数据库事务创建工作流并记录状态变更事件。"""

    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self.session_factory = session_factory

    def instantiate_workflow(
        self, *, user_id: str, project_id: str, template_snapshot_id: str
    ) -> str:
        """从不可变模板快照在同一事务中创建工作流和全部节点。"""

        with self.session_factory() as session:
            with session.begin():
                project = session.scalar(
                    select(Project).where(
                        Project.id == project_id, Project.user_id == user_id
                    )
                )
                if project is None:
                    raise WorkflowNotFoundError("project not found")
                snapshot = session.get(WorkflowTemplateSnapshot, template_snapshot_id)
                if snapshot is None:
                    raise WorkflowNotFoundError("workflow template snapshot not found")
                nodes = _snapshot_nodes(snapshot.definition)
                workflow = Workflow(
                    id=_new_id("wfl"),
                    user_id=user_id,
                    project_id=project.id,
                    template_snapshot_id=snapshot.id,
                    state="draft",
                    state_version=0,
                )
                session.add(workflow)
                for node in nodes:
                    session.add(
                        WorkflowNode(
                            id=_new_id("wnd"),
                            workflow_id=workflow.id,
                            name=node["name"],
                            state="queued",
                            depends_on=node["depends_on"],
                            retryable=node["retryable"],
                            manual_gate=node["manual_gate"],
                            max_attempts=node["max_attempts"],
                        )
                    )
                return workflow.id

    def transition_workflow(
        self,
        *,
        workflow_id: str,
        target_state: str,
        actor: str,
        idempotency_key: str,
    ) -> bool:
        """持久化允许的状态转换，并在同一事务追加唯一 Outbox 事件。"""

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
                workflow = session.scalar(
                    select(Workflow).where(Workflow.id == workflow_id).with_for_update()
                )
                if workflow is None:
                    raise WorkflowNotFoundError("workflow not found")
                if not transition_workflow_state(
                    workflow.state, target_state, actor=actor
                ):
                    return False
                workflow.state = target_state
                workflow.state_version += 1
                session.add(
                    WorkflowOutbox(
                        id=_new_id("obx"),
                        workflow_id=workflow.id,
                        workflow_node_id=None,
                        event_type="workflow.state_changed",
                        idempotency_key=idempotency_key,
                        payload={
                            "state": workflow.state,
                            "state_version": workflow.state_version,
                        },
                        status="pending",
                    )
                )
                return True
