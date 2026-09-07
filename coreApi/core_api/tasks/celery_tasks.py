from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from core_api.adapters.narrato.asr import AsrAdapter
from core_api.adapters.narrato.volcengine_asr import VolcengineAsrTranscriber
from core_api.adapters.narrato.media_probe import MediaProbeAdapter
from core_api.adapters.narrato.short_drama import (
    ShortDramaAdapter,
    create_short_drama_provider,
)
from core_api.adapters.narrato.tts import TtsAdapter, create_tts_provider
from core_api.adapters.narrato.render import (
    FakeRenderBackend,
    FfmpegRenderBackend,
    RenderAdapter,
)
from core_api.runtime.process_runner import ProcessRunner
from core_api.celery_app import celery_app
from core_api.config import Settings, get_cached_settings
from core_api.database import get_engine
from core_api.infrastructure.oss_client import (
    CdnUrlPolicy,
    HttpCdnDownloader,
    Oss2Client,
)
from core_api.runtime.artifact_store import ArtifactStore
from core_api.tasks.handlers import AtomicTaskHandler
from core_api.tasks.dispatch import DispatchOutboxPublisher
from core_api.tasks.callbacks import CallbackOutboxPublisher, HttpCallbackClient
from core_api.tasks.service import TaskService
from core_api.tasks.recovery import TaskRecoveryScanner
from core_api.tasks.artifact_reconciliation import (
    ArtifactReconciliationJournal,
    ArtifactReconciliationScanner,
)
from core_api.tasks.asr_jobs import AsrProviderJobStore
from core_api.tasks.queueing import queue_for_task_type


class CeleryWakeDispatcher:
    """把持久 dispatch 事件发布为带 fencing 的 Celery wake。"""

    def dispatch(
        self,
        task_id: str,
        *,
        task_type: str,
        expected_state_version: int,
        not_before: datetime,
        dispatch_id: str,
    ) -> None:
        """发布数据库事实中已到期且带版本的 wake。"""

        wake_core_task.apply_async(
            args=(
                task_id,
                expected_state_version,
                not_before.isoformat(),
                dispatch_id,
            ),
            queue=queue_for_task_type(task_type),
        )


def _create_source_transcriber(
    *,
    task_type: str,
    settings: Settings,
    job_store: AsrProviderJobStore,
) -> VolcengineAsrTranscriber | None:
    """仅为 ASR 任务校验并初始化远程识别供应商。"""

    if task_type != "asr" or settings.asr_provider != "volcengine":
        return None
    return VolcengineAsrTranscriber(
        appid=settings.volcengine_asr_appid,
        token=settings.volcengine_asr_token,
        cluster=settings.volcengine_asr_cluster,
        poll_interval_seconds=settings.volcengine_asr_poll_interval_seconds,
        total_timeout_seconds=settings.volcengine_asr_total_timeout_seconds,
        language=settings.volcengine_asr_language,
        use_itn=settings.volcengine_asr_use_itn,
        use_punc=settings.volcengine_asr_use_punc,
        with_speaker_info=settings.volcengine_asr_with_speaker_info,
        callback_base_url=settings.volcengine_asr_callback_base_url,
        job_store=job_store,
    )


