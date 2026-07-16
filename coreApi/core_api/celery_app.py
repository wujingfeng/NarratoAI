from __future__ import annotations

from celery import Celery

from core_api.config import Settings, get_cached_settings


def create_celery_app(settings: Settings | None = None) -> Celery:
    """创建使用 Core 专属 Broker、键和队列前缀的 Celery 应用。"""

    current = settings or get_cached_settings()
    app = Celery("narrato_core", broker=current.celery_broker_url)
    app.conf.update(
        task_default_queue=f"{current.celery_queue_prefix}.default",
        task_create_missing_queues=True,
        broker_transport_options={
            "global_keyprefix": f"{current.redis_key_prefix}celery:"
        },
        result_backend=None,
    )
    return app


celery_app = create_celery_app()
