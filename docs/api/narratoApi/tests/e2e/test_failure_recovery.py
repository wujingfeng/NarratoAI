from __future__ import annotations

from narrato_api.projects.models import Project
from narrato_api.workflows.models import Workflow
from narrato_api.workflows.reconciler import WorkflowReconciler

from helpers import workflow_fixture


def test_terminal_core_failure_marks_workflow_and_project_failed_once() -> None:
    sessions, _ = workflow_fixture(node_names=("media_probe",))
    reconciler = WorkflowReconciler(sessions)

    assert reconciler.reconcile_callback(
        core_task_id="ctask_e2e_1", event_id="evt_failed", state_version=3,
        state="failed", result={"code": "PROVIDER_UNAVAILABLE"},
    )
    assert not reconciler.reconcile_polling(
        core_task_id="ctask_e2e_1", event_id="evt_failed_retry", state_version=3,
        state="failed", result={"code": "PROVIDER_UNAVAILABLE"},
    )

    with sessions() as session:
        workflow = session.get(Workflow, "wfl_e2e")
        project = session.get(Project, "prj_e2e")
    assert workflow is not None and workflow.state == "failed"
    assert project is not None and project.status == "failed"
