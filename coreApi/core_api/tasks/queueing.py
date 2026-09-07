from __future__ import annotations

from core_api.config import Settings, get_cached_settings


def queue_for_task_type(task_type: str, settings: Settings | None = None) -> str:
    """把原子任务映射到稳定的角色队列，ASR 不进入默认队列。"""

    current = settings or get_cached_settings()
    role = {
        "asr": "asr",
        "audio_understanding": "analysis",
        "video_analysis": "analysis",
        "script_generation": "analysis",
        "tts": "tts",
        "video_render": "render",
    }.get(task_type, "default")
    return f"{current.celery_queue_prefix}.{role}"
