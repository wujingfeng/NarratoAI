from __future__ import annotations

from narrato_api.workflows.templates.short_drama_narration_v1 import (
    SHORT_DRAMA_NARRATION_TEMPLATE_V1,
)


def test_short_drama_template_has_the_fixed_versioned_node_order() -> None:
    assert SHORT_DRAMA_NARRATION_TEMPLATE_V1.version == "short_drama_narration_v1"
    assert [node.name for node in SHORT_DRAMA_NARRATION_TEMPLATE_V1.nodes] == [
        "media_probe",
        "asr",
        "video_analysis",
        "script_generation",
        "waiting_for_edit",
        "tts",
        "subtitle",
        "video_render",
        "publish_artifacts",
    ]


def test_short_drama_template_has_required_dag_dependencies() -> None:
    dependencies = {
        node.name: node.depends_on for node in SHORT_DRAMA_NARRATION_TEMPLATE_V1.nodes
    }

    assert dependencies == {
        "media_probe": (),
        "asr": ("media_probe",),
        "video_analysis": ("media_probe", "asr"),
        "script_generation": ("video_analysis",),
        "waiting_for_edit": ("script_generation",),
        "tts": ("waiting_for_edit",),
        "subtitle": ("tts",),
        "video_render": ("subtitle",),
        "publish_artifacts": ("video_render",),
    }


def test_waiting_for_edit_is_a_non_expiring_manual_gate() -> None:
    waiting_node = next(
        node
        for node in SHORT_DRAMA_NARRATION_TEMPLATE_V1.nodes
        if node.name == "waiting_for_edit"
    )

    assert waiting_node.manual_gate is True
    assert waiting_node.timeout_seconds is None
    assert waiting_node.retryable is False
