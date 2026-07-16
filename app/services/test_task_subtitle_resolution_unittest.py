import unittest

from app.models.schema import VideoClipParams
from app.services import task


class TaskSubtitleResolutionTests(unittest.TestCase):
    def test_get_original_subtitle_paths_does_not_guess_from_video_name(self):
        params = VideoClipParams(video_origin_path="/tmp/01_1080p_20260608113314.mp4")

        self.assertEqual([], task._get_original_subtitle_paths(params))

    def test_get_original_subtitle_paths_keeps_explicit_params(self):
        params = VideoClipParams(
            video_origin_path="/tmp/01_1080p_20260608113314.mp4",
            original_subtitle_paths=["/tmp/provided.srt"],
        )

        self.assertEqual(["/tmp/provided.srt"], task._get_original_subtitle_paths(params))


if __name__ == "__main__":
    unittest.main()
