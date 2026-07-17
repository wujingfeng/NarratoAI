from __future__ import annotations

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from narrato_api.auth.models import User
from narrato_api.database import Base
from narrato_api.projects.models import Project
from narrato_api.workflows.models import Workflow, WorkflowNode, WorkflowOutbox, WorkflowTemplateSnapshot
from narrato_api.workflows.service import WorkflowService


def _workflow_service() -> tuple[WorkflowService, sessionmaker]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    with sessions.begin() as session:
        session.add(User(id="usr_workflow", email="workflow@example.com", password_hash="hash"))
        session.add(Project(id="prj_workflow", user_id="usr_workflow", product="short_drama", status="queued"))
        session.add(
            WorkflowTemplateSnapshot(
                id="tpl_short_drama_v1",
                template_name="short_drama_narration",
                version="short_drama_narration_v1",
                definition={
                    "nodes": [
                        {"name": "media_probe", "depends_on": [], "max_attempts": 3},
                        {
                            "name": "waiting_for_edit",
                            "depends_on": ["media_probe"],
                            "retryable": False,
                            "manual_gate": True,
                            "max_attempts": 1,
                        },
                    ]
                },
            )
        )
    return WorkflowService(sessions), sessions


def test_instantiate_workflow_persists_all_nodes_from_its_versioned_snapshot() -> None:
    service, sessions = _workflow_service()

    workflow_id = service.instantiate_workflow(
        user_id="usr_workflow",
        project_id="prj_workflow",
        template_snapshot_id="tpl_short_drama_v1",
    )

    with sessions() as session:
        workflow = session.get(Workflow, workflow_id)
        nodes = session.scalars(
            select(WorkflowNode).where(WorkflowNode.workflow_id == workflow_id).order_by(WorkflowNode.name)
        ).all()

    assert workflow is not None
    assert (workflow.user_id, workflow.project_id, workflow.template_snapshot_id, workflow.state) == (
        "usr_workflow",
        "prj_workflow",
        "tpl_short_drama_v1",
        "draft",
    )
    assert [(node.name, node.depends_on, node.retryable, node.manual_gate, node.max_attempts) for node in nodes] == [
        ("media_probe", [], True, False, 3),
        ("waiting_for_edit", ["media_probe"], False, True, 1),
    ]


def test_transition_persists_state_and_a_single_idempotent_outbox_event() -> None:
    service, sessions = _workflow_service()
    workflow_id = service.instantiate_workflow(
        user_id="usr_workflow",
        project_id="prj_workflow",
        template_snapshot_id="tpl_short_drama_v1",
    )

    assert service.transition_workflow(
        workflow_id=workflow_id,
        target_state="queued",
        actor="system",
        idempotency_key="workflow-state:queued:one",
    )
    assert not service.transition_workflow(
        workflow_id=workflow_id,
        target_state="queued",
        actor="system",
        idempotency_key="workflow-state:queued:one",
    )

    with sessions() as session:
        workflow = session.get(Workflow, workflow_id)
        outbox = session.scalars(
            select(WorkflowOutbox).where(WorkflowOutbox.workflow_id == workflow_id)
        ).all()

    assert workflow is not None and (workflow.state, workflow.state_version) == ("queued", 1)
    assert [(event.event_type, event.idempotency_key, event.status, event.payload) for event in outbox] == [
        (
            "workflow.state_changed",
            "workflow-state:queued:one",
            "pending",
            {"state": "queued", "state_version": 1},
        )
    ]
