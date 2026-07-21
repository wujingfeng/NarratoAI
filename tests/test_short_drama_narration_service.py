import importlib
import sys


def test_short_drama_service_imports_without_streamlit(monkeypatch):
    monkeypatch.setitem(sys.modules, "streamlit", None)
    sys.modules.pop("app.services.short_drama_narration_service", None)

    module = importlib.import_module("app.services.short_drama_narration_service")

    assert callable(module.build_short_drama_script)


def test_json_repair_normalization_and_public_field_filtering():
    from app.services.short_drama_narration_service import (
        ShortDramaAnalysisRequest,
        build_short_drama_script,
    )

    class Analyzer:
        def match_narration_copy_to_script(self, **kwargs):
            return {
                "status": "success",
                "narration_script": """```json
                {"items": [{"_id": 1, "video_id": 2, "video_name": "wrong.mp4",
                "timestamp": "00:00:01,000-00:00:02,000", "picture": "画面",
                "narration": "解说", "OST": 0, "planner_note": "remove"}]}
                ```""",
            }

    request = ShortDramaAnalysisRequest(
        analyzer=Analyzer(),
        video_paths=["/tmp/first.mp4", "/tmp/second.mp4"],
        short_name="测试短剧",
        plot_analysis="剧情分析",
        subtitle_content="字幕",
        narration_copy="审核后的文案",
        temperature=0.7,
    )

    assert build_short_drama_script(request) == [
        {
            "_id": 1,
            "video_id": 2,
            "video_name": "second.mp4",
            "timestamp": "00:00:01,000-00:00:02,000",
            "picture": "画面",
            "narration": "解说",
            "OST": 0,
        }
    ]


def test_narration_char_range_preserves_existing_calculation():
    from app.services.short_drama_narration_service import build_narration_char_range

    assert build_narration_char_range(600, "short_drama_narration", 40, 5) == "270-450"
