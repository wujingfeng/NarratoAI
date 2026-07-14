import unittest
from unittest.mock import patch

from app.services.script_diagnosis.service import ScriptDiagnosisService


SUBTITLE_CONTENT = """# 视频 1: first.mp4
字幕文件: first.srt
1
00:00:01,000 --> 00:00:04,000
女主被众人误会，所有人都在羞辱她。

2
00:00:04,000 --> 00:00:08,000
男主冷眼看着她，气氛越来越紧张。

# 视频 2: second.mp4
字幕文件: second.srt
1
00:00:02,000 --> 00:00:05,000
女主终于拿出证据。

2
00:00:05,000 --> 00:00:09,000
众人震惊，反派彻底慌了。
"""


class ScriptDiagnosisServiceTests(unittest.TestCase):
    def setUp(self):
        self.service = ScriptDiagnosisService()
        self.video_paths = ["/tmp/first.mp4", "/tmp/second.mp4"]

    def test_diagnoses_original_sound_ratio_by_item_count(self):
        result = self.service.diagnose(
            items=[
                self._item(1, 1, "00:00:01,000-00:00:04,000", "她被当众误会。", 0),
                self._item(2, 1, "00:00:04,000-00:00:08,000", "气氛逐渐紧张。", 0),
                self._item(3, 2, "00:00:02,000-00:00:09,000", "播放原片3", 1),
            ],
            subtitle_content=SUBTITLE_CONTENT,
            video_paths=self.video_paths,
            original_sound_ratio=50,
            analysis_mode="rule",
        )

        self.assertEqual(3, result.overall.total_segments)
        self.assertEqual(1, result.overall.current_original_sound_count)
        self.assertEqual(2, result.overall.target_original_sound_count)
        self.assertEqual("low", result.overall.ratio_status)
        self.assertTrue(any("增加" in item for item in result.overall.ratio_adjustment_suggestions))

    def test_highlight_score_prioritizes_original_video_value(self):
        result = self.service.diagnose(
            items=[
                self._item(1, 2, "00:00:02,000-00:00:09,000", "播放原片1", 1),
            ],
            subtitle_content=SUBTITLE_CONTENT,
            video_paths=self.video_paths,
            original_sound_ratio=80,
            analysis_mode="rule",
        )

        segment = result.segments[0]
        self.assertGreaterEqual(segment.highlight_score, 80)
        self.assertEqual("high", segment.highlight_level)
        self.assertEqual("keep_as_original_sound", segment.decision)
        self.assertTrue(any("证据" in text or "震惊" in text for text in segment.evidence))

    def test_dense_narration_gets_manual_adjustment_suggestion(self):
        result = self.service.diagnose(
            items=[
                self._item(
                    1,
                    1,
                    "00:00:01,000-00:00:04,000",
                    "她原本只是一个被所有人看不起的普通女人，可这一刻她必须用自己的方式证明真相并完成反击。",
                    0,
                ),
            ],
            subtitle_content=SUBTITLE_CONTENT,
            video_paths=self.video_paths,
            original_sound_ratio=0,
            analysis_mode="rule",
        )

        segment = result.segments[0]
        self.assertEqual("adjust", segment.status)
        self.assertTrue(any(s["type"] == "extend_or_shorten_narration" for s in segment.suggestions))
        self.assertTrue(any("解说过密" in text for text in segment.evidence))

    def test_target_zero_original_sound_recommends_changing_ost(self):
        result = self.service.diagnose(
            items=[
                self._item(1, 2, "00:00:02,000-00:00:09,000", "播放原片1", 1),
            ],
            subtitle_content=SUBTITLE_CONTENT,
            video_paths=self.video_paths,
            original_sound_ratio=0,
            analysis_mode="rule",
        )

        segment = result.segments[0]
        self.assertEqual("adjust", segment.status)
        self.assertTrue(any(s["type"] == "change_ost" and s["to"] == 0 for s in segment.suggestions))

    def test_low_score_without_specific_suggestion_does_not_claim_reasonable(self):
        result = self.service.diagnose(
            items=[
                {
                    "_id": 1,
                    "video_id": 1,
                    "video_name": "first.mp4",
                    "timestamp": "00:00:01,000-00:00:04,000",
                    "picture": "人物在室内走动",
                    "narration": "普通过渡画面。",
                    "OST": 0,
                }
            ],
            subtitle_content="",
            video_paths=self.video_paths,
            original_sound_ratio=0,
            analysis_mode="rule",
        )

        segment = result.segments[0]
        self.assertEqual("adjust", segment.status)
        self.assertLess(segment.score, 65)
        self.assertNotIn("基本合理", segment.reason)
        self.assertIn("高燃", segment.reason)

    def test_documentary_profile_prioritizes_information_value(self):
        item = {
            "_id": 1,
            "video_id": 1,
            "video_name": "first.mp4",
            "timestamp": "00:00:01,000-00:00:08,000",
            "picture": "镜头记录真实现场环境变化，并展示历史数据",
            "narration": "这一段解释现场环境变化背后的事实原因。",
            "OST": 0,
        }

        documentary = self.service.diagnose(
            items=[item],
            subtitle_content="",
            video_paths=self.video_paths,
            original_sound_ratio=0,
            content_type="documentary",
            analysis_mode="rule",
        ).segments[0]
        short_drama = self.service.diagnose(
            items=[item],
            subtitle_content="",
            video_paths=self.video_paths,
            original_sound_ratio=0,
            content_type="short_drama_narration",
            analysis_mode="rule",
        ).segments[0]

        self.assertGreater(documentary.highlight_score, short_drama.highlight_score)
        self.assertIn("信息价值", documentary.reason)

    def test_short_mix_profile_prioritizes_original_sound_highlight_value(self):
        item = {
            "_id": 1,
            "video_id": 2,
            "video_name": "second.mp4",
            "timestamp": "00:00:02,000-00:00:08,000",
            "picture": "关键对白爆发，身份反转后完成打脸爽点",
            "narration": "播放原片1",
            "OST": 1,
        }

        short_mix = self.service.diagnose(
            items=[item],
            subtitle_content="",
            video_paths=self.video_paths,
            original_sound_ratio=100,
            content_type="short_drama_mix",
            analysis_mode="rule",
        ).segments[0]
        documentary = self.service.diagnose(
            items=[item],
            subtitle_content="",
            video_paths=self.video_paths,
            original_sound_ratio=100,
            content_type="documentary",
            analysis_mode="rule",
        ).segments[0]

        self.assertGreater(short_mix.highlight_score, documentary.highlight_score)
        self.assertEqual("keep_as_original_sound", short_mix.decision)

    def test_llm_analysis_uses_global_context_and_marks_visual_review(self):
        prompts = []

        async def fake_generate_text(**kwargs):
            prompts.append(kwargs["prompt"])
            return """
            {
              "segments": [
                {
                  "item_id": 1,
                  "highlight_score": 88,
                  "score": 82,
                  "decision": "keep_as_original_sound",
                  "status": "keep",
                  "reason": "这是女主反击前的关键羞辱节点，保留原声能强化情绪。",
                  "evidence": ["命中剧情理解中的误会和反击前置冲突"],
                  "suggestions": [{"type": "visual_review", "reason": "需要确认人物表情和现场压迫感"}],
                  "confidence": 0.61,
                  "needs_visual_review": true
                }
              ]
            }
            """

        with patch(
            "app.services.script_diagnosis.service.UnifiedLLMService.generate_text",
            new=fake_generate_text,
            create=True,
        ):
            result = self.service.diagnose(
                items=[self._item(1, 1, "00:00:01,000-00:00:04,000", "播放原片1", 1)],
                subtitle_content=SUBTITLE_CONTENT,
                video_paths=self.video_paths,
                original_sound_ratio=100,
                content_type="short_drama_narration",
                plot_analysis="女主被家人误会羞辱，随后用证据完成反击。",
                narration_copy="她被逼到绝境，反击从这一刻开始。",
            )

        self.assertEqual(1, len(prompts))
        self.assertIn("女主被家人误会羞辱", prompts[0])
        self.assertIn("她被逼到绝境", prompts[0])
        segment = result.segments[0]
        self.assertEqual(88, segment.highlight_score)
        self.assertEqual(82, segment.score)
        self.assertEqual("keep_as_original_sound", segment.decision)
        self.assertIn("关键羞辱节点", segment.reason)
        self.assertTrue(segment.needs_visual_review)

    @staticmethod
    def _item(item_id, video_id, timestamp, narration, ost):
        video_name = "first.mp4" if video_id == 1 else "second.mp4"
        return {
            "_id": item_id,
            "video_id": video_id,
            "video_name": video_name,
            "timestamp": timestamp,
            "picture": "人物发生冲突",
            "narration": narration,
            "OST": ost,
        }


if __name__ == "__main__":
    unittest.main()
