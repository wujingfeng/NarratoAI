"""Celery 入口：重放 Outbox，并轮询没有收到 Core 回调的原子任务。"""

from __future__ import annotations

from celery import Celery
from sqlalchemy.engine import Engine
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from narrato_api.config import Settings
from narrato_api.database import create_database_engine
from narrato_api.integrations.core_client import HttpCoreClient
from narrato_api.workflows.dispatcher import WorkflowOutboxDispatcher
from narrato_api.workflows.models import WorkflowNodeAttempt, WorkflowOutbox
from narrato_api.workflows.orchestrator import WorkflowDispatchError, WorkflowOrchestrator
from narrato_api.workflows.reconciler import WorkflowReconciler


def _services(
    settings: Settings,
) -> tuple[Engine, sessionmaker[Session], HttpCoreClient]:
    engine = create_database_engine(
        settings.database_url,
        settings.database_connect_timeout_seconds,
        settings.database_read_timeout_seconds,
    )
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    client = HttpCoreClient(
        base_url=str(settings.core_base_url), request_token=settings.core_request_token
    )
    return engine, sessions, client


def register_workflow_tasks(app: Celery, settings: Settings) -> None:
    @app.task(name="narrato.workflows.replay_outbox")  # type: ignore[untyped-decorator]
    def replay_outbox(*, limit: int = 100) -> int:
        engine, sessions, client = _services(settings)
        try:
            dispatcher = WorkflowOutboxDispatcher(sessions)
            dispatcher.requeue_expired_sending(
                lease_seconds=settings.workflow_outbox_lease_seconds
            )
            with sessions() as session:
                event_ids = list(
                    session.scalars(
                        select(WorkflowOutbox.id)
                        .where(WorkflowOutbox.status == "pending")
                        .order_by(WorkflowOutbox.created_at)
                        .limit(limit)
                    )
                )
            orchestrator = WorkflowOrchestrator(
                sessions,
                video_translation_model_id=settings.video_translation_model_id,
            )
            sent = 0
            for event_id in event_ids:

                def wake(_event_id: str, _key: str, *, item_id: str = event_id) -> bool:
                    with sessions() as session:
                        event = session.get(WorkflowOutbox, item_id)
                        if event is None:
                            return False
                        workflow_id = event.workflow_id
                    return orchestrator.dispatch_ready(
                        workflow_id=workflow_id, core_client=client
                    )

                if dispatcher.dispatch(event_id, wake):
                    sent += 1
            return sent
        finally:
            engine.dispose()

    @app.task(name="narrato.workflows.poll_core_tasks")  # type: ignore[untyped-decorator]
    def poll_core_tasks(*, limit: int = 100) -> int:
        engine, sessions, client = _services(settings)
        try:
            with sessions() as session:
                task_ids = list(
                    session.scalars(
                        select(WorkflowNodeAttempt.core_task_id)
                        .where(
                            WorkflowNodeAttempt.state == "running",
                            WorkflowNodeAttempt.core_task_id.is_not(None),
                        )
                        .order_by(WorkflowNodeAttempt.created_at)
                        .limit(limit)
                    )
                )
            reconciler = WorkflowReconciler(sessions)
            orchestrator = WorkflowOrchestrator(
                sessions,
                video_translation_model_id=settings.video_translation_model_id,
            )
            applied = 0
            for core_task_id in task_ids:
                if core_task_id is None:
                    continue
                try:
                    result = client.get_task_result(core_task_id)
                except Exception:
                    continue
                # 目前 Core 只定义 succeeded/failed 终态；cancelled 仅由本地
                # 工作流传播使用，不把它作为 Core 轮询契约。
                if result.status not in {"succeeded", "failed"}:
                    continue
                payload = (
                    result.result
                    if isinstance(result.result, dict)
                    else {"result": result.result}
                )
                if reconciler.reconcile_polling(
                    core_task_id=core_task_id,
                    event_id=f"poll:{core_task_id}:{result.state_version}:{result.status}",
                    state_version=result.state_version,
                    state=result.status,
                    result={"result": payload, "artifacts": list(result.artifacts)},
                ):
                    applied += 1
                    if result.status == "succeeded":
                        try:
                            orchestrator.dispatch_ready(
                                workflow_id=reconciler.workflow_id_for_core_task(
                                    core_task_id
                                ),
                                core_client=client,
                            )
                        except (LookupError, WorkflowDispatchError):
                            # 收口事务已创建 pending Outbox；即时提交失败时由
                            # replay_outbox 按同一 attempt 幂等重试。
                            pass
            return applied
        finally:
            engine.dispose()
