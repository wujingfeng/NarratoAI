from __future__ import annotations

import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from narrato_api.auth.models import User
from narrato_api.database import Base, create_database_engine
from narrato_api.projects.models import Project
from narrato_api.workflows.models import (
    Workflow,
    WorkflowNode,
    WorkflowNodeAttempt,
    WorkflowOutbox,
    WorkflowReconciliationEvent,
    WorkflowTemplateSnapshot,
)


def test_workflow_models_define_ownership_dependencies_and_lookup_constraints() -> None:
    engine = create_database_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    inspector = inspect(engine)

    assert {
        item["referred_table"] for item in inspector.get_foreign_keys("workflows")
    } == {
        "users",
        "projects",
        "workflow_template_snapshots",
    }
    assert {
        item["referred_table"] for item in inspector.get_foreign_keys("workflow_nodes")
    } == {"workflows"}
    assert {
        item["referred_table"]
        for item in inspector.get_foreign_keys("workflow_node_attempts")
    } == {"workflow_nodes"}
    assert {
        item["referred_table"] for item in inspector.get_foreign_keys("workflow_outbox")
    } == {
        "workflows",
        "workflow_nodes",
    }
    assert {
        item["referred_table"]
        for item in inspector.get_foreign_keys("workflow_reconciliation_events")
    } == {"workflow_node_attempts"}
    assert {
        item["name"] for item in inspector.get_unique_constraints("workflow_nodes")
    } >= {"uq_workflow_nodes_workflow_name"}
    assert {
        item["name"]
        for item in inspector.get_unique_constraints("workflow_node_attempts")
    } >= {"uq_workflow_node_attempts_node_number"}
    assert {
        item["name"] for item in inspector.get_unique_constraints("workflow_outbox")
    } >= {"uq_workflow_outbox_idempotency_key"}
    assert {
        item["name"]
        for item in inspector.get_unique_constraints("workflow_reconciliation_events")
    } >= {
        "uq_workflow_reconciliation_events_attempt_event",
        "uq_workflow_reconciliation_events_attempt_state_version",
    }
    assert {item["name"] for item in inspector.get_indexes("workflow_outbox")} >= {
        "ix_workflow_outbox_status_created"
    }


def test_workflow_records_persist_versioned_dag_and_reject_duplicate_node_attempt() -> (
    None
):
    engine = create_database_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(User(id="usr_1", email="owner@example.com", password_hash="hash"))
        session.add(
            Project(id="prj_1", user_id="usr_1", product="short_drama", status="queued")
        )
        session.flush()
        session.add(
            WorkflowTemplateSnapshot(
                id="tpl_1",
                template_name="short_drama_narration",
                version="v1",
                definition={"nodes": [{"name": "media_probe"}]},
            )
        )
        session.flush()
        session.add(
            Workflow(
                id="wfl_1",
                user_id="usr_1",
                project_id="prj_1",
                template_snapshot_id="tpl_1",
                state="queued",
            )
        )
        session.flush()
        session.add(
            WorkflowNode(
                id="wnd_1",
                workflow_id="wfl_1",
                name="media_probe",
                state="queued",
                depends_on=[],
                max_attempts=3,
            )
        )
        session.flush()
        session.add(
            WorkflowNodeAttempt(
                id="wat_1",
                workflow_node_id="wnd_1",
                attempt_number=1,
                state="queued",
            )
        )
        session.add(
            WorkflowOutbox(
                id="obx_1",
                workflow_id="wfl_1",
                workflow_node_id="wnd_1",
                event_type="node.dispatch",
                idempotency_key="dispatch:wfl_1:wnd_1:1",
                payload={"attempt": 1},
            )
        )
        session.add(
            WorkflowReconciliationEvent(
                id="wre_1",
                workflow_node_attempt_id="wat_1",
                event_id="evt_1",
                state_version=1,
                source="callback",
                state="succeeded",
            )
        )
        session.commit()

        assert session.get(Workflow, "wfl_1").template_snapshot_id == "tpl_1"  # type: ignore[union-attr]
        assert session.get(WorkflowNode, "wnd_1").depends_on == []  # type: ignore[union-attr]

        session.add(
            WorkflowNodeAttempt(
                id="wat_2",
                workflow_node_id="wnd_1",
                attempt_number=1,
                state="queued",
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
