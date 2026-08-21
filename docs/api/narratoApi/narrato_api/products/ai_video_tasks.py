"""Business API 自动收敛模型任务。

所有供应商轮询、结果转存 OSS、Core 视频信息探测及最终结算都由 Celery
Worker 负责；浏览器只读取 Business API 的本地任务状态。
"""
from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass
from datetime import timedelta
from pathlib import PurePosixPath

from celery import Celery
from sqlalchemy import and_, or_, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from narrato_api.config import Settings
from narrato_api.database import create_database_engine
from narrato_api.integrations.core_client import CoreClientError, HttpCoreClient
from narrato_api.integrations.oss_client import HttpOssClient, OssClientError
from narrato_api.products.providers import ProviderError, ProviderRegistry

logger = logging.getLogger(__name__)
_ACTIVE_STATES = ("submitting", "queued", "processing", "finalizing")


def _ai():
    from narrato_api.products import ai_video
    return ai_video


@dataclass(frozen=True, slots=True)
class PollClaim:
    task_id: str
    lease_token: str


def _services(settings: Settings) -> tuple[Engine, sessionmaker[Session], ProviderRegistry, HttpOssClient, HttpCoreClient]:
    engine = create_database_engine(settings.database_url, settings.database_connect_timeout_seconds, settings.database_read_timeout_seconds)
    return (
        engine,
        sessionmaker(bind=engine, expire_on_commit=False),
        ProviderRegistry(),
        HttpOssClient(endpoint=settings.oss_endpoint, access_key_id=settings.oss_access_key_id, access_key_secret=settings.oss_access_key_secret, cdn_public_base_url=settings.cdn_public_base_url),
        HttpCoreClient(base_url=str(settings.core_base_url), request_token=settings.core_request_token),
    )


