from __future__ import annotations

import json

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from narrato_api.assets.models import Asset
from narrato_api.auth.models import User
from narrato_api.database import Base
from narrato_api.editor.models import EditorDraft, EditorRevision
from narrato_api.integrations.core_client import HttpCoreClient
from narrato_api.projects.models import Project, ProjectNarrationSettings
from narrato_api.workflows.models import (
    Workflow,
    WorkflowNode,
    WorkflowNodeAttempt,
    WorkflowOutbox,
    WorkflowTemplateSnapshot,
)
from narrato_api.workflows.dispatcher import WorkflowOutboxDispatcher
from narrato_api.workflows.orchestrator import WorkflowOrchestrator
from narrato_api.workflows.reconciler import WorkflowReconciler


class FakeCore:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self.analysis_sources: list[dict[str, object]] = []
        self.analysis_configs: list[dict[str, object]] = []
        self.script_configs: list[dict[str, object]] = []

    def submit_asr(self, *, caller_task_id: str, **_kwargs: object) -> str:
        self.calls.append(("asr", caller_task_id))
        return f"core:{caller_task_id}"

    def submit_asr_batch(
        self, *, caller_task_id: str, sources: list[dict[str, object]]
    ) -> str:
        self.calls.append(("asr", caller_task_id))
        assert all(item.get("source_asset_id") for item in sources)
        return f"core:{caller_task_id}"

    def submit_video_analysis(
        self,
        *,
        caller_task_id: str,
        config_snapshot: dict[str, object],
        sources: list[dict[str, object]],
        model_id: str,
        **_kwargs: object,
    ) -> str:
        self.calls.append(("qwen", caller_task_id))
        self.analysis_sources.extend(sources)
        self.analysis_configs.append(config_snapshot)
        assert model_id == "model_qwen_plus"
        return f"core:{caller_task_id}"

    def submit_script_generation(
        self,
        *,
        caller_task_id: str,
        analysis_artifact: dict[str, object],
        sources: list[dict[str, object]],
        model_id: str,
        config_snapshot: dict[str, object],
        **_kwargs: object,
    ) -> str:
        self.calls.append(("script", caller_task_id))
        self.script_configs.append(config_snapshot)
        assert model_id == "model_qwen_plus"
        assert analysis_artifact == {
            "artifact_id": "art_analysis",
            "url": "https://cdn.example/analysis.json",
        }
        assert [item["source_asset_id"] for item in sources] == ["ast2", "ast"]
        assert [item["duration_seconds"] for item in sources] == [20, 10]
        return f"core:{caller_task_id}"


