from __future__ import annotations

import pytest

from narrato_api.projects.service import ProjectStateConflict, ensure_project_deletable


@pytest.mark.parametrize(
    ("status", "current_stage"),
    [
        ("completed", "export"),
        ("failed", "analysis"),
        ("draft", "created"),
        ("uploading", "created"),
        ("validating", "created"),
        ("ready", "settings"),
    ],
)
def test_terminal_or_pre_analysis_projects_pass_the_deletion_eligibility_guard(
    status: str, current_stage: str
) -> None:
    ensure_project_deletable(status, current_stage)


@pytest.mark.parametrize(
    ("status", "current_stage"),
    [
        ("queued", "analysis"),
        ("analyzing", "analysis"),
        ("waiting_for_edit", "edit"),
        ("render_queued", "generate"),
        ("rendering", "generate"),
        ("cancelled", "export"),
        ("deleting", "created"),
        ("deleted", "settings"),
    ],
)
def test_processing_or_deletion_states_are_rejected_by_the_deletion_guard(
    status: str, current_stage: str
) -> None:
    with pytest.raises(ProjectStateConflict) as caught:
        ensure_project_deletable(status, current_stage)

    assert caught.value.code == "PROJECT_NOT_TERMINAL"
