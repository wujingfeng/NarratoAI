from __future__ import annotations

import inspect

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from narrato_api.artifacts.models import RegisteredArtifact
from narrato_api.auth.models import User
from narrato_api.database import Base
from narrato_api.editor.models import EditorRevision
from narrato_api.integrations.core_client import CoreJianyingManifest
from narrato_api.projects.models import Project
from narrato_api.workflows.models import (
    Workflow,
    WorkflowNode,
    WorkflowNodeAttempt,
    WorkflowTemplateSnapshot,
)


def _add_project(
    session: Session, *, project_id: str, user_id: str, status: str
) -> None:
    session.add(User(id=user_id, email=f"{user_id}@example.com", password_hash="hash"))
    session.add(
        Project(
            id=project_id,
            user_id=user_id,
            product="short_drama",
            status=status,
        )
    )


def _add_complete_artifacts(session: Session, *, project_id: str) -> None:
    session.add_all(
        [
            RegisteredArtifact(
                id=f"art_{kind}",
                project_id=project_id,
                kind=kind,
                cdn_url=f"https://cdn.example.test/exports/{kind}.{extension}",
                size=1024,
                checksum="sha256:" + "a" * 64,
                content_type=content_type,
                width=1920 if kind == "video" else None,
                height=1080 if kind == "video" else None,
                duration=1.0 if kind in {"video", "voice"} else None,
            )
            for kind, extension, content_type in (
                ("video", "mp4", "video/mp4"),
                ("subtitle", "srt", "application/x-subrip"),
                ("voice", "wav", "audio/wav"),
                ("timeline", "json", "application/json"),
            )
        ]
    )


class FakeCoreClient:
    def __init__(self) -> None:
        self.kwargs: dict[str, object] | None = None

    def build_jianying_manifest(self, **kwargs: object) -> CoreJianyingManifest:
        self.kwargs = kwargs
        return CoreJianyingManifest(
            template_version="v1", package_name="draft.zip", files=()
        )


def test_build_owned_completed_project_jianying_manifest_returns_the_pure_manifest() -> (
    None
):
    from narrato_api.exports.service import (
        build_owned_completed_project_jianying_manifest,
    )

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        _add_project(
            session,
            project_id="prj_completed",
            user_id="usr_owner",
            status="completed",
        )
        _add_complete_artifacts(session, project_id="prj_completed")
        session.add(
            EditorRevision(
                id="erv_1",
                project_id="prj_completed",
                content={
                    "timeline": [
                        {
                            "source_asset_id": "ast_1",
                            "start": 0,
                            "end": 1,
                            "narration": "Hi",
                        }
                    ]
                },
            )
        )
        session.commit()

        manifest = build_owned_completed_project_jianying_manifest(
            session,
            user_id="usr_owner",
            project_id="prj_completed",
            core_client=FakeCoreClient(),
        )

    assert manifest == CoreJianyingManifest(
        template_version="v1", package_name="draft.zip", files=()
    )


def test_build_manifest_uses_final_render_snapshot_and_normalizes_artifact_metadata() -> None:
    from narrato_api.exports.service import (
        build_owned_completed_project_jianying_manifest,
    )

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    client = FakeCoreClient()

    with Session(engine) as session:
        _add_project(
            session,
            project_id="prj_completed",
            user_id="usr_owner",
            status="completed",
        )
        _add_complete_artifacts(session, project_id="prj_completed")
        video = session.get(RegisteredArtifact, "art_video")
        subtitle = session.get(RegisteredArtifact, "art_subtitle")
        assert video is not None and subtitle is not None
        video.width = video.height = None
        video.duration = None
        subtitle.content_type = "application/x-subrip; charset=utf-8"
        session.add(
            EditorRevision(
                id="erv_final",
                project_id="prj_completed",
                content={"render_snapshot": {"timeline": [{"start": 99, "end": 100}]}},
            )
        )
        session.add(
            WorkflowTemplateSnapshot(
                id="wts_1",
                template_name="short_drama",
                version="1",
                definition={},
            )
        )
        session.add(
            Workflow(
                id="wfl_1",
                user_id="usr_owner",
                project_id="prj_completed",
                template_snapshot_id="wts_1",
                state="completed",
            )
        )
        session.add(
            WorkflowNode(
                id="wnd_render",
                workflow_id="wfl_1",
                name="video_render",
                state="completed",
                depends_on=[],
            )
        )
        final_timeline = [
            {
                "source_asset_id": "ast_1",
                "start": 0.0,
                "end": 1.5,
                "narration": "最终字幕",
            }
        ]
        session.add(
            WorkflowNodeAttempt(
                id="wat_render",
                workflow_node_id="wnd_render",
                attempt_number=1,
                state="completed",
                state_version=2,
                core_task_id="ctask_render",
                result={
                    "result": {
                        "metadata": {
                            "snapshot_id": "erv_final",
                            "jianying_snapshot": {
                                "timeline": final_timeline,
                                "video": {
                                    "width": 720,
                                    "height": 1280,
                                    "duration": 1.5,
                                },
                            },
                        }
                    }
                },
            )
        )
        session.commit()

        build_owned_completed_project_jianying_manifest(
            session,
            user_id="usr_owner",
            project_id="prj_completed",
            core_client=client,
        )

    assert client.kwargs is not None
    assert client.kwargs["timeline"] == final_timeline
    resources = client.kwargs["resources"]
    assert isinstance(resources, list)
    video_resource = next(item for item in resources if item.kind == "video")
    subtitle_resource = next(item for item in resources if item.kind == "subtitle")
    assert (video_resource.width, video_resource.height, video_resource.duration) == (
        720,
        1280,
        1.5,
    )
    assert subtitle_resource.content_type == "application/x-subrip"


@pytest.mark.parametrize(
    ("user_id", "project_id", "status", "expected_code"),
    [
        ("usr_other", "prj_private", "completed", "PROJECT_RESULT_NOT_FOUND"),
        ("usr_owner", "prj_missing", None, "PROJECT_RESULT_NOT_FOUND"),
        ("usr_owner", "prj_draft", "draft", "PROJECT_RESULT_NOT_COMPLETED"),
    ],
)
def test_build_owned_completed_project_jianying_manifest_rejects_ineligible_projects(
    user_id: str, project_id: str, status: str | None, expected_code: str
) -> None:
    from narrato_api.exports.service import (
        build_owned_completed_project_jianying_manifest,
    )
    from narrato_api.projects.service import ProjectResultLookupError

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        if status is not None:
            _add_project(
                session,
                project_id=project_id,
                user_id="usr_owner",
                status=status,
            )
            session.commit()

        with pytest.raises(ProjectResultLookupError) as error:
            build_owned_completed_project_jianying_manifest(
                session,
                user_id=user_id,
                project_id=project_id,
                core_client=FakeCoreClient(),
            )

    assert error.value.code == expected_code


def test_build_owned_completed_project_jianying_manifest_has_no_external_dependencies() -> (
    None
):
    from narrato_api.exports import service

    source = inspect.getsource(service.build_owned_completed_project_jianying_manifest)
    for forbidden_dependency in (
        "zipfile",
        "httpx",
        "requests",
        "urllib",
        "open(",
        "oss",
    ):
        assert forbidden_dependency not in source
