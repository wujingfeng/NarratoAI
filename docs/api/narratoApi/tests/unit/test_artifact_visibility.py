from __future__ import annotations

from narrato_api.projects.service import visible_artifacts


def test_failed_project_hides_all_previously_available_artifacts() -> None:
    partial_artifacts = [
        {"id": "art_partial_video", "kind": "video"},
        {"id": "art_partial_subtitle", "kind": "subtitle"},
    ]

    assert visible_artifacts("failed", partial_artifacts) == []


def test_completed_project_keeps_registered_artifacts_visible() -> None:
    artifacts = [{"id": "art_final_video", "kind": "video"}]

    assert visible_artifacts("completed", artifacts) == artifacts
