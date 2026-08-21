from __future__ import annotations

from celery import Celery
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from narrato_api.assets.models import Asset
from narrato_api.auth.models import User
from narrato_api.config import Settings
from narrato_api.database import Base
from narrato_api.deletion.celery_tasks import register_deletion_tasks
from narrato_api.projects.models import DeletionJob, Project


class FakeOssClient:
    def __init__(self) -> None:
        self.deleted: list[tuple[str, str]] = []

    def delete_object(self, bucket: str, object_key: str) -> None:
        self.deleted.append((bucket, object_key))


def test_deletion_services_wire_oss_delete_credentials(tmp_path) -> None:
    import narrato_api.deletion.celery_tasks as task_module

    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'services.db'}",
        oss_endpoint="oss-cn-shanghai.aliyuncs.com",
        oss_access_key_id="access-key",
        oss_access_key_secret="access-secret",
    )

    engine, _sessions, oss_client = task_module._services(settings)
    try:
        assert oss_client.access_key_id == "access-key"
        assert oss_client.access_key_secret == "access-secret"
    finally:
        engine.dispose()


def test_registered_deletion_sweep_executes_pending_and_retryable_jobs(
    tmp_path, monkeypatch
) -> None:
    import narrato_api.deletion.celery_tasks as task_module

    engine = create_engine(f"sqlite:///{tmp_path / 'deletion-sweep.db'}")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    with sessions.begin() as session:
        session.add(User(id="usr_1", email="owner@example.test", password_hash="hash"))
        for index, status in enumerate(("pending", "retryable_failed"), start=1):
            project_id = f"prj_{index}"
            session.add(
                Project(
                    id=project_id,
                    user_id="usr_1",
                    product="short_drama",
                    status="deleting",
                )
            )
            session.add(
                DeletionJob(
                    id=f"dlj_{index}",
                    project_id=project_id,
                    user_id="usr_1",
                    status=status,
                )
            )
            session.add(
                Asset(
                    id=f"ast_{index}",
                    user_id="usr_1",
                    project_id=project_id,
                    asset_type="video",
                    status="ready",
                    filename=f"video-{index}.mp4",
                    bucket="media",
                    object_key=f"owner/video-{index}.mp4",
                    cdn_url=f"https://cdn.example.test/video-{index}.mp4",
                    size_bytes=1,
                )
            )
    oss = FakeOssClient()
    monkeypatch.setattr(
        task_module, "_services", lambda _settings: (engine, sessions, oss)
    )
    app = Celery("deletion-test")
    register_deletion_tasks(app, Settings(database_url="sqlite://"))

    assert app.tasks["narrato.deletion.sweep"].run(limit=10) == 2
    assert oss.deleted == [
        ("media", "owner/video-1.mp4"),
        ("media", "owner/video-2.mp4"),
    ]
    with sessions() as session:
        assert {
            job.status for job in session.query(DeletionJob).order_by(DeletionJob.id)
        } == {"completed"}
        assert {
            project.status for project in session.query(Project).order_by(Project.id)
        } == {"deleted"}
