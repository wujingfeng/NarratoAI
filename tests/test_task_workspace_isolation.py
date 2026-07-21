from pathlib import Path

import pytest


def test_attempt_workspaces_never_share_paths(tmp_path: Path):
    from app.runtime.task_workspace import TaskWorkspace

    first = TaskWorkspace.create(tmp_path, "ctask_a", 1)
    second = TaskWorkspace.create(tmp_path, "ctask_a", 2)

    assert first.root != second.root
    assert first.temp_dir.parent == first.root
    assert first.output_dir.parent == first.root
    assert first.temp_dir.is_dir()
    assert first.output_dir.is_dir()


def test_same_attempt_workspace_cannot_be_reused(tmp_path: Path):
    from app.runtime.task_workspace import TaskWorkspace

    TaskWorkspace.create(tmp_path, "ctask_a", 1)

    with pytest.raises(FileExistsError):
        TaskWorkspace.create(tmp_path, "ctask_a", 1)
