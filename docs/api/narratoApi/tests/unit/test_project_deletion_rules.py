from __future__ import annotations

import pytest

from narrato_api.projects.service import ProjectStateConflict, ensure_project_deletable


@pytest.mark.parametrize("status", ["completed", "failed"])
def test_only_terminal_projects_pass_the_deletion_eligibility_guard(
    status: str,
) -> None:
    ensure_project_deletable(status)


@pytest.mark.parametrize(
    "status",
    [
        "draft",
        "uploading",
        "validating",
        "ready",
        "queued",
        "analyzing",
        "waiting_for_edit",
        "render_queued",
        "rendering",
        "deleting",
        "deleted",
    ],
)
def test_non_terminal_projects_are_rejected_by_the_deletion_eligibility_guard(
    status: str,
) -> None:
    with pytest.raises(ProjectStateConflict) as caught:
        ensure_project_deletable(status)

    assert caught.value.code == "PROJECT_NOT_TERMINAL"
