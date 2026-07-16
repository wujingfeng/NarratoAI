from __future__ import annotations

from core_api.celery_app import celery_app


@celery_app.task(name="core.tasks.wake", ignore_result=True)
def wake_core_task(task_id: str) -> None:
    """仅唤醒数据库任务；执行状态始终以 PostgreSQL 为准。"""

    del task_id
