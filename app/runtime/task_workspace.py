"""Core Task attempt 的独立文件工作区。"""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class TaskWorkspace:
    """描述单次 Core Task attempt 独占的临时和输出目录。"""

    root: Path
    temp_dir: Path
    output_dir: Path

    @classmethod
    def create(cls, base: Path, task_id: str, attempt_no: int) -> "TaskWorkspace":
        """在指定基目录中创建不可复用的 attempt 工作区。"""

        root = base / task_id / str(attempt_no)
        temp_dir, output_dir = root / "temp", root / "output"
        temp_dir.mkdir(parents=True, exist_ok=False)
        output_dir.mkdir(parents=True, exist_ok=True)
        return cls(root=root, temp_dir=temp_dir, output_dir=output_dir)
