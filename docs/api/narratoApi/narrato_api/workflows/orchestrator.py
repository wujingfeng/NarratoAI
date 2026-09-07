"""持久化 DAG 的窄执行器。

本模块不把 Core 调用放进数据库事务：先持久化 attempt，再以 attempt ID 作为
Core 幂等键提交；提交响应随后才绑定 Core task ID。Broker 重放同一 Outbox 事件
或 HTTP 请求中断都只会重用同一 attempt 和同一 Core 幂等键。
"""

from __future__ import annotations

import hashlib
from copy import deepcopy
from collections.abc import Callable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from narrato_api.assets.models import Asset
from narrato_api.editor.models import EditorRevision
from narrato_api.integrations.core_client import (
    CoreClientError,
    CoreClientRejectedError,
    HttpCoreClient,
)
from narrato_api.projects.models import Project, ProjectNarrationSettings
from narrato_api.workflows.models import (
    Workflow,
    WorkflowNode,
    WorkflowNodeAttempt,
    WorkflowOutbox,
    utc_now,
)
from narrato_api.workflows.service import _new_id


class WorkflowDispatchError(RuntimeError):
    """工作流无法准备或提交 Core 原子任务。"""


ANALYSIS_PROJECTION_NODES = (
    ("conflict_highlights", "plot_structure"),
    ("highlight_scoring", "conflict_highlights"),
)


def _latest_completed_attempt(
    session: Session, node: WorkflowNode
) -> WorkflowNodeAttempt | None:
    return session.scalar(
        select(WorkflowNodeAttempt)
        .where(
            WorkflowNodeAttempt.workflow_node_id == node.id,
            WorkflowNodeAttempt.state == "completed",
        )
        .order_by(WorkflowNodeAttempt.attempt_number.desc())
    )


def _complete_analysis_projection_nodes(
    session: Session, nodes_by_name: dict[str, WorkflowNode]
) -> None:
    """把完整剧情报告投影到展示节点，禁止为同一报告重复调用 LLM。"""

    for node_name, source_name in ANALYSIS_PROJECTION_NODES:
        node = nodes_by_name.get(node_name)
        source = nodes_by_name.get(source_name)
        if (
            node is None
            or source is None
            or node.state != "queued"
            or source.state != "completed"
        ):
            continue
        source_attempt = _latest_completed_attempt(session, source)
        if source_attempt is None or not isinstance(source_attempt.result, dict):
            continue
        attempt = session.scalar(
            select(WorkflowNodeAttempt)
            .where(WorkflowNodeAttempt.workflow_node_id == node.id)
            .order_by(WorkflowNodeAttempt.attempt_number.desc())
            .with_for_update()
        )
        if attempt is not None and attempt.state == "running":
            continue
        if attempt is None:
            attempt = WorkflowNodeAttempt(
                id=_new_id("wat"),
                workflow_node_id=node.id,
                attempt_number=1,
                state="completed",
                state_version=source_attempt.state_version,
            )
            session.add(attempt)
        else:
            attempt.state = "completed"
            attempt.state_version = source_attempt.state_version
        projected = deepcopy(source_attempt.result)
        projected["projection"] = {
            "source_node": source_name,
            "target_node": node_name,
            "reused_analysis_artifact": True,
        }
        attempt.result = projected
        attempt.completed_at = utc_now()
        node.state = "completed"


def _translation_allowed_duration_ms(
    rows: list[object], index: int, source_duration_seconds: object
) -> int:
    """允许译音使用本句区间及下一句前的真实空白，但绝不覆盖下一句。"""

    row = rows[index]
    start_ms = int(getattr(row, "start_ms"))
    end_ms = int(getattr(row, "end_ms"))
    if index + 1 < len(rows):
        boundary_ms = int(getattr(rows[index + 1], "start_ms"))
    elif type(source_duration_seconds) in (int, float):
        boundary_ms = round(float(source_duration_seconds) * 1000)
    else:
        boundary_ms = end_ms
    return max(end_ms - start_ms, boundary_ms - start_ms)


def _translation_rewrite_max_words(allowed_duration_ms: int, language: str) -> int:
    """按可用口播时长给 LLM 一个确定性上限，同时保留产品的 100 单位硬限。"""

    units_per_second = 6.0 if language in {"ja", "ko"} else 2.7
    return max(1, min(100, int(allowed_duration_ms / 1000 * units_per_second)))


