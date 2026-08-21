from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from narrato_api.artifacts.models import RegisteredArtifact
from narrato_api.assets.models import Asset
from narrato_api.auth.models import User
from narrato_api.database import Base
from narrato_api.editor.models import EditorRevision
from narrato_api.editor.service import EditorLockedError
from narrato_api.projects.models import Project, ProjectNarrationSettings
from narrato_api.workflows.models import (
    Workflow,
    WorkflowNode,
    WorkflowNodeAttempt,
    WorkflowOutbox,
    WorkflowTemplateSnapshot,
)
from narrato_api.workflows.reconciler import WorkflowReconciler
from narrato_api.workflows.orchestrator import WorkflowOrchestrator


class _RenderCore:
    def __init__(self) -> None:
        self.request: dict[str, object] | None = None

    def submit_video_render(self, *, caller_task_id: str, **kwargs: object) -> str:
        self.request = {"caller_task_id": caller_task_id, **kwargs}
        return f"core:{caller_task_id}"


def _render_artifacts() -> list[dict[str, object]]:
    checksum = f"sha256:{'a' * 64}"
    return [
        {
            "artifact_id": f"art_{kind}",
            "kind": kind,
            "url": f"https://cdn.example/narrato/coreApi/{kind}.{extension}",
            "content_type": content_type,
            "size": 128,
            "checksum": checksum,
        }
        for kind, extension, content_type in (
            ("video", "mp4", "video/mp4"),
            ("subtitle", "srt", "application/x-subrip"),
            ("voice", "wav", "audio/wav"),
            ("timeline", "json", "application/json"),
        )
    ]


def test_render_artifact_contract_rejects_duplicate_kind() -> None:
    artifacts = _render_artifacts()
    duplicate_video = {
        **artifacts[0],
        "artifact_id": "art_duplicate_video",
        "url": "https://cdn.example/narrato/coreApi/video-duplicate.mp4",
    }

    with pytest.raises(ValueError, match="render artifacts are incomplete"):
        WorkflowReconciler._validated_render_artifacts(
            {"artifacts": [*artifacts, duplicate_video]}
        )