def _short_drama_provider_arguments(
    *,
    settings: Settings,
    provider_code: str,
    provider_model_code: str,
    secret_ref: str,
    provider_settings: object,
) -> dict[str, str]:
    """解析一次短剧调用的私有连接参数。

    方舟模型 ID 是部署配置，而非能力目录中的 model_id 或 provider_model_code。
    因此切换火山 Endpoint 后只需更新 config.toml 并重启分析 Worker。
    """

    settings_map = provider_settings if isinstance(provider_settings, dict) else {}
    result = {
        "provider_code": provider_code,
        "provider_model_code": provider_model_code,
        "api_key": str(settings.provider_secrets.get(secret_ref, "")),
        "base_url": str(
            settings_map.get("base_url") or settings_map.get("api_base") or ""
        ),
        "prompt_category": str(
            settings_map.get("prompt_category") or "short_drama_narration"
        ),
    }
    if provider_code == "volcengine_ark":
        result.update(
            provider_model_code=settings.volcengine_ark_model_id,
            api_key=settings.volcengine_ark_api_key,
            base_url=settings.volcengine_ark_base_url,
        )
    return result


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
    engine = get_engine(settings)
    job_store = AsrProviderJobStore(
        lambda: Session(engine, expire_on_commit=False)
    )
    with Session(engine, expire_on_commit=False) as session:
        service = TaskService(session)
        task = service.get_task(task_id)

        def heartbeat_once(
            attempt_id: str, token: str, version: int, lease_seconds: float
        ) -> None:
            """使用独立短 Session 续租，避免跨线程复用 Worker 主事务。"""

            with Session(
                get_engine(settings), expire_on_commit=False
            ) as heartbeat_session:
                TaskService(heartbeat_session).heartbeat(
                    attempt_id,
                    token,
                    version,
                    lease_seconds=lease_seconds,
                )

        def local_transcribe(local_file: str, subtitle_file: str) -> str | None:
            """显式传入本 attempt 输出文件调用既有本地 ASR。"""

            return create_with_local_fun_asr(
                local_file,
                subtitle_file=subtitle_file,
                api_url=settings.asr_local_api_url,
            )

        source_transcriber = _create_source_transcriber(
            task_type=task.task_type,
            settings=settings,
            job_store=job_store,
        )

        short_drama_adapter = None
        tts_adapter = None
        render_adapter = None
        if task.task_type in {
            "audio_understanding",
            "video_analysis",
            "script_generation",
        }:
            model_snapshot = task.input_snapshot.get("model_snapshot")
            provider_code = (
                model_snapshot.get("provider_code")
                if isinstance(model_snapshot, dict)
                else None
            )
            provider_settings = (
                model_snapshot.get("provider_settings", {})
                if isinstance(model_snapshot, dict)
                else {}
            )
            secret_ref = (
                model_snapshot.get("secret_ref")
                if isinstance(model_snapshot, dict)
                else None
            )
            provider_args = _short_drama_provider_arguments(
                settings=settings,
                provider_code=str(provider_code or ""),
                provider_model_code=str(model_snapshot.get("provider_model_code") or "")
                if isinstance(model_snapshot, dict)
                else "",
                secret_ref=str(secret_ref or ""),
                provider_settings=provider_settings,
            )
            provider = create_short_drama_provider(
                **provider_args,
                model_limits={
                    **(
                        model_snapshot.get("provider_limits", {})
                        if isinstance(model_snapshot, dict)
                        and isinstance(model_snapshot.get("provider_limits"), dict)
                        else {}
                    ),
                    **(
                        model_snapshot.get("model_limits", {})
                        if isinstance(model_snapshot, dict)
                        and isinstance(model_snapshot.get("model_limits"), dict)
                        else {}
                    ),
                },
            )
            artifact_downloader = HttpCdnDownloader(
                CdnUrlPolicy(
                    set(settings.cdn_allowed_hosts), prefix="/narrato/coreApi/"
                ),
                connect_timeout=settings.download_connect_timeout_seconds,
                read_timeout=settings.download_read_timeout_seconds,
                total_timeout=settings.download_total_timeout_seconds,
            )
            short_drama_adapter = ShortDramaAdapter(
                provider=provider,
                downloader=downloader,
                artifact_downloader=artifact_downloader,
                artifact_store=ArtifactStore(oss_client),
            )
        if task.task_type in {"tts", "video_render"}:
            voice_snapshot = task.input_snapshot.get("voice_snapshot", {})
            provider_code = (
                voice_snapshot.get("provider_code")
                if isinstance(voice_snapshot, dict)
                else ""
            )
            secret_ref = (
                voice_snapshot.get("secret_ref")
                if isinstance(voice_snapshot, dict)
                else ""
            )
            tts_provider = create_tts_provider(
                str(provider_code or ""),
                voice_snapshot=voice_snapshot
                if isinstance(voice_snapshot, dict)
                else {},
                api_key=str(settings.provider_secrets.get(str(secret_ref or ""), "")),
            )
            tts_adapter = TtsAdapter(
                provider=tts_provider, artifact_store=ArtifactStore(oss_client)
            )
            if task.task_type == "video_render":
                render_adapter = RenderAdapter(
                    downloader=downloader,
                    backend=FfmpegRenderBackend(
                        provider=tts_provider,
                        voice_snapshot=voice_snapshot,
                        runner=ProcessRunner(heartbeat_interval_seconds=5),
                    ),
                    artifact_store=ArtifactStore(oss_client),
                )
        elif task.task_type == "subtitle":
            # 字幕任务只使用 RenderAdapter 的纯 SRT 路径，不执行 Fake 渲染。
            render_adapter = RenderAdapter(
                downloader=downloader,
                backend=FakeRenderBackend(),
                artifact_store=ArtifactStore(oss_client),
            )
        handler = AtomicTaskHandler(
            task_service=service,
            work_root=settings.work_root,
            media_probe_adapter=MediaProbeAdapter(
                downloader=downloader, probe=probe_media
            ),
            asr_adapter=AsrAdapter(
                downloader=downloader,
                transcriber=local_transcribe if source_transcriber is None else None,
                artifact_store=ArtifactStore(oss_client),
                source_transcriber=source_transcriber,
                source_url_validator=policy.validate if source_transcriber else None,
                process_runner=ProcessRunner(heartbeat_interval_seconds=5)
                if source_transcriber
                else None,
                provider_job_store=job_store if source_transcriber else None,
            ),
            short_drama_adapter=short_drama_adapter,
            tts_adapter=tts_adapter,
            render_adapter=render_adapter,
            heartbeat_once=heartbeat_once,
            reconciliation_store=ArtifactStore(oss_client),
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


@celery_app.task(name="core.tasks.publish_callback_outbox", ignore_result=True)
def publish_callback_outbox() -> None:
    """周期投递 Core 状态回调，网络故障由数据库退避重放。"""

    settings = get_cached_settings()
    if not settings.callback_url or not settings.callback_token:
        return
    try:
        client = HttpCallbackClient(
            settings.callback_url,
            settings.callback_token,
            connect_timeout=settings.callback_connect_timeout_seconds,
            read_timeout=settings.callback_read_timeout_seconds,
            total_timeout=settings.callback_total_timeout_seconds,
        )
    except ValueError:
        # 配置错误不允许触碰 Outbox；readiness 会同步报告不可用。
        return
    with Session(get_engine(settings), expire_on_commit=False) as session:
        CallbackOutboxPublisher(
            session,
            minimum_claim_seconds=settings.callback_total_timeout_seconds + 5.0,
        ).publish_pending(client)


@celery_app.task(name="core.tasks.recover_stalled", ignore_result=True)
def recover_stalled_core_tasks() -> None:
    """扫描 Broker 丢失 wake 与过期 Worker 租约，恢复为持久 dispatch。"""

    settings = get_cached_settings()
    with Session(get_engine(settings), expire_on_commit=False) as session:
        TaskRecoveryScanner(session).recover()
        # 同一次生产扫描立即发布已恢复及原本到期的 retry_wait 事件。
        DispatchOutboxPublisher(session).publish_pending(CeleryWakeDispatcher())


@celery_app.task(name="core.tasks.reconcile_artifacts", ignore_result=True)
def reconcile_artifacts() -> None:
    """独立周期扫描提交结果未知的 OSS 对象并按数据库事实收敛。"""
    settings = get_cached_settings()
    oss_client = Oss2Client(
        endpoint=settings.oss_endpoint,
        bucket=settings.oss_bucket,
        access_key_id=settings.oss_access_key_id,
        access_key_secret=settings.oss_access_key_secret,
        public_base_url=settings.oss_public_base_url,
    )
    with Session(get_engine(settings), expire_on_commit=False) as session:
        ArtifactReconciliationScanner(
            session,
            ArtifactReconciliationJournal(settings.work_root),
            ArtifactStore(oss_client),
        ).scan()
