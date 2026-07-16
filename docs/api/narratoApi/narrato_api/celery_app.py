from __future__ import annotations

from celery import Celery

from narrato_api.config import Settings, get_cached_settings


def create_celery_app(settings: Settings | None = None) -> Celery:
    """创建使用业务专属 Broker 命名空间且无结果后端的 Celery。"""

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
    return app


celery_app = create_celery_app()
