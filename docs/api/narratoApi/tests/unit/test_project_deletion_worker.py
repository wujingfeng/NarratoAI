from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from narrato_api.assets.models import Asset
from narrato_api.auth.models import User
from narrato_api.database import Base
from narrato_api.projects.models import DeletionJob, Project


class FakeOssClient:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.deleted: list[tuple[str, str]] = []

    def delete_object(self, bucket: str, object_key: str) -> None:
        self.deleted.append((bucket, object_key))
        if self.fail:
            raise RuntimeError("temporary OSS failure")


def _seed(session: Session) -> None:
    session.add(User(id="usr_1", email="owner@example.com", password_hash="hash"))
    session.add(
        Project(id="prj_1", user_id="usr_1", product="short_drama", status="deleting")
    )
    session.add(
        DeletionJob(id="dlj_1", project_id="prj_1", user_id="usr_1", status="pending")
    )
    session.add_all(
        [
            Asset(
                id="ast_1",
                user_id="usr_1",
                project_id="prj_1",
                asset_type="video",
                status="ready",
                filename="video.mp4",
                bucket="media",
                object_key="owner/video.mp4",
                cdn_url="https://cdn.example.test/owner/video.mp4",
                size_bytes=1,
            ),
            Asset(
                id="ast_2",
                user_id="usr_1",
                project_id="prj_1",
                asset_type="subtitle",
                status="ready",
                filename="video.srt",
                bucket="media",
                object_key="owner/video.srt",
                cdn_url="https://cdn.example.test/owner/video.srt",
                size_bytes=1,
            ),
        ]
    )
    session.commit()


def test_pending_deletion_worker_deletes_only_owned_assets_then_retains_terminal_audit() -> (
    None
):
    from narrato_api.deletion.tasks import ProjectDeletionWorker

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        _seed(session)
    oss = FakeOssClient()
    worker = ProjectDeletionWorker(sessionmaker(bind=engine), oss)

    assert worker.run_pending_job("dlj_1") is True
    assert oss.deleted == [("media", "owner/video.mp4"), ("media", "owner/video.srt")]

    with Session(engine) as session:
        job = session.get(DeletionJob, "dlj_1")
        project = session.get(Project, "prj_1")
        assert job is not None and job.status == "completed"
        assert project is not None and project.status == "deleted"
        assert session.query(Asset).filter_by(project_id="prj_1").count() == 2


def test_pending_deletion_worker_records_retryable_failure_without_deleting_business_records() -> (
    None
):
    from narrato_api.deletion.tasks import ProjectDeletionWorker

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        _seed(session)
    worker = ProjectDeletionWorker(sessionmaker(bind=engine), FakeOssClient(fail=True))

    assert worker.run_pending_job("dlj_1") is False

    with Session(engine) as session:
        job = session.get(DeletionJob, "dlj_1")
        project = session.get(Project, "prj_1")
        assert job is not None and job.status == "retryable_failed"
        assert project is not None and project.status == "deleting"
        assert session.query(Asset).filter_by(project_id="prj_1").count() == 2


def test_worker_retries_retryable_failed_jobs_idempotently() -> None:
    from narrato_api.deletion.tasks import ProjectDeletionWorker

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        _seed(session)
        session.get(DeletionJob, "dlj_1").status = "retryable_failed"
        session.commit()
    oss = FakeOssClient()

    assert ProjectDeletionWorker(sessionmaker(bind=engine), oss).run_pending_job(
        "dlj_1"
    )
    assert oss.deleted == [("media", "owner/video.mp4"), ("media", "owner/video.srt")]
    with Session(engine) as session:
        assert session.get(DeletionJob, "dlj_1").status == "completed"
        assert session.get(Project, "prj_1").status == "deleted"


def test_worker_waits_for_issued_upload_policy_to_expire_before_cleanup() -> None:
    from narrato_api.deletion.tasks import ProjectDeletionWorker

    now = datetime(2026, 8, 5, 8, 0, tzinfo=timezone.utc)
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        _seed(session)
        session.get(Asset, "ast_1").reservation_expires_at = now + timedelta(minutes=10)
        session.commit()
    oss = FakeOssClient()
    worker = ProjectDeletionWorker(sessionmaker(bind=engine), oss, now=lambda: now)

    assert worker.run_pending_job("dlj_1") is False
    assert oss.deleted == []
    with Session(engine) as session:
        job = session.get(DeletionJob, "dlj_1")
        project = session.get(Project, "prj_1")
        assert job is not None and (job.status, job.attempt_count) == ("pending", 0)
        assert project is not None and project.status == "deleting"
        session.get(Asset, "ast_1").reservation_expires_at = now - timedelta(seconds=1)
        session.commit()

    assert worker.run_pending_job("dlj_1") is True
    assert oss.deleted == [("media", "owner/video.mp4"), ("media", "owner/video.srt")]