def test_render_artifact_contract_merges_result_dimensions_with_public_artifacts() -> None:
    artifacts = _render_artifacts()
    detailed = [
        {
            **item,
            **(
                {"width": 1280, "height": 720, "duration": 12.5}
                if item["kind"] == "video"
                else {}
            ),
        }
        for item in artifacts
    ]

    validated = WorkflowReconciler._validated_render_artifacts(
        {"artifacts": artifacts, "result": {"artifacts": detailed}}
    )

    video = next(item for item in validated if item["kind"] == "video")
    assert video["width"] == 1280
    assert video["height"] == 720
    assert video["duration"] == 12.5


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
            Asset(
                id="ast_editor", user_id="usr_editor", project_id="prj_editor",
                asset_type="video", status="ready", filename="episode.mp4",
                bucket="b", object_key="episode", cdn_url="https://cdn.example/episode.mp4",
                size_bytes=1, duration_seconds=30,
            )
        )
        session.add(ProjectNarrationSettings(
            project_id="prj_editor",
            settings={"voice_id": "voice-1", "video_ratio": "9:16", "subtitle_style": "经典白色"},
        ))
        session.add(
            Project(
                id="prj_editor",
                user_id="usr_editor",
                product="short_drama",
                status="waiting_for_edit",
                current_stage="edit",
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
        session.add_all((
            WorkflowNode(
                id="node_edit", workflow_id="wfl_editor", name="waiting_for_edit",
                state="queued", depends_on=["script_generation"], retryable=False,
                manual_gate=True, max_attempts=1,
            ),
            WorkflowNode(
                id="node_render", workflow_id="wfl_editor", name="video_render",
                state="queued", depends_on=["waiting_for_edit"], retryable=True,
                manual_gate=False, max_attempts=3,
            ),
            WorkflowNode(
                id="node_publish", workflow_id="wfl_editor", name="publish_artifacts",
                state="queued", depends_on=["video_render"], retryable=False,
                manual_gate=True, max_attempts=1,
            ),
        ))
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
        user_id="usr_editor", project_id="prj_editor", content=_renderable_draft()
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
    assert len(revisions) == 1
    assert revisions[0].content["render_snapshot"] == {
        "voice_id": "voice-1",
        "sources": [{"source_asset_id": "ast_editor", "video_url": "https://cdn.example/episode.mp4"}],
        "timeline": [{"source_asset_id": "ast_editor", "start": 0.0, "end": 5.0, "narration": "最终解说", "subtitle": "最终解说", "original_sound": False}],
        "render_config": {
            "video_ratio": "9:16",
            "subtitle_style": "经典白色",
            "voice_volume": 100,
            "voice_rate": 1.0,
            "original_sound_volume": 0,
        },
    }

    with pytest.raises(EditorLockedError):
        service.save_draft(
            user_id="usr_editor", project_id="prj_editor", content={"tracks": []}
        )


def test_render_callback_completes_generation_and_unblocks_export() -> None:
    service, sessions = _editor_service()
    service.save_draft(
        user_id="usr_editor", project_id="prj_editor", content=_renderable_draft()
    )
    service.submit_render(
        user_id="usr_editor",
        project_id="prj_editor",
        idempotency_key="render-submit:prj_editor:callback",
    )
    with sessions() as session:
        event = session.scalar(select(WorkflowOutbox))
        attempt = session.scalar(select(WorkflowNodeAttempt))
    assert event is not None and attempt is None
    assert event.payload["revision_id"].startswith("erv_")

    core = _RenderCore()
    assert WorkflowOrchestrator(sessions).dispatch_ready(
        workflow_id="wfl_editor", core_client=core  # type: ignore[arg-type]
    )
    assert core.request is not None
    assert core.request["voice_id"] == "voice-1"
    assert core.request["render_config"] == {
        "video_ratio": "9:16",
        "subtitle_style": "经典白色",
        "voice_volume": 100,
        "voice_rate": 1.0,
        "original_sound_volume": 0,
    }
    with sessions() as session:
        attempt = session.scalar(select(WorkflowNodeAttempt))
    assert attempt is not None and attempt.core_task_id is not None

    assert WorkflowReconciler(sessions).reconcile_callback(
        core_task_id=attempt.core_task_id,
        event_id="evt_render_completed",
        state_version=1,
        state="succeeded",
        result={"artifacts": _render_artifacts()},
    )
    with sessions() as session:
        project = session.get(Project, "prj_editor")
        workflow = session.get(Workflow, "wfl_editor")
    assert project is not None and (project.current_stage, project.status) == ("export", "completed")
    assert workflow is not None and workflow.state == "completed"


def test_render_success_without_complete_artifacts_is_failed_not_exported() -> None:
    service, sessions = _editor_service()
    service.save_draft(
        user_id="usr_editor", project_id="prj_editor", content=_renderable_draft()
    )
    service.submit_render(
        user_id="usr_editor",
        project_id="prj_editor",
        idempotency_key="render-submit:prj_editor:invalid-artifacts",
    )
    core = _RenderCore()
    assert WorkflowOrchestrator(sessions).dispatch_ready(
        workflow_id="wfl_editor", core_client=core  # type: ignore[arg-type]
    )
    with sessions() as session:
        attempt = session.scalar(select(WorkflowNodeAttempt))
    assert attempt is not None and attempt.core_task_id is not None

    video_only = _render_artifacts()[:1]
    assert WorkflowReconciler(sessions).reconcile_callback(
        core_task_id=attempt.core_task_id,
        event_id="evt_render_missing_artifacts",
        state_version=1,
        state="succeeded",
        result={"artifacts": video_only},
    )

    with sessions() as session:
        project = session.get(Project, "prj_editor")
        workflow = session.get(Workflow, "wfl_editor")
        persisted_attempt = session.get(WorkflowNodeAttempt, attempt.id)
        artifacts = list(session.scalars(select(RegisteredArtifact)))
    assert project is not None and (project.current_stage, project.status) == (
        "generate",
        "failed",
    )
    assert workflow is not None and workflow.state == "failed"
    assert persisted_attempt is not None and persisted_attempt.state == "failed"
    assert persisted_attempt.result == {
        "error": {
            "code": "RENDER_ARTIFACT_CONTRACT_INVALID",
            "retryable": False,
        }
    }
    assert artifacts == []


def _renderable_draft() -> dict[str, object]:
    return {
        "clips": [
            {"id": "video-1", "track_id": "video", "start": 0, "duration": 5, "source_start": 0, "asset_id": "ast_editor", "region_id": "r1"},
            {"id": "script-1", "track_id": "script", "start": 0, "duration": 5, "text": "最终解说", "region_id": "r1"},
        ],
        "subtitles": [],
        "settings": {"voice_role": "voice-1"},
    }
