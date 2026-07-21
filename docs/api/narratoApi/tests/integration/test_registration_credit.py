from __future__ import annotations

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from narrato_api.auth.models import User
from narrato_api.auth.service import (
    AuthService,
    EmailCodeManager,
    InMemoryEmailCodeStore,
    InMemorySessionStore,
    PasswordHasher,
    SingleSessionTokens,
)
from narrato_api.billing.models import CreditAccount, CreditLedger
from narrato_api.database import Base
from narrato_api.integrations.mail_client import FakeMailDispatcher


def test_successful_registration_commits_exactly_one_signup_bonus() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    codes = EmailCodeManager(
        InMemoryEmailCodeStore(), secret="test-secret", ttl_seconds=600
    )
    service = AuthService(
        session_factory=sessions,
        password_hasher=PasswordHasher(
            time_cost=1, memory_cost_kib=8192, parallelism=1
        ),
        codes=codes,
        tokens=SingleSessionTokens(InMemorySessionStore(), ttl_seconds=2_592_000),
        mail_dispatcher=FakeMailDispatcher(),
    )
    issue = codes.issue("signup@example.com", purpose="register")
    user = service.register(
        "signup@example.com", "Correct-Horse-Battery-42", issue.code
    )

    with sessions() as session:
        account = session.get(CreditAccount, user.id)
        entries = session.scalars(
            select(CreditLedger).where(CreditLedger.user_id == user.id)
        ).all()
        assert account is not None and account.balance == 100
        assert [
            (entry.entry_type, entry.amount, entry.idempotency_key) for entry in entries
        ] == [("signup_bonus", 100, f"signup:{user.id}")]
        assert session.get(User, user.id) is not None
