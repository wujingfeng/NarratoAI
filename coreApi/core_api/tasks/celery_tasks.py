from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from core_api.adapters.narrato.asr import AsrAdapter
from core_api.adapters.narrato.media_probe import MediaProbeAdapter
from core_api.celery_app import celery_app
from core_api.config import get_cached_settings
from core_api.database import get_engine
from core_api.infrastructure.oss_client import CdnUrlPolicy, HttpCdnDownloader, Oss2Client
from core_api.runtime.artifact_store import ArtifactStore
from core_api.tasks.handlers import AtomicTaskHandler
from core_api.tasks.dispatch import DispatchOutboxPublisher
from core_api.tasks.service import TaskService
from core_api.tasks.recovery import TaskRecoveryScanner


class CeleryWakeDispatcher:
    """把持久 dispatch 事件发布为带 fencing 的 Celery wake。"""

    def dispatch(
        self,
        task_id: str,
        *,
        expected_state_version: int,
        not_before: datetime,
        dispatch_id: str,
    ) -> None:
        """发布数据库事实中已到期且带版本的 wake。"""

        wake_core_task.delay(
            task_id,
            expected_state_version,
            not_before.isoformat(),
            dispatch_id,
        )


def _run_atomic_task(
    task_id: str,
    expected_state_version: int,
    not_before: str,
    dispatch_id: str,
) -> None:
    """为 Celery 唤醒构建本进程私有 Adapter 并执行数据库 attempt。"""

    from app.services.fun_asr_subtitle import create_with_local_fun_asr
    from app.services.media_probe import probe_media

    settings = get_cached_settings()
    policy = CdnUrlPolicy(set(settings.cdn_allowed_hosts))
    downloader = HttpCdnDownloader(
        policy,
        connect_timeout=settings.download_connect_timeout_seconds,
        read_timeout=settings.download_read_timeout_seconds,
        total_timeout=settings.download_total_timeout_seconds,
    )
    oss_client = Oss2Client(
        endpoint=settings.oss_endpoint,
        bucket=settings.oss_bucket,
        access_key_id=settings.oss_access_key_id,
        access_key_secret=settings.oss_access_key_secret,
        public_base_url=settings.oss_public_base_url,
    )
    with Session(get_engine(settings), expire_on_commit=False) as session:
        service = TaskService(session)

        def heartbeat_once(
            attempt_id: str, token: str, version: int, lease_seconds: float
        ) -> None:
            """使用独立短 Session 续租，避免跨线程复用 Worker 主事务。"""

            with Session(get_engine(settings), expire_on_commit=False) as heartbeat_session:
                TaskService(heartbeat_session).heartbeat(
                    attempt_id,
                    token,
                    version,
                    lease_seconds=lease_seconds,
                )

        def transcribe(local_file: str, subtitle_file: str) -> str | None:
            """显式传入本 attempt 输出文件调用既有本地 ASR。"""

            return create_with_local_fun_asr(
                local_file,
                subtitle_file=subtitle_file,
                api_url=settings.asr_local_api_url,
            )

        handler = AtomicTaskHandler(
            task_service=service,
            work_root=settings.work_root,
            media_probe_adapter=MediaProbeAdapter(
                downloader=downloader, probe=probe_media
            ),
            asr_adapter=AsrAdapter(
                downloader=downloader,
                transcriber=transcribe,
                artifact_store=ArtifactStore(oss_client),
            ),
            heartbeat_once=heartbeat_once,
        )
        handler.run(
            task_id,
            expected_state_version=expected_state_version,
            not_before=datetime.fromisoformat(not_before),
            dispatch_id=dispatch_id,
        )


@celery_app.task(
    name="core.tasks.wake",
    ignore_result=True,
    acks_late=True,
    reject_on_worker_lost=True,
)
def wake_core_task(
    task_id: str,
    expected_state_version: int,
    not_before: str,
    dispatch_id: str,
) -> None:
    """仅唤醒数据库任务；执行状态始终以 PostgreSQL 为准。"""

    _run_atomic_task(task_id, expected_state_version, not_before, dispatch_id)


@celery_app.task(name="core.tasks.replay_dispatch_outbox", ignore_result=True)
def replay_dispatch_outbox() -> None:
    """扫描到期数据库唤醒事件，Broker 故障恢复后可重复执行。"""

    settings = get_cached_settings()

    with Session(get_engine(settings), expire_on_commit=False) as session:
        DispatchOutboxPublisher(session).publish_pending(CeleryWakeDispatcher())


@celery_app.task(name="core.tasks.recover_stalled", ignore_result=True)
def recover_stalled_core_tasks() -> None:
    """扫描 Broker 丢失 wake 与过期 Worker 租约，恢复为持久 dispatch。"""

    settings = get_cached_settings()
    with Session(get_engine(settings), expire_on_commit=False) as session:
        TaskRecoveryScanner(session).recover()
        # 同一次生产扫描立即发布已恢复及原本到期的 retry_wait 事件。
        DispatchOutboxPublisher(session).publish_pending(CeleryWakeDispatcher())
