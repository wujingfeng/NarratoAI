from __future__ import annotations

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from narrato_api.auth.models import User
from narrato_api.billing.models import CreditAccount, CreditLedger
from narrato_api.billing.service import BillingService
from narrato_api.database import Base


def test_failure_refund_is_applied_once_as_a_reverse_ledger_entry() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    with sessions.begin() as session:
        session.add(
            User(
                id="usr_refund",
                email="refund@example.com",
                password_hash="test-hash",
                status="active",
            )
        )
    billing = BillingService(sessions)
    billing.grant("usr_refund", 100, reason="operator_grant", idempotency_key="grant:one")
    billing.charge_project("usr_refund", "prj_refund", 20)
    billing.refund_failed_project("prj_refund")
    billing.refund_failed_project("prj_refund")

    with sessions() as session:
        account = session.get(CreditAccount, "usr_refund")
        entries = session.scalars(
            select(CreditLedger)
            .where(CreditLedger.reference_id == "prj_refund")
            .order_by(CreditLedger.created_at)
        ).all()
        assert account is not None and account.balance == 100
        assert [(entry.entry_type, entry.amount) for entry in entries] == [
            ("charge", -20),
            ("refund", 20),
        ]
