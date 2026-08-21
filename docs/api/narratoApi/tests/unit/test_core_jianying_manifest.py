from __future__ import annotations

import json
from contextlib import contextmanager
from hashlib import sha256

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from narrato_api.artifacts.models import RegisteredArtifact
from narrato_api.auth.models import User
from narrato_api.database import Base
from narrato_api.editor.models import EditorRevision
from narrato_api.projects.models import Project


def _complete_artifacts(project_id: str) -> list[RegisteredArtifact]:
    return [
        RegisteredArtifact(
            id=f"art_{kind}",
            project_id=project_id,
            kind=kind,
            cdn_url=f"https://cdn.example.test/final.{extension}",
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


class FakeResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self.status = 200
        self._payload = payload

    def read(self) -> bytes:
        return json.dumps(self._payload).encode()

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *_args: object) -> None:
        return None


def test_core_client_posts_typed_jianying_manifest_request(monkeypatch) -> None:
    from narrato_api.integrations.core_client import (
        CoreJianyingResource,
        HttpCoreClient,
    )

    requests = []

    @contextmanager
    def fake_urlopen(request, timeout: int):
        requests.append(request)
        yield FakeResponse(
            {
                "data": {
                    "template_version": "v1",
                    "package_name": "NarratoAI_erv_2.zip",
                    "files": [
                        {
                            "zip_path": "draft_content.json",
                            "content": "{}",
                            "content_base64": None,
                            "url": None,
                            "size": None,
                            "checksum": None,
                            "content_type": "application/json",
                        }
                    ],
                }
            }
        )

    monkeypatch.setattr("narrato_api.integrations.core_client.urlopen", fake_urlopen)
    client = HttpCoreClient(base_url="https://core.example.test", request_token="token")
    manifest = client.build_jianying_manifest(
        snapshot_id="erv_2",
        timeline=[
            {"source_asset_id": "ast_1", "start": 0, "end": 1, "narration": "Hi"}
        ],
        resources=[
            CoreJianyingResource(
                kind="video",
                zip_path="video/final.mp4",
                url="https://cdn.example.test/final.mp4",
                size=1024,
                checksum="sha256:" + "a" * 64,
                content_type="video/mp4",
                width=1920,
                height=1080,
                duration=1.0,
            )
        ],
    )

    assert manifest.template_version == "v1"
    assert manifest.files[0].zip_path == "draft_content.json"
    assert requests[0].full_url.endswith("/api/v1/jianying/manifests/build")
    assert json.loads(requests[0].data) == {
        "snapshot_id": "erv_2",
        "timeline": [
            {"source_asset_id": "ast_1", "start": 0, "end": 1, "narration": "Hi"}
        ],
        "resources": [
            {
                "kind": "video",
                "zip_path": "video/final.mp4",
                "url": "https://cdn.example.test/final.mp4",
                "size": 1024,
                "checksum": "sha256:" + "a" * 64,
                "content_type": "video/mp4",
                "width": 1920,
                "height": 1080,
                "duration": 1.0,
            }
        ],
    }


def test_owned_completed_project_manifest_uses_latest_revision_and_core_resources() -> (
    None
):
    from narrato_api.exports.service import (
        build_owned_completed_project_jianying_manifest,
    )

    class FakeCoreClient:
        def __init__(self) -> None:
            self.request: dict[str, object] | None = None

        def build_jianying_manifest(self, **kwargs: object) -> dict[str, object]:
            self.request = kwargs
            return {"template_version": "v1", "package_name": "draft.zip", "files": []}

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    core = FakeCoreClient()
    with Session(engine) as session:
        session.add(User(id="usr_1", email="owner@example.com", password_hash="hash"))
        session.add(
            Project(
                id="prj_1", user_id="usr_1", product="short_drama", status="completed"
            )
        )
        session.add_all(
            [
                EditorRevision(
                    id="erv_1", project_id="prj_1", content={"timeline": []}
                ),
                EditorRevision(
                    id="erv_2",
                    project_id="prj_1",
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
                ),
                *_complete_artifacts("prj_1"),
            ]
        )
        session.commit()

        manifest = build_owned_completed_project_jianying_manifest(
            session, user_id="usr_1", project_id="prj_1", core_client=core
        )

    assert manifest == {
        "template_version": "v1",
        "package_name": "draft.zip",
        "files": [],
    }
    assert core.request is not None
    assert core.request["snapshot_id"] == "erv_2"
    assert core.request["timeline"] == [
        {"source_asset_id": "ast_1", "start": 0, "end": 1, "narration": "Hi"}
    ]
    assert len(core.request["resources"]) == 4
    resource = next(
        item for item in core.request["resources"] if item.kind == "video"
    )
    assert resource.kind == "video"
    artifact_digest = sha256(b"art_video").hexdigest()[:32]
    assert resource.zip_path == f"assets/video/{artifact_digest}.mp4"
    assert resource.url == "https://cdn.example.test/final.mp4"
    assert (resource.size, resource.checksum, resource.content_type) == (
        1024,
        "sha256:" + "a" * 64,
        "video/mp4",
    )
    assert (resource.width, resource.height, resource.duration) == (1920, 1080, 1.0)


def test_owned_completed_project_manifest_rejects_missing_revision() -> None:
    from narrato_api.exports.service import (
        JianyingManifestSnapshotNotFoundError,
        build_owned_completed_project_jianying_manifest,
    )

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(User(id="usr_1", email="owner@example.com", password_hash="hash"))
        session.add(
            Project(
                id="prj_1", user_id="usr_1", product="short_drama", status="completed"
            )
        )
        session.add_all(_complete_artifacts("prj_1"))
        session.commit()

        with pytest.raises(JianyingManifestSnapshotNotFoundError) as error:
            build_owned_completed_project_jianying_manifest(
                session, user_id="usr_1", project_id="prj_1", core_client=object()
            )

    assert error.value.code == "JIANYING_SNAPSHOT_NOT_FOUND"
