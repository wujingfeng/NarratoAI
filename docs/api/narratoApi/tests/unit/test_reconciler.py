from __future__ import annotations

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from narrato_api.auth.models import User
from narrato_api.billing.models import CreditAccount, CreditLedger
from narrato_api.billing.service import _apply_credit
from narrato_api.database import Base
from narrato_api.projects.models import Project
from narrato_api.workflows.models import (
    Workflow,
    WorkflowNode,
    WorkflowNodeAttempt,
    WorkflowTemplateSnapshot,
)
from narrato_api.workflows.reconciler import WorkflowReconciler


def _reconciler() -> tuple[WorkflowReconciler, sessionmaker]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    with sessions.begin() as session:
        session.add(
            User(
                id="usr_reconcile", email="reconcile@example.com", password_hash="hash"
            )
        )
        session.add(
            Project(
                id="prj_reconcile",
                user_id="usr_reconcile",
                product="short_drama",
                status="queued",
            )
        )
        session.add(
            WorkflowTemplateSnapshot(
                id="tpl_reconcile",
                template_name="short_drama_narration",
                version="v1",
                definition={"nodes": [{"name": "media_probe"}]},
            )
        )
        session.add(
            Workflow(
                id="wfl_reconcile",
                user_id="usr_reconcile",
                project_id="prj_reconcile",
                template_snapshot_id="tpl_reconcile",
                state="queued",
            )
        )
        session.add(
            WorkflowNode(
                id="wnd_reconcile",
                workflow_id="wfl_reconcile",
                name="media_probe",
                state="running",
            )
        )
        session.add(
            WorkflowNodeAttempt(
                id="wat_reconcile",
                workflow_node_id="wnd_reconcile",
                attempt_number=1,
                state="running",
                core_task_id="ctask_reconcile",
            )
        )
    return WorkflowReconciler(sessions), sessions


def test_callback_and_polling_converge_on_one_terminal_event() -> None:
    reconciler, sessions = _reconciler()

    assert reconciler.reconcile_callback(
        core_task_id="ctask_reconcile",
        event_id="evt_core_succeeded_3",
        state_version=3,
        state="succeeded",
        result={"artifact_id": "art_1"},
    )
    assert not reconciler.reconcile_polling(
        core_task_id="ctask_reconcile",
        event_id="evt_core_succeeded_3",
        state_version=3,
        state="succeeded",
        result={"artifact_id": "art_1"},
    )

    with sessions() as session:
        attempt = session.get(WorkflowNodeAttempt, "wat_reconcile")
        node = session.get(WorkflowNode, "wnd_reconcile")
        workflow = session.get(Workflow, "wfl_reconcile")

    assert attempt is not None and (
        attempt.state,
        attempt.state_version,
        attempt.result,
    ) == (
        "completed",
        3,
        {"artifact_id": "art_1"},
    )
    assert node is not None and node.state == "completed"
    assert workflow is not None and (workflow.state, workflow.state_version) == (
        "completed",
        2,
    )


def test_stale_or_same_version_terminal_results_do_not_overwrite_completion() -> None:
    reconciler, sessions = _reconciler()
    assert reconciler.reconcile_callback(
        core_task_id="ctask_reconcile",
        event_id="evt_core_succeeded_3",
        state_version=3,
        state="succeeded",
        result={"artifact_id": "art_1"},
    )

    assert not reconciler.reconcile_polling(
        core_task_id="ctask_reconcile",
        event_id="evt_core_succeeded_duplicate_version",
        state_version=3,
        state="failed",
        result={"error_code": "LATE_FAILURE"},
    )
    assert not reconciler.reconcile_callback(
        core_task_id="ctask_reconcile",
        event_id="evt_core_stale_2",
        state_version=2,
        state="failed",
        result={"error_code": "STALE_FAILURE"},
    )

    with sessions() as session:
        attempt = session.get(WorkflowNodeAttempt, "wat_reconcile")
        node = session.get(WorkflowNode, "wnd_reconcile")
        workflow = session.get(Workflow, "wfl_reconcile")

    assert attempt is not None and (
        attempt.state,
        attempt.state_version,
        attempt.result,
    ) == (
        "completed",
        3,
        {"artifact_id": "art_1"},
    )
    assert node is not None and node.state == "completed"
    assert workflow is not None and workflow.state == "completed"


def test_higher_version_result_does_not_overwrite_cancellation() -> None:
    reconciler, sessions = _reconciler()
    assert reconciler.reconcile_callback(
        core_task_id="ctask_reconcile",
        event_id="evt_core_cancelled_3",
        state_version=3,
        state="cancelled",
        result={"error_code": "USER_CANCELLED"},
    )

    assert not reconciler.reconcile_polling(
        core_task_id="ctask_reconcile",
        event_id="evt_core_late_success_4",
        state_version=4,
        state="succeeded",
        result={"artifact_id": "late_artifact"},
    )

    with sessions() as session:
        attempt = session.get(WorkflowNodeAttempt, "wat_reconcile")
        node = session.get(WorkflowNode, "wnd_reconcile")
        workflow = session.get(Workflow, "wfl_reconcile")

    assert attempt is not None and (
        attempt.state,
        attempt.state_version,
        attempt.result,
    ) == (
        "cancelled",
        3,
        {"error_code": "USER_CANCELLED"},
    )
    assert node is not None and node.state == "cancelled"
    assert workflow is not None and workflow.state == "cancelled"


def test_video_translation_failure_refunds_main_charge_not_preview_charge() -> None:
    """试听也是 project reference，但失败退款不得误退其 12 点消费。"""

    reconciler, sessions = _reconciler()
    with sessions.begin() as session:
        project = session.get(Project, "prj_reconcile")
        assert project is not None
        project.product = "video_translation"
        session.add(CreditAccount(user_id="usr_reconcile", balance=100))
        _apply_credit(
            session,
            user_id="usr_reconcile",
            entry_type="charge",
            amount=-80,
            idempotency_key="charge:prj_reconcile",
            reference_id="prj_reconcile",
            reason="video_translation_charge",
        )
        _apply_credit(
            session,
            user_id="usr_reconcile",
            entry_type="charge",
            amount=-12,
            idempotency_key="translation-preview:prj_reconcile:seg:charge",
            reference_id="prj_reconcile",
            reason="video_translation_preview",
        )

    assert reconciler.reconcile_callback(
        core_task_id="ctask_reconcile",
        event_id="evt_translation_failure",
        state_version=1,
        state="failed",
        result={"error": {"code": "RENDER_FAILED"}},
    )
    with sessions() as session:
        account = session.get(CreditAccount, "usr_reconcile")
        entries = session.scalars(
            select(CreditLedger)
            .where(CreditLedger.reference_id == "prj_reconcile")
            .order_by(CreditLedger.id)
        ).all()
    assert account is not None and account.balance == 88
    assert [(entry.reason, entry.amount) for entry in entries] == [
        ("video_translation_charge", -80),
        ("video_translation_preview", -12),
        ("project_failed_refund", 80),
    ]
