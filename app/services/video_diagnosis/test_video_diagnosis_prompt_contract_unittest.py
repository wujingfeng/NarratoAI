import re
import unittest
from pathlib import Path


PROMPT_DIR = Path(__file__).resolve().parents[1] / "prompts" / "video_diagnosis"


def render_like_quality_analyzer(template: str, parameters: dict) -> str:
    rendered = template
    for key, value in parameters.items():
        rendered = rendered.replace("{{" + key + "}}", str(value))
        rendered = rendered.replace("{" + key + "}", str(value))
    return rendered


class VideoDiagnosisPromptContractTests(unittest.TestCase):
    def test_quality_analyzer_prompts_match_current_parameters_and_output_fields(self):
        cases = {
            "consistency_check.txt": {
                "params": {"num_shots": 12, "batch_index": 1, "total_batches": 2, "video_type_context": "短剧标准"},
                "must_contain": ["12", "第 1 / 2 批", "短剧标准", '"score"', '"description"', '"inconsistent_shots"'],
                "must_not_contain": ["{shot_descriptions}"],
            },
            "coherence_check.txt": {
                "params": {"window_start": 2, "window_end": 4, "total_shots": 12, "video_type_context": "短剧标准"},
                "must_contain": ["镜头 2 到镜头 4", "短剧标准", '"issues"', '"problematic_transitions"', '"suggestions"'],
                "must_not_contain": ["{num_consecutive}", "{consecutive_shot_data}"],
            },
            "duplicate_check.txt": {
                "params": {"shot_i": 3, "shot_j": 7, "hamming_distance": 2, "video_type_context": "短剧标准"},
                "must_contain": ["镜头 3", "镜头 7", "汉明距离: 2", "短剧标准", '"is_duplicate"', '"confidence"', '"reason"'],
                "must_not_contain": ["{shot1_description}", "{shot2_description}"],
            },
            "rhythm_check.txt": {
                "params": {"total_shots": 12, "problematic_ranges": "镜头 1-3: 连续过短 (<1s)", "video_type_context": "短剧标准"},
                "must_contain": ["总镜头数: 12", "镜头 1-3", "短剧标准", '"suggestions"'],
                "must_not_contain": ["{avg_duration", "{min_duration", "{max_duration", "{std_duration", "{abnormal_sequences}"],
            },
            "waste_check.txt": {
                "params": {"shot_id": 5, "reasons": "黑屏 (1.0s-2.0s)", "video_type_context": "短剧标准"},
                "must_contain": ["镜头编号: 5", "黑屏 (1.0s-2.0s)", "短剧标准", '"is_waste"', '"reason"', '"action"'],
                "must_not_contain": ["{waste_candidates}", '"confirmed_waste_clips"', '"false_positives"'],
            },
        }

        for filename, contract in cases.items():
            with self.subTest(filename=filename):
                template = (PROMPT_DIR / filename).read_text(encoding="utf-8")
                rendered = render_like_quality_analyzer(template, contract["params"])

                for expected in contract["must_contain"]:
                    self.assertIn(expected, rendered)
                for stale in contract["must_not_contain"]:
                    self.assertNotIn(stale, rendered)
                self.assertEqual([], re.findall(r"\{[a-zA-Z_][a-zA-Z0-9_]*(?::[^}]*)?\}", rendered))


if __name__ == "__main__":
    unittest.main()
