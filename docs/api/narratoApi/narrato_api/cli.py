from __future__ import annotations

import argparse
import sys

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from narrato_api.auth.models import User
from narrato_api.billing.service import BillingService
from narrato_api.config import load_settings
from narrato_api.database import create_database_engine


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m narrato_api.cli")
    commands = parser.add_subparsers(dest="command", required=True)
    credits = commands.add_parser("credits")
    credit_commands = credits.add_subparsers(dest="credits_command", required=True)
    grant = credit_commands.add_parser("grant")
    grant.add_argument("--email", required=True)
    grant.add_argument("--amount", required=True, type=int)
    grant.add_argument("--reason", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    """执行不依赖在线支付的本地幂等运营充值。"""

    args = _parser().parse_args(argv)
    if args.command != "credits" or args.credits_command != "grant":
        raise AssertionError("unreachable parser command")
    if args.amount <= 0:
        raise ValueError("amount must be positive")
    settings = load_settings()
    engine = create_database_engine(
        settings.database_url,
        settings.database_connect_timeout_seconds,
        settings.database_read_timeout_seconds,
    )
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    try:
        with sessions() as session:
            user = session.scalar(
                select(User).where(User.email == args.email.strip().lower())
            )
            if user is None:
                raise ValueError("user not found")
            user_id = user.id
        applied = BillingService(sessions).grant(
            user_id,
            args.amount,
            reason=args.reason,
            idempotency_key=f"operator_grant:{args.email.strip().lower()}:{args.amount}:{args.reason}",
        )
    finally:
        engine.dispose()
    print("applied" if applied else "already_applied")
    return 0


if __name__ == "__main__":
    sys.exit(main())
