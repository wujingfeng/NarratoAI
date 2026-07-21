from __future__ import annotations

from sqlalchemy import select

from narrato_api.projects.models import Project
from narrato_api.workflows.models import Workflow, WorkflowNodeAttempt
from narrato_api.workflows.reconciler import WorkflowReconciler

from helpers import workflow_fixture


def test_fake_core_terminal_events_complete_full_short_drama_workflow() -> None:
    sessions, names = workflow_fixture()
    reconciler = WorkflowReconciler(sessions)

    assert names == (
        "media_probe",
        "asr",
        "video_analysis",
        "script_generation",
        "waiting_for_edit",
        "tts",
        "subtitle",
        "video_render",
        "publish_artifacts",
    )
    for index, _name in enumerate(names, start=1):
        assert reconciler.reconcile_callback(
            core_task_id=f"ctask_e2e_{index}",
            event_id=f"evt_e2e_{index}",
            state_version=1,
            state="succeeded",
            result={"artifact_id": f"art_e2e_{index}"},
        )

    with sessions() as session:
        workflow = session.get(Workflow, "wfl_e2e")
        project = session.get(Project, "prj_e2e")
        attempts = session.scalars(select(WorkflowNodeAttempt)).all()
    assert workflow is not None and workflow.state == "completed"
    assert project is not None and project.status == "completed"
    assert all(attempt.state == "completed" for attempt in attempts)
