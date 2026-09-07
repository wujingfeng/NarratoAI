from core_api.tasks.queueing import queue_for_task_type


def test_asr_queue_is_physically_separate(settings):
    assert queue_for_task_type("asr", settings) == "narrato.core.asr"
    assert (
        queue_for_task_type("audio_understanding", settings)
        == "narrato.core.analysis"
    )
    assert queue_for_task_type("video_analysis", settings) == "narrato.core.analysis"
    assert queue_for_task_type("script_generation", settings) == "narrato.core.analysis"
    assert queue_for_task_type("tts", settings) == "narrato.core.tts"
    assert queue_for_task_type("video_render", settings) == "narrato.core.render"
    assert queue_for_task_type("media_probe", settings) == "narrato.core.default"
