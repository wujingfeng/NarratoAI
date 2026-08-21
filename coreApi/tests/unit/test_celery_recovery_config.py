from core_api.celery_app import create_celery_app
from core_api.tasks.celery_tasks import publish_callback_outbox, wake_core_task


def test_worker_lost_delivery_and_recovery_scanner_are_configured(settings):
    """Worker 异常退出时 wake 可重投，且生产 Beat 会扫描数据库恢复。"""

    app = create_celery_app(settings)
    assert app.conf.task_acks_late is True
    assert app.conf.task_reject_on_worker_lost is True
    assert app.conf.worker_prefetch_multiplier == 1
    assert "core_api.tasks.celery_tasks" in app.conf.imports
    assert wake_core_task.acks_late is True
    assert wake_core_task.reject_on_worker_lost is True
    assert app.conf.beat_schedule["recover-stalled-core-tasks"] == {
        "task": "core.tasks.recover_stalled",
        "schedule": 15.0,
    }
    assert app.conf.beat_schedule["reconcile-core-artifacts"] == {
        "task": "core.tasks.reconcile_artifacts",
        "schedule": 15.0,
    }
    assert app.conf.beat_schedule["publish-core-callback-outbox"] == {
        "task": "core.tasks.publish_callback_outbox",
        "schedule": 5.0,
    }


def test_invalid_callback_configuration_does_not_touch_outbox(
    settings, monkeypatch
):
    import core_api.tasks.celery_tasks as tasks_module

    invalid = settings.model_copy(
        update={"callback_url": "https://api.example.com/callback"}
    )
    monkeypatch.setattr(tasks_module, "get_cached_settings", lambda: invalid)
    monkeypatch.setattr(
        tasks_module,
        "get_engine",
        lambda _settings: (_ for _ in ()).throw(
            AssertionError("invalid callback configuration touched the database")
        ),
    )

    publish_callback_outbox.run()
