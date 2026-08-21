from __future__ import annotations

import pytest

from core_api.adapters.narrato.short_drama import ProviderOutputError
from core_api.adapters.narrato.video_translation import VideoTranslationAdapter
from core_api.runtime.workspace import CoreTaskWorkspace


class RewriteProvider:
    def rewrite_translations(self, segments, *, target_language):
        assert target_language == "en"
        assert [item["segment_id"] for item in segments] == ["seg-1"]
        return ["Run now"]


class TooLongRewriteProvider:
    def rewrite_translations(self, _segments, *, target_language):
        assert target_language == "en"
        return ["one two three four"]


class UnusedDownloader:
    def download(self, *_args, **_kwargs):
        raise AssertionError("rewrite must not download an SRT")


def _workspace(tmp_path, attempt: int = 1) -> CoreTaskWorkspace:
    return CoreTaskWorkspace.create(tmp_path, "ctask_rewrite", attempt)


def test_rewrite_only_processes_inline_affected_segments(tmp_path):
    result = VideoTranslationAdapter(
        provider=RewriteProvider(), downloader=UnusedDownloader()
    ).run(
        workspace=_workspace(tmp_path),
        target_language="en",
        rewrite_mode=True,
        segments=[
            {
                "segment_id": "seg-1",
                "segment_index": 2,
                "source_text": "快跑",
                "translated_text": "You need to run right now",
                "allowed_duration_ms": 900,
                "max_words": 3,
            }
        ],
    )
    assert result == {
        "segments": [
            {
                "segment_id": "seg-1",
                "segment_index": 2,
                "source_text": "快跑",
                "translated_text": "Run now",
                "allowed_duration_ms": 900,
                "max_words": 3,
                "rewrite_status": "rewritten",
            }
        ]
    }


def test_rewrite_rejects_provider_output_still_over_limit(tmp_path):
    adapter = VideoTranslationAdapter(
        provider=TooLongRewriteProvider(), downloader=UnusedDownloader()
    )
    with pytest.raises(ProviderOutputError, match="TRANSLATION_REWRITE_STILL_TOO_LONG"):
        adapter.run(
            workspace=_workspace(tmp_path, 2),
            target_language="en",
            rewrite_mode=True,
            segments=[
                {
                    "segment_id": "seg-1",
                    "segment_index": 0,
                    "translated_text": "one two three four five",
                    "allowed_duration_ms": 700,
                    "max_words": 3,
                }
            ],
        )
