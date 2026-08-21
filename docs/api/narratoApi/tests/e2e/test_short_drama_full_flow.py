from __future__ import annotations

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from narrato_api.artifacts.models import RegisteredArtifact
from narrato_api.assets.models import Asset
from narrato_api.auth.models import User
from narrato_api.database import Base
from narrato_api.editor.models import EditorDraft, EditorRevision
from narrato_api.projects.models import Project, ProjectNarrationSettings
from narrato_api.projects.service import lookup_completed_project_result
from narrato_api.workflows.dispatcher import WorkflowOutboxDispatcher
from narrato_api.workflows.models import (
    Workflow,
    WorkflowNode,
    WorkflowNodeAttempt,
    WorkflowOutbox,
    WorkflowTemplateSnapshot,
)
from narrato_api.workflows.orchestrator import WorkflowOrchestrator
from narrato_api.workflows.reconciler import WorkflowReconciler


class RecordingRenderCore:
    def __init__(self) -> None:
        self.request: dict[str, object] | None = None

    def submit_video_render(
        self, *, caller_task_id: str, **kwargs: object
    ) -> str:
        self.request = {"caller_task_id": caller_task_id, **kwargs}
        return f"core-render:{caller_task_id}"


def _sessions():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    with sessions.begin() as session:
        session.add(
            User(id="usr_e2e", email="e2e@example.com", password_hash="hash")
        )
        session.add(
            Project(
                id="prj_e2e",
                user_id="usr_e2e",
                product="short_drama_narration",
                status="analyzing",
                current_stage="analysis",
            )
        )
        session.add(
            Asset(
                id="asset_e2e",
                user_id="usr_e2e",
                project_id="prj_e2e",
                asset_type="video",
                status="ready",
                filename="episode.mp4",
                bucket="test",
                object_key="episode.mp4",
                cdn_url="https://cdn.example.test/source/episode.mp4",
                size_bytes=1024,
                duration_seconds=12,
            )
        )
        session.add(
            ProjectNarrationSettings(
                project_id="prj_e2e",
                settings={
                    "narration_style": "悬疑/犯罪",
                    "video_ratio": "9:16",
                    "voice_id": "voice_real",
                    "subtitle_style": "经典白色",
                    "execution_mode": "auto",
                },
            )
        )
        session.add(
            WorkflowTemplateSnapshot(
                id="tpl_e2e",
                template_name="short_drama_narration",
                version="v2",
                definition={"nodes": []},
            )
        )
        session.add(
            Workflow(
                id="wfl_e2e",
                user_id="usr_e2e",
                project_id="prj_e2e",
                template_snapshot_id="tpl_e2e",
                state="running",
            )
        )
        session.add_all(
            (
                WorkflowNode(
                    id="node_script_e2e",
                    workflow_id="wfl_e2e",
                    name="script_generation",
                    state="running",
                ),
                WorkflowNode(
                    id="node_edit_e2e",
                    workflow_id="wfl_e2e",
                    name="waiting_for_edit",
                    state="queued",
                    depends_on=["script_generation"],
                    retryable=False,
                    manual_gate=True,
                    max_attempts=1,
                ),
                WorkflowNode(
                    id="node_render_e2e",
                    workflow_id="wfl_e2e",
                    name="video_render",
                    state="queued",
                    depends_on=["waiting_for_edit"],
                    retryable=True,
                    manual_gate=False,
                    max_attempts=3,
                ),
                WorkflowNode(
                    id="node_publish_e2e",
                    workflow_id="wfl_e2e",
                    name="publish_artifacts",
                    state="queued",
                    depends_on=["video_render"],
                    retryable=False,
                    manual_gate=True,
                    max_attempts=1,
                ),
            )
        )
        session.add(
            WorkflowNodeAttempt(
                id="attempt_script_e2e",
                workflow_node_id="node_script_e2e",
                attempt_number=1,
                state="running",
                core_task_id="core-script-e2e",
            )
        )
    return sessions


def _script_result() -> dict[str, object]:
    return {
        "result": {
            "editor_draft": {
                "tracks": [
                    {
                        "items": [
                            {
                                "source_asset_id": "asset_e2e",
                                "start": 1,
                                "end": 7,
                                "narration": "这是来自脚本任务的真实解说结果。",
                            }
                        ]
                    }
                ]
            }
        }
    }


def _render_artifacts() -> list[dict[str, object]]:
    checksum = f"sha256:{'a' * 64}"
    return [
        {
            "artifact_id": f"artifact_e2e_{kind}",
            "kind": kind,
            "url": f"https://cdn.example.test/results/{kind}.{extension}",
            "content_type": content_type,
            "size": 4096,
            "checksum": checksum,
        }
        for kind, extension, content_type in (
            ("video", "mp4", "video/mp4"),
            ("subtitle", "srt", "application/x-subrip"),
            ("voice", "wav", "audio/wav"),
            ("timeline", "json", "application/json"),
        )
    ]


