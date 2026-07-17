from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WorkflowNodeTemplate:
    """描述模板内一个不可变的 DAG 节点。"""

    name: str
    depends_on: tuple[str, ...] = ()
    retryable: bool = True
    manual_gate: bool = False
    timeout_seconds: int | None = None


@dataclass(frozen=True)
class WorkflowTemplate:
    """描述可快照化的版本化工作流模板。"""

    version: str
    nodes: tuple[WorkflowNodeTemplate, ...]


SHORT_DRAMA_NARRATION_TEMPLATE_V1 = WorkflowTemplate(
    version="short_drama_narration_v1",
    nodes=(
        WorkflowNodeTemplate(name="media_probe"),
        WorkflowNodeTemplate(name="asr", depends_on=("media_probe",)),
        WorkflowNodeTemplate(
            name="video_analysis", depends_on=("media_probe", "asr")
        ),
        WorkflowNodeTemplate(name="script_generation", depends_on=("video_analysis",)),
        WorkflowNodeTemplate(
            name="waiting_for_edit",
            depends_on=("script_generation",),
            retryable=False,
            manual_gate=True,
        ),
        WorkflowNodeTemplate(name="tts", depends_on=("waiting_for_edit",)),
        WorkflowNodeTemplate(name="subtitle", depends_on=("tts",)),
        WorkflowNodeTemplate(name="video_render", depends_on=("subtitle",)),
        WorkflowNodeTemplate(name="publish_artifacts", depends_on=("video_render",)),
    ),
)
