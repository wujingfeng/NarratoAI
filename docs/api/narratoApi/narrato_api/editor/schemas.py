from __future__ import annotations

from typing import Any

from pydantic import Field

from narrato_api.api.responses import StrictModel


class EditorSaveRequest(StrictModel):
    """编辑器以最后写入覆盖保存的完整草稿。"""

    content: dict[str, Any] = Field(default_factory=dict)


class EditorDraftData(StrictModel):
    """当前草稿及是否已进入只读锁定。"""

    draft_id: str
    content: dict[str, Any]
    locked: bool


class EditorSaveData(StrictModel):
    """草稿保存结果。"""

    draft_id: str


class RenderSubmitData(StrictModel):
    """最终渲染提交已被接受。"""

    accepted: bool
