from __future__ import annotations

import pytest

from narrato_api.projects import service


def test_completed_project_passes_the_export_eligibility_guard() -> None:
    service.ensure_project_exportable("completed")


@pytest.mark.parametrize(
    "status",
    [
        "failed",
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
def test_non_completed_projects_are_rejected_by_the_export_eligibility_guard(
    status: str,
) -> None:
    with pytest.raises(service.ProjectStateConflict) as caught:
        service.ensure_project_exportable(status)

    assert caught.value.code == "PROJECT_NOT_COMPLETED"
