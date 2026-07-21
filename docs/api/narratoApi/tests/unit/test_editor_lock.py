from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from narrato_api.auth.models import User
from narrato_api.database import Base
from narrato_api.editor.models import EditorRevision
from narrato_api.editor.service import EditorLockedError
from narrato_api.projects.models import Project
from narrato_api.workflows.models import (
    Workflow,
    WorkflowOutbox,
    WorkflowTemplateSnapshot,
)


def _editor_service():
    from narrato_api.editor.service import EditorService

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    with sessions.begin() as session:
        session.add(
            User(id="usr_editor", email="editor@example.com", password_hash="hash")
        )
        session.add(
            Project(
                id="prj_editor",
                user_id="usr_editor",
                product="short_drama",
                status="waiting_for_edit",
                created_at=datetime(2000, 1, 1, tzinfo=timezone.utc),
            )
        )
        session.add(
            WorkflowTemplateSnapshot(
                id="tpl_editor",
                template_name="short_drama_narration",
                version="v1",
                definition={"nodes": [{"name": "waiting_for_edit"}]},
            )
        )
        session.add(
            Workflow(
                id="wfl_editor",
                user_id="usr_editor",
                project_id="prj_editor",
                template_snapshot_id="tpl_editor",
                state="waiting_for_edit",
            )
        )
    return EditorService(sessions), sessions


def test_waiting_for_edit_stays_editable_without_an_expiration_path() -> None:
    service, sessions = _editor_service()

    revision_id = service.save_draft(
        user_id="usr_editor", project_id="prj_editor", content={"tracks": []}
    )

    with sessions() as session:
        project = session.get(Project, "prj_editor")
    assert revision_id.startswith("edr_")
    assert project is not None and (project.status, project.is_locked) == (
        "waiting_for_edit",
        False,
    )


def test_submit_render_locks_editor_and_persists_one_outbox_event() -> None:
    service, sessions = _editor_service()
    service.save_draft(
        user_id="usr_editor", project_id="prj_editor", content={"tracks": ["final"]}
    )

    assert service.submit_render(
        user_id="usr_editor",
        project_id="prj_editor",
        idempotency_key="render-submit:prj_editor:one",
    )

    with sessions() as session:
        project = session.get(Project, "prj_editor")
        workflow = session.get(Workflow, "wfl_editor")
        events = session.scalars(
            select(WorkflowOutbox).where(WorkflowOutbox.workflow_id == "wfl_editor")
        ).all()
        revisions = session.scalars(
            select(EditorRevision).where(EditorRevision.project_id == "prj_editor")
        ).all()

    assert project is not None and (project.status, project.is_locked) == (
        "render_queued",
        True,
    )
    assert workflow is not None and workflow.state == "render_queued"
    assert [
        (event.event_type, event.idempotency_key, event.status) for event in events
    ] == [("workflow.render_requested", "render-submit:prj_editor:one", "pending")]
    assert [revision.content for revision in revisions] == [{"tracks": ["final"]}]

    with pytest.raises(EditorLockedError):
        service.save_draft(
            user_id="usr_editor", project_id="prj_editor", content={"tracks": []}
        )
