from __future__ import annotations

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from narrato_api.auth.models import User
from narrato_api.database import Base
from narrato_api.editor.models import EditorDraft, EditorRevision
from narrato_api.editor.service import EditorService
from narrato_api.projects.models import Project
from narrato_api.workflows.models import Workflow, WorkflowTemplateSnapshot


def _editor_service() -> tuple[EditorService, sessionmaker]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    with sessions.begin() as session:
        session.add(User(id="usr_lww", email="lww@example.com", password_hash="hash"))
        session.add(
            Project(
                id="prj_lww",
                user_id="usr_lww",
                product="short_drama",
                status="waiting_for_edit",
            )
        )
        session.add(
            WorkflowTemplateSnapshot(
                id="tpl_lww",
                template_name="short_drama_narration",
                version="v1",
                definition={"nodes": [{"name": "waiting_for_edit"}]},
            )
        )
        session.add(
            Workflow(
                id="wfl_lww",
                user_id="usr_lww",
                project_id="prj_lww",
                template_snapshot_id="tpl_lww",
                state="waiting_for_edit",
            )
        )
    return EditorService(sessions), sessions


def test_editor_draft_keeps_only_the_last_accepted_save_until_render_submission() -> None:
    service, sessions = _editor_service()

    first_id = service.save_draft(
        user_id="usr_lww", project_id="prj_lww", content={"script": "first"}
    )
    second_id = service.save_draft(
        user_id="usr_lww", project_id="prj_lww", content={"script": "last"}
    )

    with sessions() as session:
        drafts = session.scalars(
            select(EditorDraft).where(EditorDraft.project_id == "prj_lww")
        ).all()
        revisions = session.scalars(
            select(EditorRevision).where(EditorRevision.project_id == "prj_lww")
        ).all()

    assert first_id == second_id
    assert [(draft.id, draft.content) for draft in drafts] == [
        (first_id, {"script": "last"})
    ]
    assert revisions == []
