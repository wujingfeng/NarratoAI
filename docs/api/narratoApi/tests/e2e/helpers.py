from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from narrato_api.auth.models import User
from narrato_api.database import Base
from narrato_api.projects.models import Project
from narrato_api.workflows.models import (
    Workflow,
    WorkflowNode,
    WorkflowNodeAttempt,
    WorkflowTemplateSnapshot,
)
from narrato_api.workflows.templates.short_drama_narration_v1 import (
    SHORT_DRAMA_NARRATION_TEMPLATE_V1,
)


def workflow_fixture(*, node_names: tuple[str, ...] | None = None):
    """建立含真实 ORM 关系的短剧工作流收口夹具。"""

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    definitions = SHORT_DRAMA_NARRATION_TEMPLATE_V1.nodes
    if node_names is not None:
        definitions = tuple(node for node in definitions if node.name in node_names)
    with sessions.begin() as session:
        session.add(User(id="usr_e2e", email="e2e@example.com", password_hash="hash"))
        session.add(Project(id="prj_e2e", user_id="usr_e2e", product="short_drama_narration", status="queued"))
        session.add(
            WorkflowTemplateSnapshot(
                id="tpl_e2e",
                template_name="short_drama_narration",
                version="v1",
                definition={"nodes": [{"name": node.name} for node in definitions]},
            )
        )
        session.add(
            Workflow(
                id="wfl_e2e",
                user_id="usr_e2e",
                project_id="prj_e2e",
                template_snapshot_id="tpl_e2e",
                state="queued",
            )
        )
        for index, node in enumerate(definitions, start=1):
            session.add(
                WorkflowNode(
                    id=f"wnd_e2e_{index}",
                    workflow_id="wfl_e2e",
                    name=node.name,
                    state="running",
                    depends_on=list(node.depends_on),
                    retryable=node.retryable,
                    manual_gate=node.manual_gate,
                    max_attempts=3,
                )
            )
            session.add(
                WorkflowNodeAttempt(
                    id=f"wat_e2e_{index}",
                    workflow_node_id=f"wnd_e2e_{index}",
                    attempt_number=1,
                    state="running",
                    core_task_id=f"ctask_e2e_{index}",
                )
            )
    return sessions, tuple(node.name for node in definitions)
