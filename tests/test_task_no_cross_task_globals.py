import inspect
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from app.models.schema import MaterialInfo, VideoClipParams
from app.runtime.task_workspace import TaskWorkspace
from app.services import jianying_task, material, task


def test_render_state_is_local_to_each_invocation():
    for render_function in (task.start_subclip, task.start_subclip_unified):
        source = inspect.getsource(render_function)
        assert "global merged_audio_path" not in source
        assert "global merged_subtitle_path" not in source


def test_renderers_do_not_scan_shared_subtitle_directory(tmp_path: Path):
    matching_subtitle = tmp_path / "episode_fun_asr_20260716090000.srt"
    matching_subtitle.write_text("shared subtitle", encoding="utf-8")
    params = VideoClipParams(video_origin_path="/uploads/episode.mp4")

    with patch.object(task.utils, "subtitle_dir", return_value=str(tmp_path)):
        assert task._get_original_subtitle_paths(params) == []
    with patch.object(jianying_task.utils, "subtitle_dir", return_value=str(tmp_path)):
        assert jianying_task._get_original_subtitle_paths(params) == []


def test_renderers_keep_explicit_subtitle_assets():
    params = VideoClipParams(
        video_origin_path="/uploads/episode.mp4",
        original_subtitle_path="/uploads/episode-main.srt",
        original_subtitle_paths=[
            "/uploads/episode-extra.srt",
            "/uploads/episode-main.srt",
        ],
    )

    expected = ["/uploads/episode-extra.srt", "/uploads/episode-main.srt"]
    assert task._get_original_subtitle_paths(params) == expected
    assert jianying_task._get_original_subtitle_paths(params) == expected


def test_clip_videos_uses_task_directory_instead_of_shared_temp():
    with (
        patch.dict(material.config.app, {"material_directory": ""}, clear=False),
        patch.object(material.utils, "task_dir", return_value="/workspaces/task-a"),
        patch.object(material, "save_clip_video", return_value="/workspaces/task-a/clip.mp4") as save_clip,
    ):
        material.clip_videos("task-a", ["00:00:00,000-00:00:01,000"], "/input.mp4")

    save_clip.assert_called_once_with(
        timestamp="00:00:00,000-00:00:01,000",
        origin_video="/input.mp4",
        save_dir="/workspaces/task-a",
    )


def test_download_videos_uses_task_directory_by_default():
    item = MaterialInfo(provider="pexels", url="https://example.test/video.mp4", duration=5)
    with (
        patch.dict(material.config.app, {"material_directory": ""}, clear=False),
        patch.object(material.utils, "task_dir", return_value="/workspaces/task-a"),
        patch.object(material, "search_videos_pexels", return_value=[item]),
        patch.object(material, "save_video", return_value="/workspaces/task-a/video.mp4") as save_video,
    ):
        material.download_videos("task-a", ["test"], audio_duration=1)

    save_video.assert_called_once_with(
        video_url="https://example.test/video.mp4",
        save_dir="/workspaces/task-a",
    )


def test_same_task_attempts_clip_into_distinct_workspace_directories(tmp_path: Path):
    first = TaskWorkspace.create(tmp_path, "task-a", 1)
    second = TaskWorkspace.create(tmp_path, "task-a", 2)

    def fake_save_clip_video(timestamp: str, origin_video: str, save_dir: str) -> str:
        output = Path(save_dir) / "same-timestamp.mp4"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(str(Path(save_dir)), encoding="utf-8")
        return str(output)

    def run_clip(workspace: TaskWorkspace) -> str:
        result = material.clip_videos(
            "task-a",
            ["00:00:00,000-00:00:01,000"],
            "/input.mp4",
            workspace=workspace,
        )
        return result[1]

    with patch.object(material, "save_clip_video", side_effect=fake_save_clip_video):
        with ThreadPoolExecutor(max_workers=2) as executor:
            first_path, second_path = executor.map(run_clip, (first, second))

    assert first_path != second_path
    assert Path(first_path).is_relative_to(first.temp_dir)
    assert Path(second_path).is_relative_to(second.temp_dir)


def test_configured_material_directory_is_scoped_per_task(tmp_path: Path):
    configured_dir = tmp_path / "materials"
    configured_dir.mkdir()
    item = MaterialInfo(provider="pexels", url="https://example.test/video.mp4", duration=5)
    saved_directories: list[str] = []

    def fake_save_video(video_url: str, save_dir: str) -> str:
        saved_directories.append(save_dir)
        return str(Path(save_dir) / "video.mp4")

    def run_download(task_id: str) -> None:
        material.download_videos(task_id, ["test"], audio_duration=1)

    with (
        patch.dict(material.config.app, {"material_directory": str(configured_dir)}, clear=False),
        patch.object(material, "search_videos_pexels", return_value=[item]),
        patch.object(material, "save_video", side_effect=fake_save_video),
    ):
        with ThreadPoolExecutor(max_workers=2) as executor:
            list(executor.map(run_download, ("task-a", "task-b")))

    assert set(saved_directories) == {
        str(configured_dir / "task-a"),
        str(configured_dir / "task-b"),
    }


def test_material_api_key_selection_has_no_module_global_counter():
    source = inspect.getsource(material)
    assert "requested_count =" not in source
    assert "global requested_count" not in source


def test_material_api_key_selection_uses_explicit_request_index():
    with patch.dict(material.config.app, {"pexels_api_keys": ["first", "second"]}, clear=False):
        with ThreadPoolExecutor(max_workers=4) as executor:
            selected = list(
                executor.map(
                    lambda index: material.get_api_key("pexels_api_keys", request_index=index),
                    (0, 1, 2, 3),
                )
            )

    assert selected == ["first", "second", "first", "second"]
