import unittest

from webui.tools import generate_short_summary
from webui.tools.generate_short_summary import _format_progress_status, parse_and_fix_json
from app.services.short_drama_narration_service import (
    ShortDramaAnalysisRequest,
    ShortDramaNarrationError,
    build_short_drama_script,
)


class GenerateShortSummaryJsonTests(unittest.TestCase):
    def test_progress_message_does_not_prefix_fake_percentage(self):
        status = _format_progress_status(60, "正在生成文案...")

        self.assertEqual("正在生成文案...", status)
        self.assertNotIn("60%", status)

    def test_invalid_json_does_not_create_default_fake_script(self):
        self.assertIsNone(parse_and_fix_json("not a json response"))

    def test_json_code_block_is_parsed(self):
        parsed = parse_and_fix_json(
            """```json
{"items": [{"_id": 1, "timestamp": "00:00:01,000-00:00:02,000"}]}
```"""
        )

        self.assertEqual(1, parsed["items"][0]["_id"])

    def test_narration_char_range_uses_category_ratio_and_original_sound_ratio(self):
        char_range = generate_short_summary.build_narration_char_range(
            source_duration_seconds=600,
            prompt_category=generate_short_summary.SHORT_DRAMA_PROMPT_CATEGORY,
            original_sound_ratio=40,
            chars_per_second=5,
        )

        self.assertEqual("270-450", char_range)

    def test_missing_items_keeps_dedicated_webui_error_message(self):
        with self.assertRaises(ShortDramaNarrationError) as caught:
            build_short_drama_script(
                ShortDramaAnalysisRequest(
                    video_paths=["/tmp/first.mp4"],
                    narration_result={
                        "status": "success",
                        "narration_script": '{"message": "valid json without items"}',
                    },
                )
            )

        self.assertEqual(
            "Generated narration missing items field",
            generate_short_summary._script_error_message_key(caught.exception),
        )


if __name__ == "__main__":
    unittest.main()
