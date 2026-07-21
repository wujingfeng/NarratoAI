from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from narrato_api.database import Base


def test_registered_artifact_persists_core_jianying_resource_metadata() -> None:
    from narrato_api.artifacts.models import RegisteredArtifact
    from narrato_api.artifacts.service import register_artifact
    from narrato_api.auth.models import User
    from narrato_api.projects.models import Project

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        session.add(User(id="usr_1", email="owner@example.com", password_hash="hash"))
        session.add(
            Project(
                id="prj_1", user_id="usr_1", product="short_drama", status="completed"
            )
        )
        session.commit()

        register_artifact(
            session,
            artifact_id="art_1",
            project_id="prj_1",
            kind="video",
            cdn_url="https://cdn.example.test/exports/art_1.mp4",
            size=1024,
            checksum="sha256:" + "a" * 64,
            content_type="video/mp4",
            width=1920,
            height=1080,
            duration=12.5,
        )
        session.commit()

    with Session(engine) as session:
        artifact = session.get(RegisteredArtifact, "art_1")

    assert artifact is not None
    assert (
        artifact.size,
        artifact.checksum,
        artifact.content_type,
        artifact.width,
        artifact.height,
        artifact.duration,
    ) == (1024, "sha256:" + "a" * 64, "video/mp4", 1920, 1080, 12.5)


def test_jianying_manifest_maps_registered_core_resource_metadata() -> None:
    from narrato_api.artifacts.models import RegisteredArtifact
    from narrato_api.exports.service import build_jianying_manifest

    manifest = build_jianying_manifest(
        [
            RegisteredArtifact(
                id="art_1",
                project_id="prj_1",
                kind="video",
                cdn_url="https://cdn.example.test/exports/art_1.mp4",
                size=1024,
                checksum="sha256:" + "a" * 64,
                content_type="video/mp4",
                width=1920,
                height=1080,
                duration=12.5,
            )
        ]
    )

    assert manifest["resources"][0] == {
        "artifact_id": "art_1",
        "cdn_url": "https://cdn.example.test/exports/art_1.mp4",
        "zip_path": "video/a462bcfc56c8dc6f20f67e81eab83864.mp4",
        "size": 1024,
        "checksum": "sha256:" + "a" * 64,
        "content_type": "video/mp4",
        "width": 1920,
        "height": 1080,
        "duration": 12.5,
    }
