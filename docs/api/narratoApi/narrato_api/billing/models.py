from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from narrato_api.database import Base


def utc_now() -> datetime:
    """返回带时区的 UTC 当前时间。"""

    return datetime.now(timezone.utc)


class CreditAccount(Base):
    """用户当前创作点余额；每次变更必须由账本流水驱动。"""

    __tablename__ = "credit_accounts"
    __table_args__ = (CheckConstraint("balance >= 0", name="ck_credit_accounts_balance"),)

    user_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("users.id", ondelete="RESTRICT"), primary_key=True
    )
    balance: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class CreditLedger(Base):
    """不可变创作点流水，amount 正数入账、负数扣费。"""

    __tablename__ = "credit_ledger"
    __table_args__ = (
        CheckConstraint("amount <> 0", name="ck_credit_ledger_nonzero_amount"),
        CheckConstraint(
            "entry_type IN ('signup_bonus', 'operator_grant', 'charge', 'refund')",
            name="ck_credit_ledger_entry_type",
        ),
        UniqueConstraint("user_id", "idempotency_key", name="uq_credit_ledger_idempotency"),
        Index("ix_credit_ledger_reference", "reference_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    entry_type: Mapped[str] = mapped_column(String(32), nullable=False)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(256), nullable=False)
    reference_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reason: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class ProductPrice(Base):
    """产品级整数价格版本；历史版本永不就地覆盖。"""

    __tablename__ = "product_prices"
    __table_args__ = (
        CheckConstraint("version > 0", name="ck_product_prices_version"),
        CheckConstraint(
            "credits_per_minute > 0", name="ck_product_prices_credits_per_minute"
        ),
        UniqueConstraint("product", "version", name="uq_product_prices_product_version"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    product: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    credits_per_minute: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