class WorkflowOrchestrator:
    """从已完成依赖中选择一个 ready 节点，并安全提交到 Core。"""

    def __init__(
        self,
        session_factory: Callable[[], Session],
        *,
        video_translation_model_id: str = "model_qwen_plus",
    ) -> None:
        self.session_factory = session_factory
        self.video_translation_model_id = video_translation_model_id

    def dispatch_ready(self, *, workflow_id: str, core_client: HttpCoreClient) -> bool:
        """提交一个满足依赖的节点；无 ready 节点或已提交时返回 False。"""

        if self._skip_asr_for_uploaded_subtitle(workflow_id):
            return True
        prepared = self._prepare_attempt(workflow_id)
        if prepared is None:
            return False
        (
            attempt_id,
            node_name,
            sources,
            settings,
            subtitle_inputs,
            analysis_artifact,
            render_snapshot,
        ) = prepared
        try:
            if node_name == "subtitle_recognition":
                core_task_id = core_client.submit_audio_understanding(
                    model_id="model_volcengine_ark",
                    sources=[
                        {
                            "source_asset_id": source["source_asset_id"],
                            "video_url": source["video_url"],
                            "video_name": source["video_name"],
                            **(
                                {"duration_seconds": source["duration_seconds"]}
                                if source.get("duration_seconds") is not None
                                else {}
                            ),
                        }
                        for source in sources
                    ],
                    caller_task_id=attempt_id,
                )
            elif node_name == "script_generation":
                core_task_id = core_client.submit_script_generation(
                    model_id="model_volcengine_ark",
                    analysis_artifact=analysis_artifact,
                    sources=[
                        {
                            "source_asset_id": source["source_asset_id"],
                            "video_url": source["video_url"],
                            "video_name": source["video_name"],
                            "subtitle_name": source["subtitle_name"],
                            **(
                                {"duration_seconds": source["duration_seconds"]}
                                if source.get("duration_seconds") is not None
                                else {}
                            ),
                            **subtitle_inputs[str(source["source_asset_id"])],
                        }
                        for source in sources
                    ],
                    caller_task_id=attempt_id,
                    config_snapshot=_short_drama_config_snapshot(settings),
                )
            elif node_name == "subtitle_translation":
                if len(sources) != 1:
                    raise WorkflowDispatchError(
                        "video translation currently requires exactly one source"
                    )
                core_task_id = core_client.submit_video_translation(
                    model_id=self.video_translation_model_id,
                    subtitle_input=subtitle_inputs[str(sources[0]["source_asset_id"])],
                    target_language=str(settings.get("target_language") or "en"),
                    caller_task_id=attempt_id,
                )
            elif node_name == "subtitle_rewrite":
                from narrato_api.products.video_translation import (
                    VideoTranslationSegment,
                )

                with self.session_factory() as session:
                    project_id = session.scalar(
                        select(Workflow.project_id).where(Workflow.id == workflow_id)
                    )
                    all_rows = list(
                        session.scalars(
                            select(VideoTranslationSegment)
                            .where(VideoTranslationSegment.project_id == project_id)
                            .order_by(VideoTranslationSegment.segment_index)
                        )
                    )
                    rows = [
                        (index, row)
                        for index, row in enumerate(all_rows)
                        if row.timing_fit_status in {"rewrite_required", "overflow"}
                    ]
                if not rows:
                    raise WorkflowDispatchError(
                        "translation rewrite segments are unavailable"
                    )
                language = str(settings.get("target_language") or "en")
                source_duration = sources[0].get("duration_seconds")
                core_task_id = core_client.submit_translation_rewrite(
                    model_id=self.video_translation_model_id,
                    target_language=language,
                    segments=[
                        {
                            "segment_id": row.id,
                            "segment_index": row.segment_index,
                            "source_text": row.source_text,
                            "translated_text": row.translated_text,
                            "allowed_duration_ms": (
                                allowed := _translation_allowed_duration_ms(
                                    all_rows, row_index, source_duration
                                )
                            ),
                            "max_words": _translation_rewrite_max_words(
                                allowed, language
                            ),
                        }
                        for row_index, row in rows
                    ],
                    caller_task_id=attempt_id,
                )
            elif node_name == "tts" and "target_language" in settings:
                # 手动模式仅在用户确认台词后才会把这个节点释放为 ready。
                from narrato_api.products.video_translation import (
                    TTS_TIMING_TOLERANCE_MS,
                    VideoTranslationSegment,
                )

                with self.session_factory() as session:
                    project_id = session.scalar(
                        select(Workflow.project_id).where(Workflow.id == workflow_id)
                    )
                    rows = list(
                        session.scalars(
                            select(VideoTranslationSegment)
                            .where(VideoTranslationSegment.project_id == project_id)
                            .order_by(VideoTranslationSegment.segment_index)
                        )
                    )
                if not rows:
                    raise WorkflowDispatchError("translation segments are unavailable")
                # 初次全部为 pending；压缩重译后只有受影响行会被重置为 pending，
                # 因而第二轮只合成这些句子，保留其它句子的真实 timing 事实。
                tts_rows = [
                    (index, row)
                    for index, row in enumerate(rows)
                    if row.timing_fit_status == "pending"
                ]
                if not tts_rows:
                    tts_rows = list(enumerate(rows))
                core_task_id = core_client.submit_translation_tts(
                    voice_id=str(settings.get("voice_id") or rows[0].voice_id),
                    language=str(settings.get("target_language") or "en"),
                    segments=[
                        {
                            "segment_id": row.id,
                            "segment_index": row.segment_index,
                            "text": row.translated_text,
                            "start": row.start_ms / 1000,
                            "end": row.end_ms / 1000,
                            "voice_id": row.voice_id,
                            "speed": row.speed,
                            "volume": row.volume,
                            "allowed_duration_ms": _translation_allowed_duration_ms(
                                rows,
                                index,
                                sources[0].get("duration_seconds"),
                            ),
                            "timing_tolerance_ms": TTS_TIMING_TOLERANCE_MS,
                        }
                        for index, row in tts_rows
                    ],
                    caller_task_id=attempt_id,
                )
            elif node_name == "video_render":
                core_task_id = core_client.submit_video_render(
                    snapshot_id=str(render_snapshot["snapshot_id"]),
                    voice_id=str(render_snapshot["voice_id"]),
                    sources=list(render_snapshot["sources"]),
                    timeline=list(render_snapshot["timeline"]),
                    render_config=dict(render_snapshot.get("render_config") or {}),
                    caller_task_id=attempt_id,
                )
            elif node_name == "plot_structure":
                core_task_id = core_client.submit_video_analysis(
                    model_id="model_volcengine_ark",
                    sources=[
                        {
                            "source_asset_id": source["source_asset_id"],
                            "video_url": source["video_url"],
                            "video_name": source["video_name"],
                            "subtitle_name": source["subtitle_name"],
                            **(
                                {"duration_seconds": source["duration_seconds"]}
                                if source.get("duration_seconds") is not None
                                else {}
                            ),
                            **subtitle_inputs[str(source["source_asset_id"])],
                        }
                        for source in sources
                    ],
                    caller_task_id=attempt_id,
                    config_snapshot=_short_drama_config_snapshot(settings),
                )
            else:
                raise WorkflowDispatchError(
                    f"unsupported Core workflow node: {node_name}"
                )
        except CoreClientRejectedError as error:
            # 4xx/422 表示 Core 已经明确拒绝了当前请求，重放相同的 outbox 不会
            # 改变结果。收敛为终态失败，避免用户永久停在“字幕识别中”。
            self._fail_rejected_attempt(attempt_id=attempt_id, error=error)
            return True
        except CoreClientError as error:
            # 保留 queued attempt。下次 Outbox 重放继续使用相同 caller_task_id，
            # 因而可恢复“Core 已受理但 HTTP 响应丢失”的场景。
            raise WorkflowDispatchError("Core task submission failed") from error

        with self.session_factory() as session:
            with session.begin():
                attempt = session.scalar(
                    select(WorkflowNodeAttempt)
                    .where(WorkflowNodeAttempt.id == attempt_id)
                    .with_for_update()
                )
                if attempt is None or attempt.core_task_id is not None:
                    return False
                attempt.core_task_id = core_task_id
                attempt.state = "running"
                node = session.get(WorkflowNode, attempt.workflow_node_id)
                if node is not None:
                    node.state = "running"
                return True

    def _fail_rejected_attempt(
        self, *, attempt_id: str, error: CoreClientRejectedError
    ) -> None:
        """将 Core 的确定性请求拒绝写成工作流终态，禁止同一请求热重试。"""

        with self.session_factory() as session:
            with session.begin():
                attempt = session.scalar(
                    select(WorkflowNodeAttempt)
                    .where(WorkflowNodeAttempt.id == attempt_id)
                    .with_for_update()
                )
                if attempt is None or attempt.state in {"completed", "failed", "cancelled"}:
                    return
                node = session.get(WorkflowNode, attempt.workflow_node_id)
                if node is None:
                    return
                workflow = session.get(Workflow, node.workflow_id)
                attempt.state = "failed"
                attempt.completed_at = utc_now()
                attempt.result = {
                    "error": {
                        "code": error.code,
                        "message": str(error),
                        "retryable": False,
                    }
                }
                node.state = "failed"

                nodes = list(
                    session.scalars(
                        select(WorkflowNode)
                        .where(WorkflowNode.workflow_id == node.workflow_id)
                        .with_for_update()
                    )
                )
                blocked = {node.name}
                while True:
                    descendants = [
                        candidate
                        for candidate in nodes
                        if candidate.state == "queued"
                        and any(dependency in blocked for dependency in candidate.depends_on)
                    ]
                    if not descendants:
                        break
                    for descendant in descendants:
                        descendant.state = "cancelled"
                        blocked.add(descendant.name)
                if workflow is not None:
                    workflow.state = "failed"
                    workflow.state_version += 1
                    project = session.get(Project, workflow.project_id)
                    if project is not None:
                        project.status = "failed"

    def _prepare_attempt(
        self, workflow_id: str
    ) -> (
        tuple[
            str,
            str,
            list[dict[str, object]],
            dict[str, object],
            dict[str, dict[str, object]],
            dict[str, object],
            dict[str, object],
        ]
        | None
    ):
        with self.session_factory() as session:
            with session.begin():
                workflow = session.scalar(
                    select(Workflow).where(Workflow.id == workflow_id).with_for_update()
                )
                if workflow is None or workflow.state in {
                    "failed",
                    "cancelled",
                    "completed",
                    "waiting_for_edit",
                }:
                    return None
                nodes = list(
                    session.scalars(
                        select(WorkflowNode)
                        .where(WorkflowNode.workflow_id == workflow.id)
                        .with_for_update()
                    )
                )
                by_name = {node.name: node for node in nodes}
                _complete_analysis_projection_nodes(session, by_name)
                ready = next(
                    (
                        node
                        for node in nodes
                        if node.state == "queued"
                        and not node.manual_gate
                        and all(
                            by_name[name].state == "completed"
                            for name in node.depends_on
                        )
                    ),
                    None,
                )
                if ready is None:
                    return None
                attempt = session.scalar(
                    select(WorkflowNodeAttempt)
                    .where(
                        WorkflowNodeAttempt.workflow_node_id == ready.id,
                        WorkflowNodeAttempt.state == "queued",
                    )
                    .order_by(WorkflowNodeAttempt.attempt_number.desc())
                    .with_for_update()
                )
                if attempt is None:
                    count = (
                        session.scalar(
                            select(func.count())
                            .select_from(WorkflowNodeAttempt)
                            .where(WorkflowNodeAttempt.workflow_node_id == ready.id)
                        )
                        or 0
                    )
                    if count >= ready.max_attempts:
                        raise WorkflowDispatchError(
                            "workflow node retry budget exhausted"
                        )
                    attempt = WorkflowNodeAttempt(
                        id=_new_id("wat"),
                        workflow_node_id=ready.id,
                        attempt_number=count + 1,
                        state="queued",
                        state_version=0,
                    )
                    session.add(attempt)
                    session.flush()
                project = session.get(Project, workflow.project_id)
                videos = (
                    []
                    if project is None
                    else list(
                        session.scalars(
                            select(Asset)
                            .where(
                                Asset.project_id == project.id,
                                Asset.asset_type == "video",
                                Asset.status == "ready",
                            )
                            .order_by(Asset.sort_order, Asset.created_at, Asset.id)
                        )
                    )
                )
                if not videos:
                    raise WorkflowDispatchError("workflow has no ready video source")
                if len(videos) > 5:
                    raise WorkflowDispatchError("workflow has too many video sources")
                sources = [
                    {
                        "source_asset_id": video.id,
                        "video_url": video.cdn_url,
                        "video_name": video.filename,
                        "subtitle_name": f"{video.filename.rsplit('.', 1)[0]}.srt",
                        "duration_seconds": video.duration_seconds,
                        "declared_extension": (
                            f".{video.filename.rsplit('.', 1)[-1].lower()}"
                            if "." in video.filename
                            else ""
                        ),
                    }
                    for video in videos
                ]
                if project is not None and project.product == "video_translation":
                    # 延迟导入避免 workflow 初始化时反向加载产品 API。
                    from narrato_api.products.video_translation import (
                        VideoTranslationSettings,
                    )

                    translation = session.get(
                        VideoTranslationSettings, workflow.project_id
                    )
                    settings = (
                        dict(translation.settings) if translation is not None else {}
                    )
                else:
                    narration = session.get(
                        ProjectNarrationSettings, workflow.project_id
                    )
                    settings = dict(narration.settings) if narration is not None else {}
                settings.setdefault("drama_name", videos[0].filename.rsplit(".", 1)[0])
                subtitle_inputs: dict[str, dict[str, object]] = {}
                analysis_artifact: dict[str, object] = {}
                render_snapshot: dict[str, object] = {}
                if ready.name not in {"subtitle_recognition", "video_render"}:
                    subtitle_inputs = _completed_subtitle_inputs(
                        session,
                        by_name,
                        [video.id for video in videos],
                    )
                    if len(subtitle_inputs) != len(videos):
                        raise WorkflowDispatchError(
                            "completed subtitle input is unavailable"
                        )
                if ready.name == "script_generation":
                    analysis_artifact = _completed_analysis_input(session, by_name)
                    if not analysis_artifact:
                        raise WorkflowDispatchError(
                            "completed analysis artifact is unavailable"
                        )
                if ready.name == "video_render":
                    if project is not None and project.product == "video_translation":
                        # 视频翻译不使用短剧解说的 EditorRevision。以独立设置和
                        # 已确认的译文台词构造不可变 render 输入。
                        from narrato_api.products.video_translation import (
                            TTS_TIMING_TOLERANCE_MS,
                            VideoTranslationSegment,
                            normalize_original_sound_mode,
                        )

                        rows = list(
                            session.scalars(
                                select(VideoTranslationSegment)
                                .where(
                                    VideoTranslationSegment.project_id
                                    == workflow.project_id
                                )
                                .order_by(VideoTranslationSegment.segment_index)
                            )
                        )
                        if not rows:
                            raise WorkflowDispatchError(
                                "translation segments are unavailable"
                            )
                        source = sources[0]
                        ratio = str(settings.get("video_ratio") or "original")
                        audio_mode = normalize_original_sound_mode(
                            settings.get("original_sound_mode")
                        )
                        translated_region = settings.get("translated_subtitle_region")
                        translated_y = (
                            translated_region.get("y", 0.82)
                            if isinstance(translated_region, dict)
                            else 0.82
                        )
                        source_region = settings.get("source_subtitle_region")
                        source_layouts = {}
                        if not settings.get("preserve_source_subtitles") and isinstance(
                            source_region, dict
                        ):
                            source_layouts = {
                                str(source["source_asset_id"]): {
                                    "status": "confirmed",
                                    "region": source_region,
                                }
                            }
                        background_music = None
                        background_music_asset_id = settings.get(
                            "background_music_asset_id"
                        )
                        if (
                            isinstance(background_music_asset_id, str)
                            and background_music_asset_id
                        ):
                            music = session.scalar(
                                select(Asset).where(
                                    Asset.id == background_music_asset_id,
                                    Asset.project_id == workflow.project_id,
                                    Asset.asset_type == "audio",
                                    Asset.status == "ready",
                                )
                            )
                            if music is None:
                                raise WorkflowDispatchError(
                                    "translation background music is unavailable"
                                )
                            background_music = {
                                "asset_id": music.id,
                                "audio_url": music.cdn_url,
                                "volume": int(
                                    settings.get("background_music_volume") or 50
                                ),
                            }
                        render_snapshot = {
                            "snapshot_id": f"translation:{workflow.id}",
                            "voice_id": str(
                                settings.get("voice_id") or rows[0].voice_id
                            ),
                            "sources": [
                                {
                                    "source_asset_id": source["source_asset_id"],
                                    "video_url": source["video_url"],
                                }
                            ],
                            "timeline": [
                                {
                                    "source_asset_id": source["source_asset_id"],
                                    "segment_id": row.id,
                                    "segment_index": row.segment_index,
                                    "start": row.start_ms / 1000,
                                    "end": row.end_ms / 1000,
                                    "narration": row.translated_text,
                                    "subtitle": row.translated_text,
                                    # video_translation 专用渲染中这里只是配音/字幕 cue，
                                    # 原视频画面由 source 全长连续承载，不能按这些区间拼接。
                                    "original_sound": False,
                                    "voice_id": row.voice_id,
                                    "speed": row.speed,
                                    "volume": row.volume,
                                    "tts_duration_ms": row.tts_duration_ms,
                                    "timing_fit_status": row.timing_fit_status,
                                    "timing_overflow_ms": row.timing_overflow_ms,
                                    "fitted_speed": row.fitted_speed,
                                    "allowed_duration_ms": _translation_allowed_duration_ms(
                                        rows,
                                        index,
                                        source.get("duration_seconds"),
                                    ),
                                    "timing_tolerance_ms": TTS_TIMING_TOLERANCE_MS,
                                }
                                for index, row in enumerate(rows)
                            ],
                            "render_config": {
                                "render_mode": "video_translation",
                                "translation_audio_mode": audio_mode,
                                "video_ratio": ratio,
                                "voice_volume": 100,
                                "voice_rate": 1.0,
                                "original_sound_volume": 100
                                if audio_mode == "voice_replacement"
                                else 0,
                                **(
                                    {"background_music": background_music}
                                    if background_music is not None
                                    else {}
                                ),
                                "source_subtitle_layouts": source_layouts,
                                "translated_subtitle_region": translated_region,
                                "narration_subtitle_position": {
                                    "y": translated_y,
                                    "font_scale": 0.9,
                                },
                            },
                        }
                    else:
                        revision = session.scalar(
                            select(EditorRevision)
                            .where(EditorRevision.project_id == workflow.project_id)
                            .order_by(EditorRevision.created_at.desc())
                        )
                        raw_snapshot = (
                            revision.content.get("render_snapshot")
                            if revision
                            else None
                        )
                        if not isinstance(raw_snapshot, dict):
                            raise WorkflowDispatchError(
                                "render revision snapshot is unavailable"
                            )
                        render_snapshot = {**raw_snapshot, "snapshot_id": revision.id}
                    if not all(
                        isinstance(
                            render_snapshot.get(key),
                            list if key in {"sources", "timeline"} else str,
                        )
                        for key in ("snapshot_id", "voice_id", "sources", "timeline")
                    ):
                        raise WorkflowDispatchError(
                            "render revision snapshot is invalid"
                        )
                return (
                    attempt.id,
                    ready.name,
                    sources,
                    settings,
                    subtitle_inputs,
                    analysis_artifact,
                    render_snapshot,
                )

    def _skip_asr_for_uploaded_subtitle(self, workflow_id: str) -> bool:
        """已有项目 SRT 时将 ASR 节点作为已完成输入，避免重复识别。"""

        with self.session_factory() as session:
            with session.begin():
                workflow = session.scalar(
                    select(Workflow).where(Workflow.id == workflow_id).with_for_update()
                )
                if workflow is None or workflow.state in {
                    "failed",
                    "cancelled",
                    "completed",
                    "waiting_for_edit",
                }:
                    return False
                node = session.scalar(
                    select(WorkflowNode)
                    .where(
                        WorkflowNode.workflow_id == workflow.id,
                        WorkflowNode.name == "subtitle_recognition",
                        WorkflowNode.state == "queued",
                    )
                    .with_for_update()
                )
                if node is None or node.depends_on:
                    return False
                videos = list(
                    session.scalars(
                        select(Asset)
                        .where(
                            Asset.project_id == workflow.project_id,
                            Asset.asset_type == "video",
                            Asset.status == "ready",
                        )
                        .order_by(Asset.sort_order, Asset.created_at, Asset.id)
                    )
                )
                subtitles = list(
                    session.scalars(
                        select(Asset)
                        .where(
                            Asset.project_id == workflow.project_id,
                            Asset.asset_type == "subtitle",
                            Asset.status == "ready",
                        )
                        .order_by(Asset.created_at, Asset.id)
                    )
                )
                if not videos or not subtitles:
                    return False
                subtitles_by_stem: dict[str, list[Asset]] = {}
                for subtitle in subtitles:
                    stem = subtitle.filename.rsplit(".", 1)[0].casefold()
                    subtitles_by_stem.setdefault(stem, []).append(subtitle)
                matches: list[tuple[Asset, Asset]] = []
                for video in videos:
                    stem = video.filename.rsplit(".", 1)[0].casefold()
                    candidates = subtitles_by_stem.get(stem, [])
                    if candidates:
                        matches.append((video, candidates.pop(0)))
                    elif len(videos) == 1 and len(subtitles) == 1:
                        matches.append((video, subtitles[0]))
                    else:
                        # 部分 SRT 不能伪装成全部来源都有字幕；统一走批量 ASR。
                        return False
                attempt = session.scalar(
                    select(WorkflowNodeAttempt)
                    .where(
                        WorkflowNodeAttempt.workflow_node_id == node.id,
                        WorkflowNodeAttempt.state == "queued",
                    )
                    .order_by(WorkflowNodeAttempt.attempt_number.desc())
                    .with_for_update()
                )
                if attempt is None:
                    attempt = WorkflowNodeAttempt(
                        id=_new_id("wat"),
                        workflow_node_id=node.id,
                        attempt_number=1,
                    )
                    session.add(attempt)
                attempt.state = "completed"
                attempt.state_version = 1
                attempt.result = {
                    "subtitles": [
                        {
                            "source_asset_id": video.id,
                            "subtitle_url": subtitle.cdn_url,
                            "subtitle_name": subtitle.filename,
                            "asset_id": subtitle.id,
                        }
                        for video, subtitle in matches
                    ]
                }
                attempt.completed_at = utc_now()
                node.state = "completed"
                if workflow.state == "queued":
                    workflow.state = "running"
                    workflow.state_version += 1
                subtitle_ids = [subtitle.id for _video, subtitle in matches]
                digest = hashlib.sha256(
                    "\n".join(subtitle_ids).encode("utf-8")
                ).hexdigest()[:24]
                session.add(
                    WorkflowOutbox(
                        id=_new_id("obx"),
                        workflow_id=workflow.id,
                        workflow_node_id=node.id,
                        event_type="workflow.dispatch_ready",
                        idempotency_key=f"workflow-dispatch:{workflow.id}:{node.id}:uploaded-subtitles:{digest}",
                        payload={
                            "completed_node": node.name,
                            "subtitle_asset_ids": subtitle_ids,
                        },
                        status="pending",
                    )
                )
                return True


