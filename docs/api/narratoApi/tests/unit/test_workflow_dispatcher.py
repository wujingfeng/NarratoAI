from __future__ import annotations

from datetime import timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from narrato_api.auth.models import User
from narrato_api.database import Base
from narrato_api.projects.models import Project
from narrato_api.workflows.dispatcher import WorkflowOutboxDispatcher
from narrato_api.workflows.models import Workflow, WorkflowOutbox, WorkflowTemplateSnapshot, utc_now


def _dispatcher() -> tuple[WorkflowOutboxDispatcher, sessionmaker, str]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    event_id = "wob_dispatch"
    with sessions.begin() as session:
        session.add(User(id="usr_dispatch", email="dispatch@example.com", password_hash="hash"))
        session.add(Project(id="prj_dispatch", user_id="usr_dispatch", product="short_drama", status="queued"))
        session.add(
            WorkflowTemplateSnapshot(
                id="tpl_dispatch",
                template_name="short_drama_narration",
                version="v1",
                definition={"nodes": [{"name": "media_probe"}]},
            )
        )
        session.add(
            Workflow(
                id="wfl_dispatch",
                user_id="usr_dispatch",
                project_id="prj_dispatch",
                template_snapshot_id="tpl_dispatch",
                state="queued",
            )
        )
        session.add(
            WorkflowOutbox(
                id=event_id,
                workflow_id="wfl_dispatch",
                event_type="workflow.state_changed",
                idempotency_key="workflow-state:queued:dispatch",
                payload={"state": "queued"},
                available_at=utc_now() - timedelta(seconds=1),
            )
        )
    return WorkflowOutboxDispatcher(sessions), sessions, event_id


def test_pending_event_is_claimed_once_and_woken_with_its_stable_idempotency_key() -> None:
    dispatcher, sessions, event_id = _dispatcher()
    wakes: list[tuple[str, str]] = []

    def wake_up(claimed_event_id: str, idempotency_key: str) -> None:
        wakes.append((claimed_event_id, idempotency_key))

    assert dispatcher.dispatch(event_id, wake_up)
    assert not dispatcher.dispatch(event_id, wake_up)
    assert wakes == [(event_id, "workflow-state:queued:dispatch")]

    with sessions() as session:
        event = session.get(WorkflowOutbox, event_id)
    assert event is not None and (event.status, event.attempt_count, event.sent_at is not None) == (
        "sent",
        1,
        True,
    )


def test_wake_failure_returns_claimed_event_to_durable_retryable_state() -> None:
    dispatcher, sessions, event_id = _dispatcher()

    def wake_up(_event_id: str, _idempotency_key: str) -> None:
        raise RuntimeError("broker unavailable")

    assert not dispatcher.dispatch(event_id, wake_up)

    with sessions() as session:
        event = session.get(WorkflowOutbox, event_id)
    assert event is not None and (event.status, event.attempt_count, event.sent_at) == (
        "pending",
        1,
        None,
    )