def test_analysis_nodes_are_dispatched_in_dependency_order_and_replay_is_idempotent() -> (
    None
):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    names = (
        "subtitle_recognition",
        "plot_structure",
        "conflict_highlights",
        "highlight_scoring",
        "script_generation",
    )
    with sessions.begin() as session:
        session.add(User(id="usr", email="a@example.com", password_hash="hash"))
        session.add(
            Project(
                id="prj",
                user_id="usr",
                product="short_drama_narration",
                status="queued",
                current_stage="analysis",
            )
        )
        session.add(
            Asset(
                id="ast",
                user_id="usr",
                project_id="prj",
                asset_type="video",
                status="ready",
                filename="episode.mp4",
                bucket="b",
                object_key="o",
                cdn_url="https://cdn.example/episode.mp4",
                size_bytes=1,
                duration_seconds=10,
                sort_order=1,
            )
        )
        session.add(
            Asset(
                id="ast2",
                user_id="usr",
                project_id="prj",
                asset_type="video",
                status="ready",
                filename="episode-2.mp4",
                bucket="b",
                object_key="o2",
                cdn_url="https://cdn.example/episode-2.mp4",
                size_bytes=1,
                duration_seconds=20,
                sort_order=0,
            )
        )
        session.add(
            ProjectNarrationSettings(project_id="prj", settings={"voice_id": "v"})
        )
        session.add(
            WorkflowTemplateSnapshot(
                id="tpl",
                template_name="short_drama_narration",
                version="v1",
                definition={"nodes": []},
            )
        )
        session.add(
            Workflow(
                id="wfl",
                user_id="usr",
                project_id="prj",
                template_snapshot_id="tpl",
                state="queued",
            )
        )
        for index, name in enumerate(names):
            session.add(
                WorkflowNode(
                    id=f"node{index}",
                    workflow_id="wfl",
                    name=name,
                    depends_on=[] if not index else [names[index - 1]],
                )
            )

    core = FakeCore()
    orchestrator = WorkflowOrchestrator(sessions)
    reconciler = WorkflowReconciler(sessions)
    assert orchestrator.dispatch_ready(workflow_id="wfl", core_client=core)  # type: ignore[arg-type]
    for index, name in enumerate(names):
        with sessions() as session:
            attempt = session.scalar(
                select(WorkflowNodeAttempt)
                .join(WorkflowNode)
                .where(
                    WorkflowNode.name == name,
                    WorkflowNodeAttempt.state == "running",
                )
            )
        assert attempt is not None
        result: dict[str, object] = {}
        if name == "subtitle_recognition":
            result = {
                "subtitles": [
                    {
                        "source_asset_id": "ast",
                        "artifact": {
                            "artifact_id": "art_subtitle",
                            "url": "https://cdn.example/narrato/coreApi/subtitle.srt",
                        },
                    },
                    {
                        "source_asset_id": "ast2",
                        "artifact": {
                            "artifact_id": "art_subtitle_2",
                            "url": "https://cdn.example/narrato/coreApi/subtitle-2.srt",
                        },
                    },
                ]
            }
        elif name == "highlight_scoring":
            result = {
                "artifacts": [
                    {
                        "artifact_id": "art_analysis",
                        "kind": "analysis",
                        "url": "https://cdn.example/analysis.json",
                    }
                ]
            }
        assert reconciler.reconcile_polling(
            core_task_id=attempt.core_task_id or "",
            event_id=f"event:{index}",
            state_version=1,
            state="succeeded",
            result=result,
        )
        if index < len(names) - 1:
            with sessions() as session:
                outbox_id = session.scalar(
                    select(WorkflowOutbox.id)
                    .where(
                        WorkflowOutbox.workflow_id == "wfl",
                        WorkflowOutbox.status == "pending",
                    )
                    .order_by(WorkflowOutbox.created_at.desc())
                )
            assert outbox_id is not None
            assert WorkflowOutboxDispatcher(sessions).dispatch(
                outbox_id,
                lambda _event_id, _idempotency_key: orchestrator.dispatch_ready(
                    workflow_id="wfl",
                    core_client=core,  # type: ignore[arg-type]
                ),
            )

    assert [kind for kind, _ in core.calls] == ["asr", "qwen", "qwen", "qwen", "script"]
    assert (
        core.analysis_sources
        == [
            {
                "source_asset_id": "ast2",
                "video_url": "https://cdn.example/episode-2.mp4",
                "video_name": "episode-2.mp4",
                "subtitle_name": "episode-2.srt",
                "duration_seconds": 20,
                "subtitle_artifact": {
                    "artifact_id": "art_subtitle_2",
                    "url": "https://cdn.example/narrato/coreApi/subtitle-2.srt",
                },
            },
            {
                "source_asset_id": "ast",
                "video_url": "https://cdn.example/episode.mp4",
                "video_name": "episode.mp4",
                "subtitle_name": "episode.srt",
                "duration_seconds": 10,
                "subtitle_artifact": {
                    "artifact_id": "art_subtitle",
                    "url": "https://cdn.example/narrato/coreApi/subtitle.srt",
                },
            },
        ]
        * 3
    )
    assert (
        core.analysis_configs
        == [{"original_sound_ratio": 30, "drama_name": "episode-2"}] * 3
    )
    assert core.script_configs == [
        {"original_sound_ratio": 30, "drama_name": "episode-2"}
    ]
    with sessions() as session:
        nodes = list(session.scalars(select(WorkflowNode).order_by(WorkflowNode.name)))
        workflow = session.get(Workflow, "wfl")
    assert all(node.state == "completed" for node in nodes)
    assert workflow is not None and workflow.state == "waiting_for_edit"


def test_failed_node_cancels_its_unstarted_descendants() -> None:
    # Uses the same fixture shape as the successful flow, but a failure must not
    # ever permit the dependent Qwen nodes to be submitted.
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    with sessions.begin() as session:
        session.add(User(id="usr", email="b@example.com", password_hash="hash"))
        session.add(
            Project(
                id="prj",
                user_id="usr",
                product="short_drama_narration",
                status="queued",
                current_stage="analysis",
            )
        )
        session.add(
            WorkflowTemplateSnapshot(
                id="tpl",
                template_name="short_drama_narration",
                version="v1",
                definition={"nodes": []},
            )
        )
        session.add(
            Workflow(
                id="wfl",
                user_id="usr",
                project_id="prj",
                template_snapshot_id="tpl",
                state="queued",
            )
        )
        session.add(
            WorkflowNode(
                id="one",
                workflow_id="wfl",
                name="subtitle_recognition",
                state="running",
            )
        )
        session.add(
            WorkflowNode(
                id="two",
                workflow_id="wfl",
                name="plot_structure",
                depends_on=["subtitle_recognition"],
            )
        )
        session.add(
            WorkflowNodeAttempt(
                id="attempt",
                workflow_node_id="one",
                attempt_number=1,
                state="running",
                core_task_id="core",
            )
        )

    assert WorkflowReconciler(sessions).reconcile_callback(
        core_task_id="core",
        event_id="failed",
        state_version=1,
        state="failed",
        result={"error": "ASR"},
    )
    with sessions() as session:
        assert session.get(WorkflowNode, "two").state == "cancelled"  # type: ignore[union-attr]
        assert session.get(Workflow, "wfl").state == "failed"  # type: ignore[union-attr]


