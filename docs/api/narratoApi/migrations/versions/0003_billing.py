"""建立整数创作点账本和产品价格版本。

Revision ID: 0003_billing
Revises: 0002_users
Create Date: 2026-07-17
"""

from typing import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_billing"
down_revision: str | None = "0002_users"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """创建余额、不可变流水和历史价格表。"""

    op.create_table(
        "credit_accounts",
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("balance", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("balance >= 0", name="ck_credit_accounts_balance"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.create_table(
        "credit_ledger",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("entry_type", sa.String(length=32), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=256), nullable=False),
        sa.Column("reference_id", sa.String(length=64), nullable=True),
        sa.Column("reason", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("amount <> 0", name="ck_credit_ledger_nonzero_amount"),
        sa.CheckConstraint(
            "entry_type IN ('signup_bonus', 'operator_grant', 'charge', 'refund')",
            name="ck_credit_ledger_entry_type",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "idempotency_key", name="uq_credit_ledger_idempotency"
        ),
    )
    op.create_index("ix_credit_ledger_reference", "credit_ledger", ["reference_id"])
    op.create_table(
        "product_prices",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("product", sa.String(length=64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("credits_per_minute", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("version > 0", name="ck_product_prices_version"),
        sa.CheckConstraint(
            "credits_per_minute > 0", name="ck_product_prices_credits_per_minute"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "product", "version", name="uq_product_prices_product_version"
        ),
    )


def downgrade() -> None:
    """以依赖反序删除计费表。"""

    op.drop_table("product_prices")
    op.drop_index("ix_credit_ledger_reference", table_name="credit_ledger")
    op.drop_table("credit_ledger")
    op.drop_table("credit_accounts")
