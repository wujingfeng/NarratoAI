from __future__ import annotations

import inspect

from narrato_api.artifacts.models import RegisteredArtifact


def _artifact(*, artifact_id: str, kind: str, cdn_url: str) -> RegisteredArtifact:
    return RegisteredArtifact(
        id=artifact_id,
        project_id="prj_1",
        kind=kind,
        cdn_url=cdn_url,
    )


def test_build_jianying_manifest_returns_only_required_resource_fields_in_artifact_id_order() -> (
    None
):
    from narrato_api.exports.service import build_jianying_manifest

    manifest = build_jianying_manifest(
        [
            _artifact(
                artifact_id="art_video",
                kind="video",
                cdn_url="https://cdn.example.test/renders/final.mp4",
            ),
            _artifact(
                artifact_id="art_audio",
                kind="audio",
                cdn_url="https://cdn.example.test/audio/voice.mp3",
            ),
        ]
    )

    assert manifest["package_name"] == "jianying-export.zip"
    assert manifest["resources"] == [
        {
            "artifact_id": "art_audio",
            "cdn_url": "https://cdn.example.test/audio/voice.mp3",
            "zip_path": "assets/voice/79edf130a465a9651ba5715b9d95b5f3.wav",
        },
        {
            "artifact_id": "art_video",
            "cdn_url": "https://cdn.example.test/renders/final.mp4",
            "zip_path": "assets/video/397b6c2889bd2f42259dda019f36c8cd.mp4",
        },
    ]


def test_build_jianying_manifest_uses_safe_static_paths_not_url_or_artifact_path_segments() -> (
    None
):
    from narrato_api.exports.service import build_jianying_manifest

    artifact = _artifact(
        artifact_id="../../unsafe id?.srt",
        kind="subtitle",
        cdn_url="https://cdn.example.test/../../evil%2Fname.exe?download=1",
    )

    manifest = build_jianying_manifest([artifact])
    resource = manifest["resources"][0]

    assert resource["artifact_id"] == "../../unsafe id?.srt"
    assert resource["cdn_url"] == artifact.cdn_url
    assert (
        resource["zip_path"] == "assets/subtitle/5730df20a59b9761ba944389d9ebf96e.srt"
    )
    assert ".." not in resource["zip_path"]
    assert "/" in resource["zip_path"]
    assert resource["zip_path"].count("/") == 2


def test_build_jianying_manifest_is_deterministic_and_has_no_io_dependencies() -> None:
    from narrato_api.exports import service

    artifacts = (
        _artifact(
            artifact_id="art_timeline",
            kind="timeline",
            cdn_url="https://cdn.example.test/timeline.json",
        ),
    )

    assert service.build_jianying_manifest(
        artifacts
    ) == service.build_jianying_manifest(artifacts)

    source = inspect.getsource(service)
    for forbidden_dependency in ("zipfile", "httpx", "requests", "urllib", "open("):
        assert forbidden_dependency not in source
