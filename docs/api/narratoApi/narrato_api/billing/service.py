from __future__ import annotations

from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from narrato_api.billing.models import CreditAccount, CreditLedger


class InsufficientCreditsError(Exception):
    """余额不足时不写入扣费流水。"""


class ChargeNotFoundError(Exception):
    """不能为不存在的扣费创建退款。"""


SessionFactory = Callable[[], Session]


def _entry(
    session: Session,
    *,
    user_id: str,
    entry_type: str,
    amount: int,
    idempotency_key: str,
    reference_id: str | None,
    reason: str,
) -> CreditLedger:
    ledger = CreditLedger(
        user_id=user_id,
        entry_type=entry_type,
        amount=amount,
        idempotency_key=idempotency_key,
        reference_id=reference_id,
        reason=reason,
    )
    session.add(ledger)
    return ledger


def _locked_account(session: Session, user_id: str) -> CreditAccount:
    account = session.scalar(
        select(CreditAccount).where(CreditAccount.user_id == user_id).with_for_update()
    )
    if account is None:
        account = CreditAccount(user_id=user_id, balance=0)
        session.add(account)
        session.flush()
    return account


def _apply_credit(
    session: Session,
    *,
    user_id: str,
    entry_type: str,
    amount: int,
    idempotency_key: str,
    reference_id: str | None,
    reason: str,
) -> bool:
    """在已开启事务中锁定余额并以唯一幂等键追加一笔流水。"""

    if amount == 0:
        raise ValueError("amount must not be zero")
    account = _locked_account(session, user_id)
    existing = session.scalar(
        select(CreditLedger).where(
            CreditLedger.user_id == user_id,
            CreditLedger.idempotency_key == idempotency_key,
        )
    )
    if existing is not None:
        return False
    if account.balance + amount < 0:
        raise InsufficientCreditsError("insufficient credits")
    account.balance += amount
    account.version += 1
    _entry(
        session,
        user_id=user_id,
        entry_type=entry_type,
        amount=amount,
        idempotency_key=idempotency_key,
        reference_id=reference_id,
        reason=reason,
    )
    return True


def grant_signup_bonus(session: Session, user_id: str, *, amount: int = 100) -> bool:
    """在注册所在事务中幂等赠送默认创作点。"""

    if amount <= 0:
        raise ValueError("amount must be positive")
    return _apply_credit(
        session,
        user_id=user_id,
        entry_type="signup_bonus",
        amount=amount,
        idempotency_key=f"signup:{user_id}",
        reference_id=user_id,
        reason="signup_bonus",
    )


class BillingService:
    """按账户行锁串行化余额变更，所有结果只通过追加流水表达。"""

    def __init__(self, session_factory: SessionFactory) -> None:
        self.session_factory = session_factory

    def grant(
        self, user_id: str, amount: int, *, reason: str, idempotency_key: str
    ) -> bool:
        """运维充值；同一个业务幂等键只会增加一次余额。"""

        if amount <= 0:
            raise ValueError("amount must be positive")
        if not reason:
            raise ValueError("reason must not be empty")
        with self.session_factory() as session:
            with session.begin():
                return _apply_credit(
                    session,
                    user_id=user_id,
                    entry_type="operator_grant",
                    amount=amount,
                    idempotency_key=idempotency_key,
                    reference_id=None,
                    reason=reason,
                )

    def charge_project(self, user_id: str, project_id: str, amount: int) -> bool:
        """为项目创建扣费流水；重试同一项目不重复扣费。"""

        if amount <= 0:
            raise ValueError("amount must be positive")
        if not project_id:
            raise ValueError("project_id must not be empty")
        with self.session_factory() as session:
            with session.begin():
                return _apply_credit(
                    session,
                    user_id=user_id,
                    entry_type="charge",
                    amount=-amount,
                    idempotency_key=f"charge:{project_id}",
                    reference_id=project_id,
                    reason="project_charge",
                )

    def refund_failed_project(self, project_id: str) -> bool:
        """仅为既有项目扣费追加一次等额反向流水。"""

        if not project_id:
            raise ValueError("project_id must not be empty")
        with self.session_factory() as session:
            with session.begin():
                charge = session.scalar(
                    select(CreditLedger)
                    .where(
                        CreditLedger.reference_id == project_id,
                        CreditLedger.entry_type == "charge",
                    )
                    .with_for_update()
                )
                if charge is None:
                    raise ChargeNotFoundError("project charge not found")
                return _apply_credit(
                    session,
                    user_id=charge.user_id,
                    entry_type="refund",
                    amount=-charge.amount,
                    idempotency_key=f"refund:{project_id}",
                    reference_id=project_id,
                    reason="project_failed_refund",
                )

    def balance(self, user_id: str) -> int:
        """读取当前余额；不存在的账户视为零。"""

        with self.session_factory() as session:
            account = session.get(CreditAccount, user_id)
            return 0 if account is None else account.balance
