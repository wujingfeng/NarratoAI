from __future__ import annotations

from celery import Celery

from narrato_api.config import Settings, get_cached_settings


def create_celery_app(settings: Settings | None = None) -> Celery:
    """创建绑定给定 Settings 的 Celery producer/worker app。"""

    current = settings or get_cached_settings()
    app = Celery("narrato_business", broker=current.celery_broker_url)
    app.conf.update(
        task_default_queue=f"{current.celery_queue_prefix}.default",
        task_create_missing_queues=True,
        broker_transport_options={
            "global_keyprefix": f"{current.redis_key_prefix}celery:"
        },
        result_backend=None,
        task_acks_late=True,
        task_reject_on_worker_lost=True,
        worker_prefetch_multiplier=1,
    )
    from narrato_api.auth.tasks import register_auth_tasks
    from narrato_api.deletion.celery_tasks import register_deletion_tasks
    from narrato_api.products.ai_video_tasks import register_ai_video_tasks
    from narrato_api.workflows.tasks import register_workflow_tasks

    register_auth_tasks(app, current)
    register_deletion_tasks(app, current)
    register_ai_video_tasks(app, current)
    register_workflow_tasks(app, current)
    app.conf.beat_schedule = {
        "workflow-outbox-replay": {
            "task": "narrato.workflows.replay_outbox",
            "schedule": current.workflow_outbox_replay_interval_seconds,
        },
        "workflow-core-poll": {
            "task": "narrato.workflows.poll_core_tasks",
            "schedule": current.workflow_poll_interval_seconds,
        },
        "project-deletion-sweep": {
            "task": "narrato.deletion.sweep",
            "schedule": current.project_deletion_sweep_interval_seconds,
        },
        "ai-video-provider-poll": {
            "task": "narrato.ai_video.poll_tasks",
            "schedule": current.ai_video_poll_interval_seconds,
            "kwargs": {"limit": current.ai_video_poll_batch_size},
        },
    }
    app.finalize(auto=True)
    return app


# Worker deployment entrypoint; Web apps create their own instance in lifespan.
celery_app = create_celery_app()