def test_auto_mode_freezes_revision_and_queues_render_after_script() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    with sessions.begin() as session:
        session.add(User(id="usr_auto", email="auto@example.com", password_hash="hash"))
        session.add(
            Project(
                id="prj_auto",
                user_id="usr_auto",
                product="short_drama_narration",
                status="analyzing",
                current_stage="analysis",
            )
        )
        session.add(
            Asset(
                id="asset_auto",
                user_id="usr_auto",
                project_id="prj_auto",
                asset_type="video",
                status="ready",
                filename="episode.mp4",
                bucket="b",
                object_key="auto-video",
                cdn_url="https://cdn.example/episode.mp4",
                size_bytes=1,
                duration_seconds=10,
            )
        )
        session.add(
            ProjectNarrationSettings(
                project_id="prj_auto",
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
                id="tpl_auto",
                template_name="short_drama_narration",
                version="v2",
                definition={"nodes": []},
            )
        )
        session.add(
            Workflow(
                id="wfl_auto",
                user_id="usr_auto",
                project_id="prj_auto",
                template_snapshot_id="tpl_auto",
                state="running",
            )
        )
        session.add_all(
            [
                WorkflowNode(
                    id="node_script_auto",
                    workflow_id="wfl_auto",
                    name="script_generation",
                    state="running",
                ),
                WorkflowNode(
                    id="node_edit_auto",
                    workflow_id="wfl_auto",
                    name="waiting_for_edit",
                    depends_on=["script_generation"],
                    manual_gate=True,
                ),
                WorkflowNode(
                    id="node_render_auto",
                    workflow_id="wfl_auto",
                    name="video_render",
                    depends_on=["waiting_for_edit"],
                ),
                WorkflowNode(
                    id="node_publish_auto",
                    workflow_id="wfl_auto",
                    name="publish_artifacts",
                    depends_on=["video_render"],
                    manual_gate=True,
                ),
            ]
        )
        session.add(
            WorkflowNodeAttempt(
                id="attempt_script_auto",
                workflow_node_id="node_script_auto",
                attempt_number=1,
                state="running",
                core_task_id="core_script_auto",
            )
        )

    assert WorkflowReconciler(sessions).reconcile_polling(
        core_task_id="core_script_auto",
        event_id="event_script_auto",
        state_version=4,
        state="succeeded",
        result={
            "result": {
                "editor_draft": {
                    "tracks": [
                        {
                            "items": [
                                {
                                    "source_asset_id": "asset_auto",
                                    "start": 1,
                                    "end": 5,
                                    "narration": "真实脚本结果",
                                }
                            ]
                        }
                    ]
                }
            }
        },
    )

    with sessions() as session:
        project = session.get(Project, "prj_auto")
        workflow = session.get(Workflow, "wfl_auto")
        draft = session.get(EditorDraft, "prj_auto")
        revisions = list(
            session.scalars(
                select(EditorRevision).where(EditorRevision.project_id == "prj_auto")
            )
        )
        render_event = session.scalar(
            select(WorkflowOutbox).where(
                WorkflowOutbox.event_type == "workflow.render_requested"
            )
        )
        edit_gate = session.get(WorkflowNode, "node_edit_auto")
    assert project is not None and (
        project.current_stage,
        project.status,
        project.is_locked,
    ) == ("generate", "render_queued", True)
    assert workflow is not None and workflow.state == "render_queued"
    assert draft is not None and len(revisions) == 1
    assert edit_gate is not None and edit_gate.state == "completed"
    assert render_event is not None
    assert render_event.payload["execution_mode"] == "auto"
    assert (
        revisions[0].content["render_snapshot"]["timeline"][0]["narration"]
        == "真实脚本结果"
    )


