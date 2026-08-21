from __future__ import annotations

import argparse
import json
import sys

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from narrato_api.auth.models import User
from narrato_api.assets.models import Asset
from narrato_api.billing.service import BillingService
from narrato_api.config import load_settings
from narrato_api.database import create_database_engine
from narrato_api.projects.models import Project  # noqa: F401 - registers Asset FK target
from narrato_api.workflows.models import Workflow, WorkflowOutbox, utc_now


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m narrato_api.cli")
    commands = parser.add_subparsers(dest="command", required=True)
    credits = commands.add_parser("credits")
    credit_commands = credits.add_subparsers(dest="credits_command", required=True)
    grant = credit_commands.add_parser("grant")
    grant.add_argument("--email", required=True)
    grant.add_argument("--amount", required=True, type=int)
    grant.add_argument("--reason", required=True)
    assets = commands.add_parser("assets")
    asset_commands = assets.add_subparsers(dest="assets_command", required=True)
    rewrite_cdn = asset_commands.add_parser("rewrite-cdn-urls")
    rewrite_cdn.add_argument(
        "--apply",
        action="store_true",
        help="actually update rows; without this flag the command is a dry run",
    )
    workflows = commands.add_parser("workflows")
    workflow_commands = workflows.add_subparsers(dest="workflows_command", required=True)
    replay = workflow_commands.add_parser("replay-outbox")
    replay.add_argument("--project-id")
    replay.add_argument("--event-type")
    replay.add_argument("--status", choices=("pending", "dead", "sent"), default="pending")
    replay.add_argument("--max-attempts", type=int, default=20)
    replay.add_argument("--limit", type=int, default=100)
    replay.add_argument("--apply", action="store_true", help="enqueue selected events; default is dry-run")
    return parser


def main(argv: list[str] | None = None) -> int:
    """执行不依赖在线支付的本地幂等运营充值。"""

    args = _parser().parse_args(argv)
    settings = load_settings()
    engine = create_database_engine(
        settings.database_url,
        settings.database_connect_timeout_seconds,
        settings.database_read_timeout_seconds,
    )
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    try:
        if args.command == "credits" and args.credits_command == "grant":
            if args.amount <= 0:
                raise ValueError("amount must be positive")
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
            print("applied" if applied else "already_applied")
            return 0

        if args.command == "assets" and args.assets_command == "rewrite-cdn-urls":
            if not settings.oss_url or not settings.cdn_public_base_url:
                raise ValueError("oss_url and cdn_public_base_url must both be configured")
            source_prefix = f"{settings.oss_url}/"
            target_prefix = f"{settings.cdn_public_base_url}/"
            with sessions.begin() as session:
                assets = list(
                    session.scalars(
                        select(Asset).where(Asset.cdn_url.startswith(source_prefix))
                    )
                )
                if args.apply:
                    for asset in assets:
                        asset.cdn_url = f"{target_prefix}{asset.cdn_url.removeprefix(source_prefix)}"
            print(f"{'updated' if args.apply else 'would_update'}={len(assets)}")
            return 0

        if args.command == "workflows" and args.workflows_command == "replay-outbox":
            if args.limit < 1 or args.limit > 1000 or args.max_attempts < 0:
                raise ValueError("limit and max-attempts are invalid")
            filters = [
                WorkflowOutbox.status == args.status,
                WorkflowOutbox.attempt_count <= args.max_attempts,
            ]
            if args.project_id:
                filters.append(WorkflowOutbox.workflow_id.in_(
                    select(Workflow.id).where(Workflow.project_id == args.project_id)
                ))
            if args.event_type:
                filters.append(WorkflowOutbox.event_type == args.event_type)
            with sessions.begin() as session:
                events = list(session.scalars(
                    select(WorkflowOutbox)
                    .where(*filters)
                    .order_by(WorkflowOutbox.created_at, WorkflowOutbox.id)
                    .limit(args.limit)
                    .with_for_update()
                ))
                audit = [{"id": item.id, "workflow_id": item.workflow_id, "event_type": item.event_type,
                          "idempotency_key": item.idempotency_key, "attempt_count": item.attempt_count,
                          "previous_status": item.status} for item in events]
                if args.apply:
                    for event in events:
                        event.status = "pending"
                        event.available_at = utc_now()
                        event.sent_at = None
            print(json.dumps({
                "mode": "applied" if args.apply else "dry_run",
                "count": len(events),
                "events": audit,
            }, ensure_ascii=False, sort_keys=True))
            return 0

        raise AssertionError("unreachable parser command")
    finally:
        engine.dispose()


if __name__ == "__main__":
    sys.exit(main())
