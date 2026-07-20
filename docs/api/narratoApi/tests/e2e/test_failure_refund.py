from __future__ import annotations

from sqlalchemy import select

from narrato_api.billing.models import CreditAccount, CreditLedger
from narrato_api.billing.service import BillingService
from narrato_api.workflows.reconciler import WorkflowReconciler

from helpers import workflow_fixture


def test_terminal_failure_refunds_the_original_charge_exactly_once() -> None:
    sessions, _ = workflow_fixture(node_names=("media_probe",))
    billing = BillingService(sessions)
    billing.grant("usr_e2e", 100, reason="test", idempotency_key="grant:e2e")
    billing.charge_project("usr_e2e", "prj_e2e", 25)
    reconciler = WorkflowReconciler(sessions)

    assert reconciler.reconcile_callback(
        core_task_id="ctask_e2e_1", event_id="evt_refund", state_version=1,
        state="failed", result={"code": "TERMINAL"},
    )
    assert not reconciler.reconcile_polling(
        core_task_id="ctask_e2e_1", event_id="evt_refund_duplicate", state_version=1,
        state="failed", result={"code": "TERMINAL"},
    )

    with sessions() as session:
        account = session.get(CreditAccount, "usr_e2e")
        entries = session.scalars(
            select(CreditLedger)
            .where(CreditLedger.reference_id == "prj_e2e")
            .order_by(CreditLedger.created_at)
        ).all()
    assert account is not None and account.balance == 100
    assert [(entry.entry_type, entry.amount) for entry in entries] == [
        ("charge", -25), ("refund", 25),
    ]