def test_uploaded_srt_skips_asr_and_is_sent_to_qwen() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    with sessions.begin() as session:
        session.add(User(id="usr", email="srt@example.com", password_hash="hash"))
        session.add(
            Project(
                id="prj",
                user_id="usr",
                product="short_drama_narration",
                status="queued",
                current_stage="analysis",
            )
        )
        session.add(
            Asset(
                id="video",
                user_id="usr",
                project_id="prj",
                asset_type="video",
                status="ready",
                filename="episode.mp4",
                bucket="b",
                object_key="video",
                cdn_url="https://cdn.example/episode.mp4",
                size_bytes=1,
            )
        )
        session.add(
            Asset(
                id="srt",
                user_id="usr",
                project_id="prj",
                asset_type="subtitle",
                status="ready",
                filename="episode.srt",
                bucket="b",
                object_key="subtitle",
                cdn_url="https://cdn.example/episode.srt",
                size_bytes=1,
            )
        )
        session.add(
            WorkflowTemplateSnapshot(
                id="tpl",
                template_name="short_drama_narration",
                version="v1",
                definition={"nodes": []},
            )
        )
        session.add(
            Workflow(
                id="wfl",
                user_id="usr",
                project_id="prj",
                template_snapshot_id="tpl",
                state="queued",
            )
        )
        session.add(
            WorkflowNode(id="asr", workflow_id="wfl", name="subtitle_recognition")
        )
        session.add(
            WorkflowNode(
                id="plot",
                workflow_id="wfl",
                name="plot_structure",
                depends_on=["subtitle_recognition"],
            )
        )

    core = FakeCore()
    orchestrator = WorkflowOrchestrator(sessions)
    assert orchestrator.dispatch_ready(workflow_id="wfl", core_client=core)  # type: ignore[arg-type]
    assert core.calls == []
    with sessions() as session:
        asr = session.get(WorkflowNode, "asr")
        attempt = session.scalar(
            select(WorkflowNodeAttempt).where(
                WorkflowNodeAttempt.workflow_node_id == "asr"
            )
        )
    assert asr is not None and asr.state == "completed"
    assert attempt is not None and attempt.result == {
        "subtitles": [
            {
                "source_asset_id": "video",
                "subtitle_url": "https://cdn.example/episode.srt",
                "asset_id": "srt",
            }
        ]
    }

    assert orchestrator.dispatch_ready(workflow_id="wfl", core_client=core)  # type: ignore[arg-type]
    assert len(core.calls) == 1 and core.calls[0][0] == "qwen"
    assert core.analysis_sources == [
        {
            "source_asset_id": "video",
            "video_url": "https://cdn.example/episode.mp4",
            "video_name": "episode.mp4",
            "subtitle_name": "episode.srt",
            "subtitle_url": "https://cdn.example/episode.srt",
        }
    ]
    assert core.analysis_configs == [
        {"original_sound_ratio": 30, "drama_name": "episode"}
    ]


def test_qwen_client_emits_core_video_analysis_source_contract(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class Response:
        status = 202

        def read(self) -> bytes:
            return b'{"data":{"core_task_id":"core_qwen"}}'

        def __enter__(self):
            return self

        def __exit__(self, *_args: object) -> None:
            return None

    def fake_urlopen(request, timeout: int):
        captured["url"] = request.full_url
        captured["body"] = json.loads(request.data)
        return Response()

    monkeypatch.setattr("narrato_api.integrations.core_client.urlopen", fake_urlopen)
    client = HttpCoreClient(base_url="https://core.example.test", request_token="token")
    task_id = client.submit_video_analysis(
        model_id="model_qwen_plus",
        sources=[
            {
                "source_asset_id": "asset_1",
                "video_url": "https://cdn.example/narrato/api/video.mp4",
                "subtitle_artifact": {
                    "artifact_id": "art_1",
                    "url": "https://cdn.example/narrato/coreApi/subtitle.srt",
                },
            }
        ],
        caller_task_id="attempt_1",
        config_snapshot={"narration_style": "悬疑"},
    )
    assert task_id == "core_qwen"
    assert captured == {
        "url": "https://core.example.test/api/v1/video-analysis/tasks",
        "body": {
            "model_id": "model_qwen_plus",
            "sources": [
                {
                    "source_asset_id": "asset_1",
                    "video_url": "https://cdn.example/narrato/api/video.mp4",
                    "subtitle_artifact": {
                        "artifact_id": "art_1",
                        "url": "https://cdn.example/narrato/coreApi/subtitle.srt",
                    },
                }
            ],
            "language": "zh-CN",
            "config_snapshot": {"narration_style": "悬疑"},
            "caller_task_id": "attempt_1",
        },
    }
