import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app.services import subtitle_corrector as corrector


SAMPLE_SRT = """1
00:00:01,000 --> 00:00:03,000
今天我们来看张三的顾是

2
00:00:04,000 --> 00:00:06,000
他来到北精找李四
"""


class SubtitleCorrectorTests(unittest.TestCase):
    def test_correct_srt_content_preserves_timecodes_and_rebuilds_text(self):
        llm_output = {
            "items": [
                {"id": 1, "text": "今天我们来看张三的故事"},
                {"id": 2, "text": "他来到北京找李四"},
            ]
        }

        with (
            mock.patch("app.services.subtitle_corrector._ensure_llm_providers_registered"),
            mock.patch(
                "app.services.subtitle_corrector._run_async_safely",
                return_value=json.dumps(llm_output, ensure_ascii=False),
            ) as run_llm,
        ):
            corrected = corrector.correct_srt_content(
                SAMPLE_SRT,
                provider="openai",
                api_key="sk-test",
                base_url="https://llm.example/v1",
            )

        self.assertIn("00:00:01,000 --> 00:00:03,000", corrected)
        self.assertIn("今天我们来看张三的故事", corrected)
        self.assertIn("他来到北京找李四", corrected)
        self.assertNotIn("顾是", corrected)

        call_kwargs = run_llm.call_args.kwargs
        self.assertEqual("openai", call_kwargs["provider"])
        self.assertEqual("sk-test", call_kwargs["api_key"])
        self.assertEqual("https://llm.example/v1", call_kwargs["api_base"])
        self.assertEqual("json", call_kwargs["response_format"])
        self.assertIn("多语言字幕校对员", call_kwargs["system_prompt"])
        self.assertIn("保持原语言", call_kwargs["prompt"])

    def test_correct_srt_content_rejects_missing_items(self):
        llm_output = {"items": [{"id": 1, "text": "今天我们来看张三的故事"}]}

        with (
            mock.patch("app.services.subtitle_corrector._ensure_llm_providers_registered"),
            mock.patch(
                "app.services.subtitle_corrector._run_async_safely",
                return_value=json.dumps(llm_output, ensure_ascii=False),
            ),
        ):
            with self.assertRaises(corrector.SubtitleCorrectionError):
                corrector.correct_srt_content(SAMPLE_SRT, provider="openai")

    def test_correct_subtitle_file_writes_corrected_srt(self):
        llm_output = {
            "items": [
                {"id": 1, "text": "今天我们来看张三的故事"},
                {"id": 2, "text": "他来到北京找李四"},
            ]
        }

        with tempfile.TemporaryDirectory() as tmp_dir:
            input_file = Path(tmp_dir) / "input.srt"
            output_file = Path(tmp_dir) / "output.srt"
            input_file.write_text(SAMPLE_SRT, encoding="utf-8")

            with (
                mock.patch("app.services.subtitle_corrector._ensure_llm_providers_registered"),
                mock.patch(
                    "app.services.subtitle_corrector._run_async_safely",
                    return_value=json.dumps(llm_output, ensure_ascii=False),
                ),
            ):
                result_path = corrector.correct_subtitle_file(
                    str(input_file),
                    str(output_file),
                    provider="openai",
                )

            self.assertEqual(str(output_file), result_path)
            self.assertIn("北京", output_file.read_text(encoding="utf-8"))

    def test_correct_srt_content_batches_large_srt_by_default_with_global_context(self):
        large_srt = "\n\n".join(
            [
                f"{index}\n00:00:{index:02d},000 --> 00:00:{index:02d},900\n错字{index}"
                for index in range(1, 46)
            ]
        )
        llm_outputs = [
            json.dumps({"items": [{"id": index, "text": f"正字{index}"} for index in range(1, 21)]}, ensure_ascii=False),
            json.dumps({"items": [{"id": index, "text": f"正字{index}"} for index in range(21, 41)]}, ensure_ascii=False),
            json.dumps({"items": [{"id": index, "text": f"正字{index}"} for index in range(41, 46)]}, ensure_ascii=False),
        ]
        progress_events = []

        with (
            mock.patch("app.services.subtitle_corrector._ensure_llm_providers_registered"),
            mock.patch(
                "app.services.subtitle_corrector._run_async_safely",
                side_effect=llm_outputs,
            ) as run_llm,
        ):
            corrected = corrector.correct_srt_content(
                large_srt,
                provider="openai",
                progress_callback=lambda completed, total, message: progress_events.append(
                    (completed, total, message)
                ),
            )

        self.assertEqual(3, run_llm.call_count)
        prompts = [call.kwargs["prompt"] for call in run_llm.call_args_list]
        for prompt in prompts:
            self.assertIn("全片字幕上下文", prompt)
            self.assertIn("仅供判断语言、专名和前后语境", prompt)
            self.assertIn("不要按上下文增删当前批字幕", prompt)
            self.assertIn("错字1", prompt)
            self.assertIn("错字45", prompt)
        self.assertIn('"id": 1', prompts[0])
        self.assertIn('"id": 20', prompts[0])
        self.assertNotIn('"id": 21', prompts[0])
        self.assertIn('"id": 21', prompts[1])
        self.assertIn('"id": 40', prompts[1])
        self.assertNotIn('"id": 20', prompts[1])
        self.assertNotIn('"id": 41', prompts[1])
        self.assertIn('"id": 41', prompts[2])
        self.assertIn('"id": 45', prompts[2])
        self.assertNotIn('"id": 40', prompts[2])
        self.assertEqual(45, corrected.count("-->"))
        self.assertIn("1\n00:00:01,000 --> 00:00:01,900\n正字1", corrected)
        self.assertIn("45\n00:00:45,000 --> 00:00:45,900\n正字45", corrected)
        self.assertEqual(0, progress_events[0][0])
        self.assertEqual(45, progress_events[0][1])
        self.assertEqual((45, 45), progress_events[-1][:2])
        self.assertIn("完成", progress_events[-1][2])

    def test_correct_srt_content_repairs_extra_id_before_accepting_batch(self):
        invalid_output = {
            "items": [
                {"id": 1, "text": "今天我们来看张三的故事"},
                {"id": 2, "text": "他来到北京找李四"},
                {"id": 99, "text": "不属于当前批次"},
            ]
        }
        repaired_output = {
            "items": [
                {"id": 1, "text": "今天我们来看张三的故事"},
                {"id": 2, "text": "他来到北京找李四"},
            ]
        }

        with (
            mock.patch("app.services.subtitle_corrector._ensure_llm_providers_registered"),
            mock.patch(
                "app.services.subtitle_corrector._run_async_safely",
                side_effect=[
                    json.dumps(invalid_output, ensure_ascii=False),
                    json.dumps(repaired_output, ensure_ascii=False),
                ],
            ) as run_llm,
        ):
            corrected = corrector.correct_srt_content(
                SAMPLE_SRT,
                provider="openai",
                repair_attempts=2,
            )

        self.assertEqual(2, run_llm.call_count)
        self.assertIn("额外字幕条目", run_llm.call_args_list[1].kwargs["prompt"])
        self.assertIn("北京", corrected)

    def test_correct_srt_content_repairs_duplicate_id_before_accepting_batch(self):
        invalid_output = {
            "items": [
                {"id": 1, "text": "今天我们来看张三的故事"},
                {"id": 1, "text": "重复的张三故事"},
                {"id": 2, "text": "他来到北京找李四"},
            ]
        }
        repaired_output = {
            "items": [
                {"id": 1, "text": "今天我们来看张三的故事"},
                {"id": 2, "text": "他来到北京找李四"},
            ]
        }

        with (
            mock.patch("app.services.subtitle_corrector._ensure_llm_providers_registered"),
            mock.patch(
                "app.services.subtitle_corrector._run_async_safely",
                side_effect=[
                    json.dumps(invalid_output, ensure_ascii=False),
                    json.dumps(repaired_output, ensure_ascii=False),
                ],
            ) as run_llm,
        ):
            corrected = corrector.correct_srt_content(
                SAMPLE_SRT,
                provider="openai",
                repair_attempts=2,
            )

        self.assertEqual(2, run_llm.call_count)
        self.assertIn("重复字幕条目", run_llm.call_args_list[1].kwargs["prompt"])
        self.assertIn("北京", corrected)

    def test_correct_srt_content_repairs_malformed_items_before_accepting_batch(self):
        repaired_output = {
            "items": [
                {"id": 1, "text": "今天我们来看张三的故事"},
                {"id": 2, "text": "他来到北京找李四"},
            ]
        }
        scenarios = {
            "malformed item": {
                "items": [
                    {"id": 1, "text": "今天我们来看张三的故事"},
                    "不是对象",
                    {"id": 2, "text": "他来到北京找李四"},
                ]
            },
            "missing id": {
                "items": [
                    {"id": 1, "text": "今天我们来看张三的故事"},
                    {"text": "缺少 id 的额外条目"},
                    {"id": 2, "text": "他来到北京找李四"},
                ]
            },
            "non-numeric id": {
                "items": [
                    {"id": 1, "text": "今天我们来看张三的故事"},
                    {"id": "abc", "text": "非数字 id 的额外条目"},
                    {"id": 2, "text": "他来到北京找李四"},
                ]
            },
        }

        for name, invalid_output in scenarios.items():
            with self.subTest(name=name):
                with (
                    mock.patch("app.services.subtitle_corrector._ensure_llm_providers_registered"),
                    mock.patch(
                        "app.services.subtitle_corrector._run_async_safely",
                        side_effect=[
                            json.dumps(invalid_output, ensure_ascii=False),
                            json.dumps(repaired_output, ensure_ascii=False),
                        ],
                    ) as run_llm,
                ):
                    corrected = corrector.correct_srt_content(
                        SAMPLE_SRT,
                        provider="openai",
                        repair_attempts=2,
                    )

                self.assertEqual(2, run_llm.call_count)
                repair_prompt = run_llm.call_args_list[1].kwargs["prompt"]
                self.assertIn("无法通过校验", repair_prompt)
                self.assertIn("上一轮输出", repair_prompt)
                self.assertIn("北京", corrected)

    def test_parse_corrections_rejects_non_numeric_mapping_key(self):
        with self.assertRaisesRegex(
            corrector.SubtitleCorrectionError,
            "无法解析的字幕 id: abc",
        ):
            corrector._parse_corrections(
                json.dumps({"1": "今天我们来看张三的故事", "abc": "畸形条目"}, ensure_ascii=False),
                {1},
            )

    def test_correct_srt_content_ignores_progress_callback_errors(self):
        llm_output = {
            "items": [
                {"id": 1, "text": "今天我们来看张三的故事"},
                {"id": 2, "text": "他来到北京找李四"},
            ]
        }

        def broken_callback(completed, total, message):
            raise RuntimeError(f"callback failed at {completed}/{total}: {message}")

        with (
            mock.patch("app.services.subtitle_corrector._ensure_llm_providers_registered"),
            mock.patch(
                "app.services.subtitle_corrector._run_async_safely",
                return_value=json.dumps(llm_output, ensure_ascii=False),
            ),
        ):
            corrected = corrector.correct_srt_content(
                SAMPLE_SRT,
                provider="openai",
                progress_callback=broken_callback,
            )

        self.assertIn("北京", corrected)

    def test_correct_subtitle_file_forwards_batch_repair_and_progress_options(self):
        progress_callback = mock.Mock()

        with tempfile.TemporaryDirectory() as tmp_dir:
            input_file = Path(tmp_dir) / "input.srt"
            output_file = Path(tmp_dir) / "output.srt"
            input_file.write_text(SAMPLE_SRT, encoding="utf-8")

            with (
                mock.patch(
                    "app.services.subtitle_corrector.correct_srt_content",
                    return_value=SAMPLE_SRT,
                ) as correct_srt_content,
                mock.patch(
                    "app.services.subtitle_corrector.write_srt_file",
                    return_value=str(output_file),
                ),
            ):
                result_path = corrector.correct_subtitle_file(
                    str(input_file),
                    str(output_file),
                    provider="openai",
                    api_key="sk-test",
                    base_url="https://llm.example/v1",
                    temperature=0.2,
                    batch_size=7,
                    repair_attempts=4,
                    progress_callback=progress_callback,
                )

        self.assertEqual(str(output_file), result_path)
        call_kwargs = correct_srt_content.call_args.kwargs
        self.assertEqual(7, call_kwargs["batch_size"])
        self.assertEqual(4, call_kwargs["repair_attempts"])
        self.assertIs(progress_callback, call_kwargs["progress_callback"])
        self.assertEqual("openai", call_kwargs["provider"])

    def test_correct_srt_content_repairs_invalid_json_before_accepting_batch(self):
        repaired_output = {
            "items": [
                {"id": 1, "text": "今天我们来看张三的故事"},
                {"id": 2, "text": "他来到北京找李四"},
            ]
        }

        with (
            mock.patch("app.services.subtitle_corrector._ensure_llm_providers_registered"),
            mock.patch(
                "app.services.subtitle_corrector._run_async_safely",
                side_effect=["不是 JSON", json.dumps(repaired_output, ensure_ascii=False)],
            ) as run_llm,
        ):
            corrected = corrector.correct_srt_content(
                SAMPLE_SRT,
                provider="openai",
                repair_attempts=2,
            )

        self.assertEqual(2, run_llm.call_count)
        repair_prompt = run_llm.call_args_list[1].kwargs["prompt"]
        self.assertIn("无法通过校验", repair_prompt)
        self.assertIn("上一轮输出", repair_prompt)
        self.assertIn("北京", corrected)

    def test_correct_srt_content_wraps_llm_errors_with_batch_range(self):
        large_srt = "\n\n".join(
            [
                f"{index}\n00:00:{index:02d},000 --> 00:00:{index:02d},900\n字幕{index}"
                for index in range(1, 26)
            ]
        )

        with (
            mock.patch("app.services.subtitle_corrector._ensure_llm_providers_registered"),
            mock.patch(
                "app.services.subtitle_corrector._run_async_safely",
                side_effect=TimeoutError("gateway timeout"),
            ),
        ):
            with self.assertRaisesRegex(
                corrector.SubtitleCorrectionError,
                r"批次 1/2.*条目 1-20.*gateway timeout",
            ):
                corrector.correct_srt_content(large_srt, provider="openai", batch_size=20)


if __name__ == "__main__":
    unittest.main()
