import unittest
from unittest import mock

from app.models.diagnosis_schema import DiagnosisResult
from app.services.video_diagnosis.pdf_reporter import PDFReporter
from app.services.video_diagnosis.preprocessor import VideoPreprocessor
from app.services.video_diagnosis.service import VideoDiagnosisService
from app.services.video_diagnosis.profiles import (
    AnalysisMode,
    VideoType,
    get_video_type_profile,
)
from app.services.video_diagnosis.quality_analyzer import (
    MultiDimensionAnalyzer,
    RhythmAnalyzer,
    WasteClipDetector,
)


class VideoDiagnosisProfileTests(unittest.TestCase):
    def test_profiles_define_different_rhythm_thresholds_and_budgets(self):
        short_drama = get_video_type_profile(VideoType.SHORT_DRAMA, AnalysisMode.STANDARD)
        documentary = get_video_type_profile(VideoType.DOCUMENTARY, AnalysisMode.STANDARD)
        fast_short_drama = get_video_type_profile(VideoType.SHORT_DRAMA, AnalysisMode.FAST)

        self.assertLess(short_drama.rhythm.slow_pace_threshold, documentary.rhythm.slow_pace_threshold)
        self.assertLess(fast_short_drama.budget.max_vlm_calls, short_drama.budget.max_vlm_calls)
        self.assertIn("coherence", short_drama.focus_dimensions)
        self.assertIn("consistency", documentary.focus_dimensions)

    def test_rhythm_analyzer_uses_video_type_thresholds(self):
        documentary_profile = get_video_type_profile(VideoType.DOCUMENTARY, AnalysisMode.STANDARD)
        short_drama_profile = get_video_type_profile(VideoType.SHORT_DRAMA, AnalysisMode.STANDARD)

        documentary_result = self._run_async(
            RhythmAnalyzer(profile=documentary_profile).analyze(shots=[(0, 12), (12, 24), (24, 36)])
        )
        short_drama_result = self._run_async(
            RhythmAnalyzer(profile=short_drama_profile).analyze(shots=[(0, 7), (7, 14), (14, 21)])
        )

        self.assertEqual("适中", documentary_result["pace_assessment"])
        self.assertEqual("过慢", short_drama_result["pace_assessment"])

    def test_fast_mode_runs_only_profile_focus_dimensions(self):
        profile = get_video_type_profile(VideoType.SHORT_DRAMA, AnalysisMode.FAST)

        result = self._run_async(
            MultiDimensionAnalyzer(profile=profile).analyze_all(
                keyframe_paths=[],
                shots=[(0, 2), (2, 4)],
                video_path="missing.mp4",
            )
        )

        self.assertEqual(set(profile.focus_dimensions), set(result.keys()))
        self.assertNotIn("consistency", result)

    def test_waste_detector_uses_profile_silence_threshold(self):
        general = WasteClipDetector(
            profile=get_video_type_profile(VideoType.GENERAL, AnalysisMode.STANDARD)
        )
        documentary = WasteClipDetector(
            profile=get_video_type_profile(VideoType.DOCUMENTARY, AnalysisMode.STANDARD)
        )

        shots = [(0, 10)]
        silence = [(0, 9)]

        self.assertEqual(1, len(general._map_segments_to_shots([], silence, shots)))
        self.assertEqual([], documentary._map_segments_to_shots([], silence, shots))

    def test_preprocessor_rejects_invalid_video_metadata(self):
        preprocessor = VideoPreprocessor()

        with mock.patch(
            "app.services.video_diagnosis.preprocessor.VideoProcessor.get_video_info",
            return_value={"width": "0", "height": "0", "fps": "0", "duration": "0"},
        ):
            with self.assertRaisesRegex(RuntimeError, "视频元信息无效"):
                preprocessor.preprocess("bad.mp4", "task-1")

    def test_pdf_reporter_reads_trimmed_duration_from_editing_plan_summary(self):
        result = DiagnosisResult(
            task_id="task-1",
            video_path="video.mp4",
            video_duration=20.0,
            total_shots=2,
            editing_plan={
                "video_clips": [{}, {}],
                "transitions": [{}],
                "summary": {"trimmed_duration": 12.5},
            },
        )

        self.assertEqual(12.5, PDFReporter._get_editing_plan_duration(result.editing_plan))

    def test_save_results_supports_pydantic_v1_models(self):
        import json
        import os
        import tempfile

        result = DiagnosisResult(
            task_id="task-compat",
            video_path="video.mp4",
            video_duration=1.0,
            total_shots=0,
        )

        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                os.chdir(tmpdir)
                self._run_async(VideoDiagnosisService._save_results("task-compat", result))
                with open("storage/tasks/task-compat/diagnosis_result.json", "r", encoding="utf-8") as f:
                    saved = json.load(f)
            finally:
                os.chdir(old_cwd)

        self.assertEqual("task-compat", saved["task_id"])

    def test_dimension_scores_include_reason_evidence_suggestions_and_confidence(self):
        service = VideoDiagnosisService()
        preprocessed = self._make_preprocessed_video()
        result = service._build_diagnosis_result(
            task_id="task-scoring",
            video_path="video.mp4",
            preprocessed=preprocessed,
            quality_results={
                "coherence": {
                    "status": "warning",
                    "score": 62,
                    "description": "镜头衔接存在跳跃",
                    "issues": ["镜头1到2转场突兀"],
                    "problematic_transitions": [[1, 2]],
                    "suggestions": ["在镜头1和2之间补充过渡镜头"],
                    "details": {"checked_windows": 1},
                }
            },
            shot_details=[],
            editing_plan={},
        )

        score = result.dimension_scores[0]
        self.assertEqual("镜头衔接存在跳跃", score.reason)
        self.assertIn("镜头1到2转场突兀", score.evidence)
        self.assertIn("转场: 镜头1 -> 镜头2", score.evidence)
        self.assertEqual(["在镜头1和2之间补充过渡镜头"], score.suggestions)
        self.assertGreaterEqual(score.confidence, 0)
        self.assertLessEqual(score.confidence, 1)

    @staticmethod
    def _make_preprocessed_video():
        from app.models.diagnosis_schema import PreprocessedVideo

        return PreprocessedVideo(
            video_path="video.mp4",
            duration=12.0,
            width=1920,
            height=1080,
            fps=25.0,
            shots=[(0, 6), (6, 12)],
            keyframe_dir="frames",
            keyframe_paths=["frames/shot_001.jpg", "frames/shot_002.jpg"],
        )

    @staticmethod
    def _run_async(coro):
        import asyncio

        return asyncio.run(coro)


if __name__ == "__main__":
    unittest.main()
