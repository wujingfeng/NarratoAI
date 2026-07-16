from __future__ import annotations

import re
import stat
import os
from dataclasses import dataclass
from pathlib import Path


_TASK_ID = re.compile(r"^ctask_[A-Za-z0-9]+$")


class WorkspaceSecurityError(ValueError):
    """attempt 工作区路径或标识不安全。"""


@dataclass(frozen=True, slots=True)
class CoreTaskWorkspace:
    """一个 Core attempt 独占的 input/temp/output 工作区。"""

    base_dir: Path
    root: Path
    input_dir: Path
    temp_dir: Path
    output_dir: Path

    @classmethod
    def create(
        cls, base: str | Path, core_task_id: str, attempt_no: int
    ) -> CoreTaskWorkspace:
        """创建新 attempt 目录，绝不静默复用已有脏目录。"""

        if not _TASK_ID.fullmatch(core_task_id) or attempt_no <= 0:
            raise WorkspaceSecurityError("WORKSPACE_ID_INVALID")
        base_path = Path(base).expanduser().resolve()
        base_path.mkdir(parents=True, exist_ok=True)
        task_root = base_path / core_task_id
        if task_root.exists() and (task_root.is_symlink() or not task_root.is_dir()):
            raise WorkspaceSecurityError("WORKSPACE_PATH_INVALID")
        task_root.mkdir(exist_ok=True)
        root = task_root / str(attempt_no)
        # attempt 目录原子新建；任何遗留内容都要求人工/恢复逻辑明确处理。
        root.mkdir(exist_ok=False)
        resolved = root.resolve()
        if base_path not in resolved.parents:
            raise WorkspaceSecurityError("WORKSPACE_ESCAPE")
        input_dir = resolved / "input"
        temp_dir = resolved / "temp"
        output_dir = resolved / "output"
        for directory in (input_dir, temp_dir, output_dir):
            directory.mkdir()
        return cls(base_path, resolved, input_dir, temp_dir, output_dir)

    def validate_directory(self, directory: Path) -> Path:
        """以创建时固定 base/root 为锚点拒绝祖先 symlink 或目录替换。"""

        lexical = Path(directory)
        try:
            relative = lexical.relative_to(self.base_dir)
        except ValueError as exc:
            raise WorkspaceSecurityError("WORKSPACE_ESCAPE") from exc
        current = self.base_dir
        for part in relative.parts:
            current = current / part
            try:
                mode = current.lstat().st_mode
            except OSError as exc:
                raise WorkspaceSecurityError("WORKSPACE_PATH_INVALID") from exc
            if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
                raise WorkspaceSecurityError("WORKSPACE_PATH_INVALID")
        if self.root not in (lexical, *lexical.parents):
            raise WorkspaceSecurityError("WORKSPACE_ESCAPE")
        return lexical

    def controlled_path(self, area: str, kind: str, extension: str) -> Path:
        """按受控 kind/extension 生成工作区文件路径。"""

        if area not in {"input", "temp", "output"}:
            raise WorkspaceSecurityError("WORKSPACE_AREA_INVALID")
        if not re.fullmatch(r"[a-z][a-z0-9_-]{0,31}", kind):
            raise WorkspaceSecurityError("WORKSPACE_KIND_INVALID")
        if not re.fullmatch(r"[a-z0-9]{1,8}", extension):
            raise WorkspaceSecurityError("WORKSPACE_EXTENSION_INVALID")
        directory = getattr(self, f"{area}_dir")
        self.validate_directory(directory)
        target = directory / f"{kind}.{extension}"
        if directory not in target.parents:
            raise WorkspaceSecurityError("WORKSPACE_ESCAPE")
        return target

    def open_area_fd(self, area: str) -> int:
        """从固定 base dirfd 逐层 O_NOFOLLOW 打开 attempt area。"""

        if area not in {"input", "temp", "output"}:
            raise WorkspaceSecurityError("WORKSPACE_AREA_INVALID")
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(self.base_dir, flags)
            relative = (self.root / area).relative_to(self.base_dir)
            for part in relative.parts:
                next_descriptor = os.open(part, flags, dir_fd=descriptor)
                os.close(descriptor)
                descriptor = next_descriptor
            return descriptor
        except (OSError, ValueError) as exc:
            try:
                os.close(descriptor)
            except (OSError, UnboundLocalError):
                pass
            raise WorkspaceSecurityError("WORKSPACE_PATH_INVALID") from exc