def _short_drama_config_snapshot(settings: dict[str, object]) -> dict[str, object]:
    """只传递火山方舟短剧分析/文案接口接受的冻结配置。"""

    selected_style = settings.get("narration_style")
    selected_genre = (
        settings.get("custom_style")
        if selected_style == "自定义类型"
        else selected_style
    )
    snapshot: dict[str, object] = {
        "original_sound_ratio": settings.get("original_sound_ratio", 30),
        "fps": 1,
        "min_frame_tokens": 64,
        "min_frame_tokens_mode": "provider_default",
    }
    if isinstance(selected_genre, str) and selected_genre.strip():
        snapshot["drama_genre"] = selected_genre.strip()
    for key in (
        "narration_style",
        "requirements",
        "target_duration_seconds",
        "temperature",
        "max_tokens",
    ):
        value = settings.get(key)
        if value is not None:
            snapshot[key] = value
    return snapshot


# 保留内部旧导入名，避免部署滚动升级期间已有 Worker/测试模块导入失败。
_qwen_config_snapshot = _short_drama_config_snapshot


def _completed_subtitle_inputs(
    session: Session,
    nodes_by_name: dict[str, WorkflowNode],
    source_asset_ids: list[str],
) -> dict[str, dict[str, object]]:
    """按来源素材 ID 取得上传 SRT 或批量 ASR Artifact。"""

    asr = nodes_by_name.get("subtitle_recognition")
    if asr is None or asr.state != "completed":
        return {}
    attempt = session.scalar(
        select(WorkflowNodeAttempt)
        .where(
            WorkflowNodeAttempt.workflow_node_id == asr.id,
            WorkflowNodeAttempt.state == "completed",
        )
        .order_by(WorkflowNodeAttempt.attempt_number.desc())
    )
    if attempt is None or not isinstance(attempt.result, dict):
        return {}
    result: dict[str, dict[str, object]] = {}
    containers = [attempt.result]
    nested = attempt.result.get("result")
    if isinstance(nested, dict):
        containers.append(nested)
    for container in containers:
        records = container.get("subtitles")
        if not isinstance(records, list):
            continue
        for record in records:
            if not isinstance(record, dict):
                continue
            source_id = record.get("source_asset_id")
            if not isinstance(source_id, str) or source_id not in source_asset_ids:
                continue
            subtitle_url = record.get("subtitle_url")
            subtitle_name = record.get("subtitle_name")
            name_snapshot = (
                {"subtitle_name": subtitle_name}
                if isinstance(subtitle_name, str) and subtitle_name
                else {}
            )
            if isinstance(subtitle_url, str) and subtitle_url:
                result[source_id] = {
                    "subtitle_url": subtitle_url,
                    **name_snapshot,
                }
                continue
            artifact = record.get("artifact")
            if not isinstance(artifact, dict):
                continue
            artifact_id, url = artifact.get("artifact_id"), artifact.get("url")
            if (
                isinstance(artifact_id, str)
                and artifact_id
                and isinstance(url, str)
                and url
            ):
                result[source_id] = {
                    "subtitle_artifact": {"artifact_id": artifact_id, "url": url},
                    **name_snapshot,
                }
    if len(result) == len(source_asset_ids):
        return result

    # 兼容升级前的单素材完成事实；多素材绝不把同一字幕复制到多个来源。
    if len(source_asset_ids) != 1:
        return result
    source_id = source_asset_ids[0]
    subtitle_url = attempt.result.get("subtitle_url")
    if isinstance(subtitle_url, str) and subtitle_url:
        return {source_id: {"subtitle_url": subtitle_url}}
    candidates: list[object] = []
    for container in containers:
        artifacts = container.get("artifacts")
        if isinstance(artifacts, list):
            candidates.extend(artifacts)
    for item in candidates:
        if not isinstance(item, dict):
            continue
        artifact_id, url = item.get("artifact_id"), item.get("url")
        if (
            isinstance(artifact_id, str)
            and artifact_id
            and isinstance(url, str)
            and url
        ):
            return {
                source_id: {
                    "subtitle_artifact": {"artifact_id": artifact_id, "url": url}
                }
            }
    return result


def _completed_analysis_input(
    session: Session, nodes_by_name: dict[str, WorkflowNode]
) -> dict[str, object]:
    """取得脚本生成必须消费的最终分析 Artifact。"""

    analysis = nodes_by_name.get("highlight_scoring")
    if analysis is None or analysis.state != "completed":
        return {}
    attempt = session.scalar(
        select(WorkflowNodeAttempt)
        .where(
            WorkflowNodeAttempt.workflow_node_id == analysis.id,
            WorkflowNodeAttempt.state == "completed",
        )
        .order_by(WorkflowNodeAttempt.attempt_number.desc())
    )
    if attempt is None or not isinstance(attempt.result, dict):
        return {}
    candidates: list[object] = []
    for container in (attempt.result, attempt.result.get("result")):
        if isinstance(container, dict) and isinstance(container.get("artifacts"), list):
            candidates.extend(container["artifacts"])
    for item in candidates:
        if not isinstance(item, dict):
            continue
        artifact_id, url = item.get("artifact_id"), item.get("url")
        if (
            isinstance(artifact_id, str)
            and artifact_id
            and isinstance(url, str)
            and url
            and item.get("kind", "analysis") == "analysis"
        ):
            return {"artifact_id": artifact_id, "url": url}
    return {}