class AiVideoPollingWorker:
    """兼容旧任务名的通用模型 Worker。"""

    def __init__(self, sessions: sessionmaker[Session], provider: ProviderRegistry, settings: Settings, *, oss_client: HttpOssClient | None = None, core_client: HttpCoreClient | None = None) -> None:
        self._sessions = sessions
        self._provider = provider
        self._settings = settings
        self._oss = oss_client
        self._core = core_client

    def claim_due_tasks(self, *, limit: int) -> list[PollClaim]:
        ai = _ai()
        now = ai.utc_now()
        lease_until = now + timedelta(seconds=self._settings.ai_video_poll_lease_seconds)
        submit_recovery_before = now - timedelta(seconds=self._settings.ai_video_submission_recovery_delay_seconds)
        normal_due = or_(ai.ModelTask.next_poll_at.is_(None), ai.ModelTask.next_poll_at <= now)
        statement = (
            select(ai.ModelTask)
            .where(
                ai.ModelTask.status.in_(_ACTIVE_STATES),
                or_(ai.ModelTask.poll_lease_until.is_(None), ai.ModelTask.poll_lease_until < now),
                normal_due,
                or_(
                    ai.ModelTask.status.in_(("queued", "processing", "finalizing")),
                    and_(ai.ModelTask.status == "submitting", ai.ModelTask.created_at <= submit_recovery_before),
                ),
            )
            .order_by(ai.ModelTask.next_poll_at, ai.ModelTask.created_at, ai.ModelTask.id)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        claims: list[PollClaim] = []
        with self._sessions.begin() as session:
            for task in session.scalars(statement):
                token = secrets.token_hex(24)
                task.poll_lease_token = token
                task.poll_lease_until = lease_until
                claims.append(PollClaim(task.id, token))
        return claims

    def run_due_tasks(self, *, limit: int) -> int:
        processed = 0
        for _ in range(limit):
            claims = self.claim_due_tasks(limit=1)
            if not claims:
                break
            self.process_claim(claims[0])
            processed += 1
        return processed

    def process_claim(self, claim: PollClaim) -> bool:
        ai = _ai()
        with self._sessions() as session:
            task = session.get(ai.ModelTask, claim.task_id)
            if task is None or task.poll_lease_token != claim.lease_token or task.status not in _ACTIVE_STATES:
                return False
            model = session.get(ai.Model, task.model_id)
            mode = session.get(ai.ModelPlayMode, task.play_mode_id)
            provider = session.get(ai.ModelPlayModeProvider, task.provider_id)
            if model is None or mode is None or provider is None:
                snapshot = None
            else:
                snapshot = (task, model, mode, provider)
        if snapshot is None:
            self._fail(claim, "MODEL_PROVIDER_NOT_AVAILABLE", "Model provider configuration is unavailable")
            return True
        task, model, mode, provider = snapshot
        try:
            if task.status == "finalizing":
                self._finalize(claim)
            elif task.provider_task_id:
                result = self._provider.get(provider.provider_code).get_status(model=model, play_mode=mode, provider=provider, provider_task_id=task.provider_task_id)
                self._persist_result(claim, result)
            else:
                with self._sessions() as submit_session:
                    task_current = submit_session.get(ai.ModelTask, claim.task_id)
                    assert task_current is not None
                    result = ai._submit_task(self._provider, submit_session, task_current)
                self._persist_result(claim, result, submitted=True)
        except ProviderError as exc:
            self._reschedule_error(claim, str(exc))
        except (OssClientError, CoreClientError) as exc:
            self._reschedule_error(claim, str(exc))
        except Exception:
            logger.exception("model_task_worker_unexpected_error task_id=%s", claim.task_id)
            self._reschedule_error(claim, "unexpected worker error")
        return True

    def _persist_result(self, claim: PollClaim, result: object, *, submitted: bool = False) -> None:
        ai = _ai()
        with self._sessions.begin() as session:
            task = self._locked(session, claim)
            if task is None:
                return
            if submitted:
                task.submitted_at = ai.utc_now()
                task.provider_request = ai._provider_payload(task, ai._task_assets_payload(session, task))
            task.last_polled_at = ai.utc_now()
            ai._stage_provider_result(session, task, result)
            self._schedule_if_active(task)

    def _finalize(self, claim: PollClaim) -> None:
        ai = _ai()
        with self._sessions() as session:
            task = session.get(ai.ModelTask, claim.task_id)
            if task is None or task.poll_lease_token != claim.lease_token:
                return
            output_rows = list(session.scalars(select(ai.ModelTaskOutput).where(ai.ModelTaskOutput.task_id == task.id).order_by(ai.ModelTaskOutput.sort_order)))
            task_type = task.task_type
        if task_type == "llm":
            with self._sessions.begin() as session:
                task = self._locked(session, claim)
                if task is not None:
                    ai._mark_completed(session, task)
            return
        if self._oss is None or self._core is None:
            raise OssClientError("model output transfer dependencies are not configured")
        for output in output_rows:
            if output.output_type == "text" or output.cdn_url:
                continue
            if not output.provider_url:
                continue
            extension = self._extension(output.provider_url, output.output_type)
            stored = self._oss.copy_from_url(bucket=self._settings.oss_bucket, object_key=f"narrato/model-results/{task.id}/{output.sort_order}.{extension}", source_url=output.provider_url, content_type=output.content_type)
            with self._sessions.begin() as session:
                row = session.get(ai.ModelTaskOutput, output.id)
                locked_task = self._locked(session, claim)
                if row is None or locked_task is None:
                    return
                row.oss_bucket = stored.bucket
                row.oss_object_key = stored.object_key
                row.cdn_url = stored.cdn_url
                row.size_bytes = stored.size_bytes
                row.content_type = stored.content_type
        if task_type == "video":
            self._probe_videos(claim)
        with self._sessions.begin() as session:
            task = self._locked(session, claim)
            if task is None:
                return
            rows = list(session.scalars(select(ai.ModelTaskOutput).where(ai.ModelTaskOutput.task_id == task.id).order_by(ai.ModelTaskOutput.sort_order)))
            if task.task_type == "image":
                completed = [row for row in rows if row.cdn_url]
                expected = task.actual_output_image_count if task.actual_output_image_count is not None else len(rows)
                if not completed:
                    ai._fail_task(session, task, code="MODEL_OUTPUT_TRANSFER_FAILED", message="No generated image could be transferred")
                else:
                    task.actual_output_image_count = len(completed)
                    ai._mark_completed(session, task, partial=len(completed) < expected)
            elif task.task_type == "video":
                if not rows:
                    ai._fail_task(session, task, code="MODEL_OUTPUT_MISSING", message="Video provider returned no output")
                    return
                if any(row.cdn_url is None or row.duration_seconds is None for row in rows):
                    self._schedule(task)
                    return
                task.actual_output_duration_seconds = sum(float(row.duration_seconds or 0) for row in rows)
                ai._mark_completed(session, task)
            else:
                ai._mark_completed(session, task)

    def _probe_videos(self, claim: PollClaim) -> None:
        ai = _ai()
        assert self._core is not None
        with self._sessions() as session:
            task = session.get(ai.ModelTask, claim.task_id)
            if task is None:
                return
            rows = list(session.scalars(select(ai.ModelTaskOutput).where(ai.ModelTaskOutput.task_id == task.id).order_by(ai.ModelTaskOutput.sort_order)))
        for output in rows:
            if output.output_type != "video" or not output.cdn_url or output.duration_seconds is not None:
                continue
            if output.core_task_id:
                result = self._core.get_probe_result(output.core_task_id)
            else:
                result = self._core.probe_media(source_url=output.cdn_url, media_type="video", declared_extension=self._extension(output.oss_object_key or output.cdn_url, "video"), caller_task_id=f"{claim.task_id}:{output.id}")
            with self._sessions.begin() as session:
                row = session.get(ai.ModelTaskOutput, output.id)
                task = self._locked(session, claim)
                if row is None or task is None:
                    return
                if result.valid is False:
                    ai._fail_task(session, task, code="MODEL_OUTPUT_MEDIA_INVALID", message="Generated video media information is invalid")
                    return
                row.core_task_id = result.core_task_id
                if result.valid is True and result.duration_seconds is not None:
                    row.duration_seconds = result.duration_seconds

    def _reschedule_error(self, claim: PollClaim, reason: str) -> None:
        ai = _ai()
        with self._sessions.begin() as session:
            task = self._locked(session, claim)
            if task is None:
                return
            task.last_polled_at = ai.utc_now()
            task.poll_error_count += 1
            if task.poll_error_count >= self._settings.ai_video_poll_max_errors:
                ai._fail_task(session, task, code="MODEL_PROVIDER_UNAVAILABLE", message="Model task could not be completed after repeated retries")
                logger.error("model_task_poll_exhausted task_id=%s reason=%s", task.id, reason)
                return
            delay = min(self._settings.ai_video_poll_interval_seconds * (2 ** (task.poll_error_count - 1)), self._settings.ai_video_poll_max_backoff_seconds)
            task.next_poll_at = ai.utc_now() + timedelta(seconds=delay)
            task.poll_lease_token = None
            task.poll_lease_until = None
            task.error_code = "MODEL_TASK_RETRYING"
            task.error_message = "Model task is temporarily unavailable"
            logger.warning("model_task_retry task_id=%s reason=%s", task.id, reason)

    def _fail(self, claim: PollClaim, code: str, message: str) -> None:
        ai = _ai()
        with self._sessions.begin() as session:
            task = self._locked(session, claim)
            if task is not None:
                ai._fail_task(session, task, code=code, message=message)

    def _schedule_if_active(self, task: object) -> None:
        if getattr(task, "status") in _ACTIVE_STATES:
            self._schedule(task)

    def _schedule(self, task: object) -> None:
        ai = _ai()
        task.poll_error_count = 0
        task.next_poll_at = ai.utc_now() + timedelta(seconds=self._settings.ai_video_poll_interval_seconds)
        task.poll_lease_token = None
        task.poll_lease_until = None

    @staticmethod
    def _extension(value: str, output_type: str) -> str:
        suffix = PurePosixPath(value.split("?", 1)[0]).suffix.lower().lstrip(".")
        if output_type == "image":
            return suffix if suffix in {"jpg", "jpeg", "png", "webp"} else "png"
        return suffix if suffix in {"mp4", "mov"} else "mp4"

    @staticmethod
    def _locked(session: Session, claim: PollClaim) -> object | None:
        ai = _ai()
        task = session.scalar(select(ai.ModelTask).where(ai.ModelTask.id == claim.task_id).with_for_update())
        if task is None or task.poll_lease_token != claim.lease_token or task.status not in _ACTIVE_STATES:
            return None
        return task


def register_ai_video_tasks(app: Celery, settings: Settings) -> None:
    @app.task(name="narrato.ai_video.poll_tasks")  # type: ignore[untyped-decorator]
    def poll_ai_video_tasks(*, limit: int | None = None) -> int:
        engine, sessions, provider, oss_client, core_client = _services(settings)
        try:
            worker = AiVideoPollingWorker(sessions, provider, settings, oss_client=oss_client, core_client=core_client)
            return worker.run_due_tasks(limit=limit if limit is not None else settings.ai_video_poll_batch_size)
        finally:
            engine.dispose()

    setattr(poll_ai_video_tasks, "__narrato_registered__", True)
