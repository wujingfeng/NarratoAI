from __future__ import annotations

from sqlalchemy import select

from narrato_api.workflows.models import (
    WorkflowNodeAttempt,
    WorkflowReconciliationEvent,
)
from narrato_api.workflows.reconciler import WorkflowReconciler

from helpers import workflow_fixture


def test_polling_recovers_lost_callback_and_late_callback_has_no_second_effect() -> (
    None
):
    sessions, _ = workflow_fixture(node_names=("media_probe",))
    reconciler = WorkflowReconciler(sessions)

    assert reconciler.reconcile_polling(
        core_task_id="ctask_e2e_1",
        event_id="evt_polled",
        state_version=4,
        state="succeeded",
        result={"artifact_id": "art_polled"},
    )
    assert not reconciler.reconcile_callback(
        core_task_id="ctask_e2e_1",
        event_id="evt_late_callback",
        state_version=4,
        state="succeeded",
        result={"artifact_id": "art_polled"},
    )

    with sessions() as session:
        attempt = session.get(WorkflowNodeAttempt, "wat_e2e_1")
        events = session.scalars(select(WorkflowReconciliationEvent)).all()
    assert attempt is not None and (attempt.state, attempt.state_version) == (
        "completed",
        4,
    )
    assert [(event.event_id, event.source) for event in events] == [
        ("evt_polled", "polling")
    ]