def test_script_revision_render_artifact_closes_real_auto_mode_flow() -> None:
    sessions = _sessions()
    reconciler = WorkflowReconciler(sessions)

    assert reconciler.reconcile_callback(
        core_task_id="core-script-e2e",
        event_id="event-script-e2e",
        state_version=1,
        state="succeeded",
        result=_script_result(),
    )

    with sessions() as session:
        draft = session.get(EditorDraft, "prj_e2e")
        revision = session.scalar(
            select(EditorRevision).where(EditorRevision.project_id == "prj_e2e")
        )
        render_event = session.scalar(
            select(WorkflowOutbox).where(
                WorkflowOutbox.event_type == "workflow.render_requested"
            )
        )
    assert draft is not None
    assert revision is not None
    assert render_event is not None
    assert render_event.payload["revision_id"] == revision.id
    assert render_event.payload["execution_mode"] == "auto"
    snapshot = revision.content["render_snapshot"]
    assert snapshot["timeline"][0]["narration"] == "这是来自脚本任务的真实解说结果。"

    core = RecordingRenderCore()
    orchestrator = WorkflowOrchestrator(sessions)
    assert WorkflowOutboxDispatcher(sessions).dispatch(
        render_event.id,
        lambda _event_id, _idempotency_key: orchestrator.dispatch_ready(
            workflow_id="wfl_e2e", core_client=core  # type: ignore[arg-type]
        ),
    )
    assert core.request is not None
    assert core.request["snapshot_id"] == revision.id
    assert core.request["voice_id"] == "voice_real"
    assert core.request["timeline"] == snapshot["timeline"]

    with sessions() as session:
        render_attempt = session.scalar(
            select(WorkflowNodeAttempt)
            .join(WorkflowNode)
            .where(WorkflowNode.name == "video_render")
        )
    assert render_attempt is not None and render_attempt.core_task_id is not None

    assert reconciler.reconcile_polling(
        core_task_id=render_attempt.core_task_id,
        event_id="event-render-e2e",
        state_version=1,
        state="succeeded",
        result={"artifacts": _render_artifacts()},
    )

    with sessions() as session:
        project = session.get(Project, "prj_e2e")
        workflow = session.get(Workflow, "wfl_e2e")
        nodes = list(
            session.scalars(
                select(WorkflowNode).where(WorkflowNode.workflow_id == "wfl_e2e")
            )
        )
        artifacts = list(
            session.scalars(
                select(RegisteredArtifact).where(
                    RegisteredArtifact.project_id == "prj_e2e"
                )
            )
        )
        result = lookup_completed_project_result(
            session, user_id="usr_e2e", project_id="prj_e2e"
        )
    assert project is not None and (
        project.current_stage,
        project.status,
        project.is_locked,
    ) == ("export", "completed", True)
    assert workflow is not None and workflow.state == "completed"
    assert all(node.state == "completed" for node in nodes)
    assert {artifact.kind for artifact in artifacts} == {
        "video",
        "subtitle",
        "voice",
        "timeline",
    }
    assert {artifact.id for artifact in result.artifacts} == {
        artifact.id for artifact in artifacts
    }


def test_invalid_script_success_cannot_create_revision_or_artifacts() -> None:
    sessions = _sessions()
    assert WorkflowReconciler(sessions).reconcile_callback(
        core_task_id="core-script-e2e",
        event_id="event-invalid-script-e2e",
        state_version=1,
        state="succeeded",
        result={"result": {"editor_draft": {"tracks": []}}},
    )

    with sessions() as session:
        project = session.get(Project, "prj_e2e")
        workflow = session.get(Workflow, "wfl_e2e")
        script_attempt = session.get(WorkflowNodeAttempt, "attempt_script_e2e")
        draft = session.get(EditorDraft, "prj_e2e")
        revisions = list(session.scalars(select(EditorRevision)))
        artifacts = list(session.scalars(select(RegisteredArtifact)))
        render_events = list(
            session.scalars(
                select(WorkflowOutbox).where(
                    WorkflowOutbox.event_type == "workflow.render_requested"
                )
            )
        )
    assert project is not None and project.status == "failed"
    assert workflow is not None and workflow.state == "failed"
    assert script_attempt is not None and script_attempt.result == {
        "error": {
            "code": "PROJECT_SCRIPT_UNAVAILABLE",
            "retryable": False,
        }
    }
    assert draft is None
    assert revisions == []
    assert render_events == []
    assert artifacts == []
