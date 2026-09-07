from __future__ import annotations

import hashlib
import logging

import pytest

from core_api.adapters.narrato.prompts.short_drama_plot_analysis import (
    PLOT_ANALYSIS_SYSTEM_PROMPT,
    PLOT_ANALYSIS_TEMPLATE,
    plot_analysis_prompt_metadata,
    render_plot_analysis_prompt,
)
from core_api.adapters.narrato.short_drama import (
    NarratoShortDramaProvider,
    ProviderResponseError,
    _safe_analysis,
    validate_plot_analysis_output,
)


def test_core_plot_analysis_prompt_v11_is_frozen_by_exact_hash() -> None:
    assert hashlib.sha256(PLOT_ANALYSIS_TEMPLATE.encode()).hexdigest() == (
        "441e3ced659a2798df26cf79635633cd6e8555ef715ae8028c2a934d44f8501c"
    )
    assert hashlib.sha256(PLOT_ANALYSIS_SYSTEM_PROMPT.encode()).hexdigest() == (
        "b8fb09058318474a7e1fd7f4dbe7d6c5d492bca54bcdf0becd0319db9a955f8d"
    )
    assert plot_analysis_prompt_metadata() == {
        "prompt_category": "short_drama_narration",
        "prompt_name": "plot_analysis",
        "prompt_version": "v1.1",
    }


def test_core_plot_analysis_prompt_renders_full_multivideo_srt_contract() -> None:
    subtitle_content = NarratoShortDramaProvider._subtitle_content(
        [
            {
                "video_name": "episode-01.mp4",
                "subtitle_name": "episode-01.srt",
                "subtitle_text": (
                    "1\n00:00:04,440 --> 00:00:05,880\n各位蓝星的朋友"
                ),
            },
            {
                "video_name": "episode-02.mp4",
                "subtitle_name": "episode-02.srt",
                "subtitle_text": "1\n00:00:00,320 --> 00:00:01,420\n还是我来吧！",
            },
        ]
    )
    assert subtitle_content == (
        "# 视频 1: episode-01.mp4\n"
        "字幕文件: episode-01.srt\n"
        "1\n00:00:04,440 --> 00:00:05,880\n各位蓝星的朋友\n\n"
        "# 视频 2: episode-02.mp4\n"
        "字幕文件: episode-02.srt\n"
        "1\n00:00:00,320 --> 00:00:01,420\n还是我来吧！"
    )
    prompt = render_plot_analysis_prompt(subtitle_content)
    assert prompt == PLOT_ANALYSIS_TEMPLATE.replace(
        "${subtitle_content}", subtitle_content
    )
    assert "00:00:04,440 --> 00:00:05,880" in prompt
    assert "必须严格按照下面的 Markdown 格式输出" in prompt
    assert "联网检索确认" in prompt


def test_plot_analysis_output_validation_matches_text_contract(caplog) -> None:
    with pytest.raises(ProviderResponseError, match="PLOT_ANALYSIS_EMPTY"):
        validate_plot_analysis_output("  ")
    with pytest.raises(ProviderResponseError, match="PLOT_ANALYSIS_TOO_SHORT"):
        validate_plot_analysis_output("剧情太短")

    without_keyword = "甲" * 50
    with caplog.at_level(
        logging.WARNING, logger="core_api.adapters.narrato.short_drama"
    ):
        assert validate_plot_analysis_output(without_keyword) == without_keyword
    assert "short_drama_plot_analysis_keywords_missing" in caplog.text

    valid = "  当前剧情围绕角色冲突展开，故事内容全部来自字幕，并保留当前情节中的悬念。" + "甲" * 20
    assert validate_plot_analysis_output(valid) == valid.strip()


def test_analysis_artifact_preserves_complete_markdown_without_truncation() -> None:
    full_markdown = "剧情" + "甲" * 6000
    result = _safe_analysis(
        {
            "title": "短剧分析",
            "summary": full_markdown,
            "scenes": [{"source_asset_id": "asset_a", "summary": "字幕"}],
        },
        ["asset_a"],
    )
    assert result["summary"] == full_markdown
