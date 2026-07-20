from __future__ import annotations

import secrets
import time
from collections.abc import Callable
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from narrato_api.billing.models import CreditLedger
from narrato_api.billing.service import _apply_credit
from narrato_api.projects.models import Project
from narrato_api.workflows.models import (
    Workflow,
    WorkflowNode,
    WorkflowNodeAttempt,
    WorkflowReconciliationEvent,
    utc_now,
)


def _new_id() -> str:
    """生成收口事件的服务端 ID。"""

    return f"wre_{time.time_ns():016x}{secrets.token_hex(8)}"


class WorkflowReconciler:
    """让 Core 回调和轮询结果进入同一个幂等数据库事务。"""

    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self.session_factory = session_factory

    def reconcile_callback(self, **result: Any) -> bool:
        """收口 Core 回调的终态结果。"""

        return self._reconcile(source="callback", **result)

    def reconcile_polling(self, **result: Any) -> bool:
        """收口持续轮询取得的终态结果。"""

        return self._reconcile(source="polling", **result)

    def _reconcile(
        self,
        *,
        source: Literal["callback", "polling"],
        core_task_id: str,
        event_id: str,
        state_version: int,
        state: Literal["succeeded", "failed"],
        result: dict[str, Any],
    ) -> bool:
        """按事件和状态版本原子应用一个 Core 终态，重复或过期结果无副作用。"""

        if not core_task_id or not event_id or state_version < 0:
            raise ValueError("core_task_id, event_id and non-negative state_version are required")
        if state not in {"succeeded", "failed"}:
            raise ValueError("only terminal Core states can be reconciled")
        with self.session_factory() as session:
            with session.begin():
                attempt = session.scalar(
                    select(WorkflowNodeAttempt)
                    .where(WorkflowNodeAttempt.core_task_id == core_task_id)
                    .with_for_update()
                )
                if attempt is None:
                    raise LookupError("workflow node attempt not found")
                # 同一 Core 版本或更早版本均不允许覆盖已经确认的终态。
                if state_version <= attempt.state_version:
                    return False
                node = session.scalar(
                    select(WorkflowNode)
                    .where(WorkflowNode.id == attempt.workflow_node_id)
                    .with_for_update()
                )
                if node is None:
                    raise LookupError("workflow node not found")
                workflow = session.scalar(
                    select(Workflow).where(Workflow.id == node.workflow_id).with_for_update()
                )
                if workflow is None:
                    raise LookupError("workflow not found")
                if attempt.state in {"completed", "failed"}:
                    return False

                session.add(
                    WorkflowReconciliationEvent(
                        id=_new_id(),
                        workflow_node_attempt_id=attempt.id,
                        event_id=event_id,
                        state_version=state_version,
                        source=source,
                        state=state,
                    )
                )
                attempt.state = "completed" if state == "succeeded" else "failed"
                attempt.state_version = state_version
                attempt.result = result
                attempt.completed_at = utc_now()
                node.state = attempt.state

                # 本原子任务只收口持久化状态；不派发下游任务或运行任何 dispatcher。
                if workflow.state == "queued":
                    workflow.state = "running"
                    workflow.state_version += 1
                if state == "failed":
                    workflow.state = "failed"
                    workflow.state_version += 1
                elif not session.scalar(
                    select(WorkflowNode.id).where(
                        WorkflowNode.workflow_id == workflow.id,
                        WorkflowNode.state != "completed",
                    )
                ):
                    workflow.state = "completed"
                    workflow.state_version += 1
                if workflow.state in {"completed", "failed"}:
                    project = session.get(Project, workflow.project_id)
                    if project is not None:
                        project.status = workflow.state
                        if workflow.state == "failed":
                            charge = session.scalar(
                                select(CreditLedger)
                                .where(
                                    CreditLedger.reference_id == project.id,
                                    CreditLedger.entry_type == "charge",
                                )
                                .with_for_update()
                            )
                            if charge is not None:
                                _apply_credit(
                                    session,
                                    user_id=charge.user_id,
                                    entry_type="refund",
                                    amount=-charge.amount,
                                    idempotency_key=f"refund:{project.id}",
                                    reference_id=project.id,
                                    reason="project_failed_refund",
                                )
                return True
