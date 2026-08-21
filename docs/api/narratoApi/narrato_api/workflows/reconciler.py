from __future__ import annotations

import secrets
import time
from collections.abc import Callable
from typing import Any, Literal
from urllib.parse import urlsplit

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from narrato_api.artifacts.models import RegisteredArtifact
from narrato_api.artifacts.service import register_artifact
from narrato_api.billing.models import CreditLedger
from narrato_api.billing.service import _apply_credit
from narrato_api.projects.models import Project, ProjectNarrationSettings
from narrato_api.projects.service import (
    EDIT_GATE_NODE,
    PUBLISH_ARTIFACTS_NODE,
    SCRIPT_GENERATION_NODE,
    ProjectLifecycleConflict,
    mark_project_render_completed,
    materialize_editor_draft,
    queue_project_render,
)
from narrato_api.workflows.models import (
    Workflow,
    WorkflowNode,
    WorkflowNodeAttempt,
    WorkflowOutbox,
    WorkflowReconciliationEvent,
    utc_now,
)


def _new_id() -> str:
    """生成收口事件的服务端 ID。"""

    return f"wre_{time.time_ns():016x}{secrets.token_hex(8)}"


class WorkflowReconciler:
    """让 Core 回调和轮询结果进入同一个幂等数据库事务。"""

    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self.session_factory = session_factory

    def reconcile_callback(self, **result: Any) -> bool:
        """收口 Core 回调的终态结果。"""

        return self._reconcile(source="callback", **result)

    def reconcile_polling(self, **result: Any) -> bool:
        """收口持续轮询取得的终态结果。"""

        return self._reconcile(source="polling", **result)

    def workflow_id_for_core_task(self, core_task_id: str) -> str:
        """返回已提交 Core 任务所属的工作流，用于事务外立即推进。"""

        with self.session_factory() as session:
            workflow_id = session.scalar(
                select(WorkflowNode.workflow_id)
                .join(WorkflowNodeAttempt)
                .where(WorkflowNodeAttempt.core_task_id == core_task_id)
            )
        if workflow_id is None:
            raise LookupError("workflow node attempt not found")
        return workflow_id

    def _reconcile(
        self,
        *,
        source: Literal["callback", "polling"],
        core_task_id: str,
        event_id: str,
        state_version: int,
        state: Literal["succeeded", "failed", "cancelled"],
        result: dict[str, Any],
    ) -> bool:
        """按事件和状态版本原子应用一个 Core 终态，重复或过期结果无副作用。"""

        if not core_task_id or not event_id or state_version < 0:
            raise ValueError(
                "core_task_id, event_id and non-negative state_version are required"
            )
        if state not in {"succeeded", "failed", "cancelled"}:
            raise ValueError("only terminal Core states can be reconciled")
        with self.session_factory() as session:
            with session.begin():
                attempt = session.scalar(
                    select(WorkflowNodeAttempt)
                    .where(WorkflowNodeAttempt.core_task_id == core_task_id)
                    .with_for_update()
                )
                if attempt is None:
                    raise LookupError("workflow node attempt not found")
                # 同一 Core 版本或更早版本均不允许覆盖已经确认的终态。
                if state_version <= attempt.state_version:
                    return False
                node = session.scalar(
                    select(WorkflowNode)
                    .where(WorkflowNode.id == attempt.workflow_node_id)
                    .with_for_update()
                )
                if node is None:
                    raise LookupError("workflow node not found")
                workflow = session.scalar(
                    select(Workflow)
                    .where(Workflow.id == node.workflow_id)
                    .with_for_update()
                )
                if workflow is None:
                    raise LookupError("workflow not found")
                project_for_product = session.get(Project, workflow.project_id)
                workflow_product = (
                    project_for_product.product
                    if project_for_product is not None
                    else ""
                )
                if attempt.state in {"completed", "failed", "cancelled"}:
                    return False

                terminal_state = state
                terminal_result = result
                render_artifacts: list[dict[str, object]] | None = None
                if state == "succeeded" and node.name == "video_render":
                    try:
                        render_artifacts = self._validated_render_artifacts(result)
                    except ValueError:
                        # Core 的成功状态不等于业务成片成功。缺少任一强制产物时，
                        # 在本事务内降级为确定性失败，禁止进入 export 或暴露空结果。
                        terminal_state = "failed"
                        terminal_result = {
                            "error": {
                                "code": "RENDER_ARTIFACT_CONTRACT_INVALID",
                                "retryable": False,
                            }
                        }

                if (
                    terminal_state == "succeeded"
                    and workflow_product == "video_translation"
                    and node.name == "subtitle_translation"
                ):
                    try:
                        self._materialize_translation_segments(
                            session,
                            project_id=workflow.project_id,
                            result=result,
                        )
                    except ValueError as error:
                        terminal_state = "failed"
                        terminal_result = {
                            "error": {
                                "code": str(error),
                                "retryable": False,
                            }
                        }

                if (
                    terminal_state == "succeeded"
                    and workflow_product == "video_translation"
                    and node.name == "tts"
                ):
                    # TTS 实际时长属于 Core 事实。缺少逐段 timing 的旧 Core
                    # 结果保持 pending，绝不能用字符数估算后伪装为实际时长。
                    self._materialize_translation_tts_timings(
                        session,
                        project_id=workflow.project_id,
                        result=result,
                    )

                if (
                    terminal_state == "succeeded"
                    and workflow_product == "video_translation"
                    and node.name == "subtitle_rewrite"
                ):
                    try:
                        self._materialize_rewritten_translation_segments(
                            session,
                            project_id=workflow.project_id,
                            result=result,
                        )
                    except ValueError as error:
                        terminal_state = "failed"
                        terminal_result = {
                            "error": {"code": str(error), "retryable": True}
                        }

                attempt.state = (
                    "completed" if terminal_state == "succeeded" else terminal_state
                )
                attempt.state_version = state_version
                attempt.result = terminal_result
                attempt.completed_at = utc_now()
                node.state = attempt.state

                edit_gate_exists = node.name == SCRIPT_GENERATION_NODE and bool(
                    session.scalar(
                        select(WorkflowNode.id).where(
                            WorkflowNode.workflow_id == workflow.id,
                            WorkflowNode.name == EDIT_GATE_NODE,
                        )
                    )
                )
                if terminal_state == "succeeded" and edit_gate_exists:
                    project = session.get(Project, workflow.project_id)
                    try:
                        if project is None:
                            raise ProjectLifecycleConflict(
                                "PROJECT_NOT_FOUND", "Project not found"
                            )
                        # 脚本成功必须能被真实映射为可编辑 Draft；否则不能把节点
                        # 标为完成，更不能在自动模式中伪造 Revision。
                        materialize_editor_draft(session, project=project)
                    except ProjectLifecycleConflict as error:
                        terminal_state = "failed"
                        terminal_result = {
                            "error": {
                                "code": error.code,
                                "retryable": False,
                            }
                        }
                        attempt.state = "failed"
                        attempt.result = terminal_result
                        node.state = "failed"

                reconciliation_event = WorkflowReconciliationEvent(
                    id=_new_id(),
                    workflow_node_attempt_id=attempt.id,
                    event_id=event_id,
                    state_version=state_version,
                    source=source,
                    state=terminal_state,
                )
                session.add(reconciliation_event)

                if terminal_state == "succeeded" and node.name == "video_render":
                    assert render_artifacts is not None
                    try:
                        with session.begin_nested():
                            self._register_render_artifacts(
                                session,
                                project_id=workflow.project_id,
                                artifacts=render_artifacts,
                            )
                            self._complete_publish_gate(session, workflow=workflow)
                    except ValueError:
                        terminal_state = "failed"
                        terminal_result = {
                            "error": {
                                "code": "RENDER_ARTIFACT_OWNERSHIP_CONFLICT",
                                "retryable": False,
                            }
                        }
                        attempt.state = "failed"
                        attempt.result = terminal_result
                        node.state = "failed"
                        reconciliation_event.state = "failed"

                # 收口后仅写 Outbox，让异步执行器推进下游，绝不在回调事务内调用 Core。
                if workflow.state == "queued":
                    workflow.state = "running"
                    workflow.state_version += 1
                    project = session.get(Project, workflow.project_id)
                    if project is not None and project.current_stage == "analysis":
                        project.status = "analyzing"
                if terminal_state in {"failed", "cancelled"}:
                    self._cancel_blocked_descendants(session, workflow.id, node.name)
                    workflow.state = terminal_state
                    workflow.state_version += 1
                elif (
                    workflow_product == "video_translation"
                    and node.name == "subtitle_translation"
                ):
                    # 手动模式的明确停点：译文已入库，先让用户编辑，禁止提前合成。
                    from narrato_api.products.video_translation import (
                        VideoTranslationSettings,
                    )

                    project = session.get(Project, workflow.project_id)
                    translation = session.get(
                        VideoTranslationSettings, workflow.project_id
                    )
                    settings = (
                        dict(translation.settings) if translation is not None else {}
                    )
                    if (
                        project is not None
                        and settings.get("execution_mode", "manual") == "manual"
                    ):
                        project.current_stage = "edit"
                        project.status = "waiting_for_edit"
                        workflow.state = "waiting_for_edit"
                        workflow.state_version += 1
                elif (
                    workflow_product == "video_translation"
                    and node.name == "subtitle_rewrite"
                ):
                    # 压缩重译只改受影响行；成功后重跑 TTS，不重跑识别和整批翻译。
                    project = session.get(Project, workflow.project_id)
                    tts_node = session.scalar(
                        select(WorkflowNode)
                        .where(
                            WorkflowNode.workflow_id == workflow.id,
                            WorkflowNode.name == "tts",
                        )
                        .with_for_update()
                    )
                    render_node = session.scalar(
                        select(WorkflowNode)
                        .where(
                            WorkflowNode.workflow_id == workflow.id,
                            WorkflowNode.name == "video_render",
                        )
                        .with_for_update()
                    )
                    if project is None or tts_node is None or render_node is None:
                        raise LookupError("translation rewrite dependencies not found")
                    attempt_count = (
                        session.scalar(
                            select(func.count())
                            .select_from(WorkflowNodeAttempt)
                            .where(WorkflowNodeAttempt.workflow_node_id == tts_node.id)
                        )
                        or 0
                    )
                    if attempt_count >= tts_node.max_attempts:
                        tts_node.max_attempts = attempt_count + 1
                    tts_node.state = "queued"
                    tts_node.manual_gate = False
                    render_node.state = "queued"
                    render_node.manual_gate = True
                    project.current_stage = "generate"
                    project.status = "queued"
                    workflow.state = "queued"
                    workflow.state_version += 1
                    session.add(
                        WorkflowOutbox(
                            id=_new_id(),
                            workflow_id=workflow.id,
                            workflow_node_id=tts_node.id,
                            event_type="workflow.dispatch_ready",
                            idempotency_key=(
                                f"translation-tts-after-rewrite:{workflow.id}:"
                                f"{attempt.state_version}"
                            ),
                            payload={
                                "completed_node": "subtitle_rewrite",
                                "product": "video_translation",
                            },
                            status="pending",
                        )
                    )
                elif workflow_product == "video_translation" and node.name == "tts":
                    project = session.get(Project, workflow.project_id)
                    if project is None:
                        raise LookupError("translation project not found")
                    if project.current_stage == "edit":
                        # 兼容旧版已提前执行 TTS 的历史任务。
                        project.status = "waiting_for_edit"
                        workflow.state = "waiting_for_edit"
                        workflow.state_version += 1
                    else:
                        # TTS 是翻译成片的唯一前置条件。只有这一个成功回调才能
                        # 解除 render 门，禁止 render 在 0/N 配音完成时被投递。
                        render_node = session.scalar(
                            select(WorkflowNode)
                            .where(
                                WorkflowNode.workflow_id == workflow.id,
                                WorkflowNode.name == "video_render",
                            )
                            .with_for_update()
                        )
                        if render_node is None:
                            raise LookupError("translation render node not found")
                        render_node.manual_gate = False
                        project.current_stage = "generate"
                        project.status = "render_queued"
                        workflow.state = "running"
                        workflow.state_version += 1
                        # render_queued 是产品展示状态，不是 workflow 的终态。
                        # TTS 完成后必须实际投递 video_render，否则手动流程会
                        # 永久停在“配音 24/N、渲染 queued”。
                        session.add(
                            WorkflowOutbox(
                                id=_new_id(),
                                workflow_id=workflow.id,
                                workflow_node_id=render_node.id,
                                event_type="workflow.dispatch_ready",
                                idempotency_key=(
                                    f"translation-render-dispatch:{workflow.id}:"
                                    f"{attempt.state_version}"
                                ),
                                payload={
                                    "completed_node": "tts",
                                    "product": "video_translation",
                                },
                                status="pending",
                            )
                        )
                elif node.name == SCRIPT_GENERATION_NODE and session.scalar(
                    select(WorkflowNode.id).where(
                        WorkflowNode.workflow_id == workflow.id,
                        WorkflowNode.name == EDIT_GATE_NODE,
                        WorkflowNode.state == "queued",
                    )
                ):
                    project = session.get(Project, workflow.project_id)
                    narration = session.get(
                        ProjectNarrationSettings, workflow.project_id
                    )
                    settings = dict(narration.settings) if narration is not None else {}
                    if (
                        settings.get("execution_mode", "manual") == "auto"
                        and project is not None
                    ):
                        queue_project_render(
                            session,
                            project=project,
                            workflow=workflow,
                            idempotency_key=(
                                f"auto-render:{workflow.id}:{attempt.id}:"
                                f"{attempt.state_version}"
                            ),
                            automatic=True,
                        )
                    else:
                        # 手动模式稳定停在编辑门，等待用户提交不可变 Revision。
                        workflow.state = "waiting_for_edit"
                        workflow.state_version += 1
                        if project is not None and project.current_stage == "analysis":
                            project.status = "waiting_for_edit"
                elif not session.scalar(
                    select(WorkflowNode.id).where(
                        WorkflowNode.workflow_id == workflow.id,
                        WorkflowNode.state != "completed",
                    )
                ):
                    project = session.get(Project, workflow.project_id)
                    if project is not None and project.current_stage == "analysis":
                        # 分析完成只解锁“进入编辑”动作，绝不把项目错误标记为导出完成。
                        workflow.state = "waiting_for_edit"
                        project.status = "waiting_for_edit"
                    else:
                        workflow.state = "completed"
                    workflow.state_version += 1
                if terminal_state == "succeeded" and workflow.state not in {
                    "waiting_for_edit",
                    "completed",
                }:
                    session.add(
                        WorkflowOutbox(
                            id=_new_id(),
                            workflow_id=workflow.id,
                            workflow_node_id=node.id,
                            event_type="workflow.dispatch_ready",
                            idempotency_key=f"workflow-dispatch:{workflow.id}:{node.id}:{attempt.state_version}",
                            payload={"completed_node": node.name},
                            status="pending",
                        )
                    )
                if workflow.state in {"completed", "failed", "cancelled"}:
                    project = session.get(Project, workflow.project_id)
                    if project is not None:
                        if (
                            workflow.state == "completed"
                            and project.current_stage == "generate"
                        ):
                            mark_project_render_completed(session, project=project)
                        else:
                            project.status = workflow.state
                        if workflow.state in {"failed", "cancelled"}:
                            # 项目可另有试听等独立消费流水；退款只能命中启动
                            # 工作流所产生的主扣费。视频翻译允许失败后重新付费
                            # 执行，故选择最新一笔产品主扣费，而不能按 reference_id
                            # 随机取第一笔 charge。
                            charge_query = select(CreditLedger).where(
                                CreditLedger.reference_id == project.id,
                                CreditLedger.entry_type == "charge",
                            )
                            if project.product == "video_translation":
                                charge_query = charge_query.where(
                                    CreditLedger.reason == "video_translation_charge"
                                ).order_by(CreditLedger.id.desc())
                            else:
                                charge_query = charge_query.where(
                                    CreditLedger.idempotency_key
                                    == f"charge:{project.id}"
                                )
                            charge = session.scalar(charge_query.with_for_update())
                            if charge is not None:
                                _apply_credit(
                                    session,
                                    user_id=charge.user_id,
                                    entry_type="refund",
                                    amount=-charge.amount,
                                    idempotency_key=f"refund:{project.id}:{charge.id}",
                                    reference_id=project.id,
                                    reason="project_failed_refund",
                                )
                return True

    @staticmethod
    def _materialize_translation_segments(
        session: Session,
        *,
        project_id: str,
        result: dict[str, Any],
    ) -> None:
        """把 Core 的时间轴翻译结果作为编辑表格唯一事实落库。"""

        # 延迟导入保持通用 workflow 与独立产品模型的启动边界。
        from narrato_api.products.video_translation import (
            VideoTranslationSegment,
            VideoTranslationSettings,
        )

        payload = result.get("result", result)
        records = payload.get("segments") if isinstance(payload, dict) else None
        if not isinstance(records, list) or not records:
            raise ValueError("TRANSLATION_SEGMENTS_MISSING")
        settings_record = session.get(VideoTranslationSettings, project_id)
        settings = dict(settings_record.settings) if settings_record is not None else {}
        voice_id = settings.get("voice_id")
        if not isinstance(voice_id, str) or not voice_id:
            raise ValueError("TRANSLATION_VOICE_MISSING")

        normalized: list[dict[str, object]] = []
        for index, item in enumerate(records):
            if not isinstance(item, dict):
                raise ValueError("TRANSLATION_SEGMENT_INVALID")
            start_ms, end_ms = item.get("start_ms"), item.get("end_ms")
            source_text, translated_text = (
                item.get("source_text"),
                item.get("translated_text"),
            )
            if (
                not isinstance(start_ms, int)
                or isinstance(start_ms, bool)
                or not isinstance(end_ms, int)
                or isinstance(end_ms, bool)
                or start_ms < 0
                or end_ms <= start_ms
                or not isinstance(source_text, str)
                or not source_text.strip()
                or not isinstance(translated_text, str)
                or not translated_text.strip()
            ):
                raise ValueError("TRANSLATION_SEGMENT_INVALID")
            normalized.append(
                {
                    "id": _new_id(),
                    "project_id": project_id,
                    "segment_index": index,
                    "start_ms": start_ms,
                    "end_ms": end_ms,
                    "source_text": source_text.strip(),
                    "translated_text": translated_text.strip(),
                    "voice_id": voice_id,
                    "speed": 1.0,
                    "volume": 100,
                    # 历史逐行开关不再控制音轨；成片统一使用项目级双态模式。
                    "keep_original_sound": False,
                    "timing_fit_status": "pending",
                    "timing_overflow_ms": 0,
                }
            )
        session.execute(
            delete(VideoTranslationSegment).where(
                VideoTranslationSegment.project_id == project_id
            )
        )
        session.add_all(VideoTranslationSegment(**item) for item in normalized)

    @staticmethod
    def _materialize_rewritten_translation_segments(
        session: Session,
        *,
        project_id: str,
        result: dict[str, Any],
    ) -> None:
        """只覆盖 Core 明确返回的超限句，并让这些句的旧试听/时长失效。"""

        from narrato_api.products.video_translation import (
            VideoTranslationSegment,
            VideoTranslationSettings,
            _invalidate_tts_timing,
            _validate_text,
        )
        from narrato_api.api.errors import ApiError

        payload = result.get("result", result)
        records = payload.get("segments") if isinstance(payload, dict) else None
        if not isinstance(records, list) or not records:
            raise ValueError("TRANSLATION_REWRITE_SEGMENTS_MISSING")
        settings_record = session.get(VideoTranslationSettings, project_id)
        settings = dict(settings_record.settings) if settings_record is not None else {}
        language = str(settings.get("target_language") or "en")
        seen: set[str] = set()
        for item in records:
            if not isinstance(item, dict):
                raise ValueError("TRANSLATION_REWRITE_SEGMENT_INVALID")
            segment_id, text = item.get("segment_id"), item.get("translated_text")
            if (
                not isinstance(segment_id, str)
                or not segment_id
                or segment_id in seen
                or not isinstance(text, str)
                or not text.strip()
            ):
                raise ValueError("TRANSLATION_REWRITE_SEGMENT_INVALID")
            row = session.scalar(
                select(VideoTranslationSegment)
                .where(
                    VideoTranslationSegment.project_id == project_id,
                    VideoTranslationSegment.id == segment_id,
                    VideoTranslationSegment.timing_fit_status.in_(
                        ["rewrite_required", "overflow"]
                    ),
                )
                .with_for_update()
            )
            if row is None:
                raise ValueError("TRANSLATION_REWRITE_SEGMENT_INVALID")
            normalized_text = text.strip()
            try:
                _validate_text(normalized_text, language)
            except ApiError as exc:
                raise ValueError(exc.code) from exc
            row.translated_text = normalized_text
            row.preview_audio_url = None
            row.preview_digest = None
            _invalidate_tts_timing(row)
            seen.add(segment_id)

    @staticmethod
    def _materialize_translation_tts_timings(
        session: Session,
        *,
        project_id: str,
        result: dict[str, Any],
    ) -> list[str]:
        """回写 Core 给出的逐段真实配音时长与适配结论。"""

        from narrato_api.products.video_translation import (
            TTS_TIMING_TOLERANCE_MS,
            VideoTranslationSegment,
        )

        payload = result.get("result", result)
        metadata = payload.get("metadata") if isinstance(payload, dict) else None
        records = payload.get("segment_timings") if isinstance(payload, dict) else None
        if not isinstance(records, list) and isinstance(metadata, dict):
            records = metadata.get("segment_timings")
        if not isinstance(records, list):
            return []
        rows = list(
            session.scalars(
                select(VideoTranslationSegment)
                .where(VideoTranslationSegment.project_id == project_id)
                .order_by(VideoTranslationSegment.segment_index)
                .with_for_update()
            )
        )
        by_id = {row.id: row for row in rows}
        by_index = {row.segment_index: row for row in rows}
        valid_statuses = {"fit", "speed_adjusted", "rewritten"}
        for item in records:
            if not isinstance(item, dict):
                continue
            row = by_id.get(item.get("segment_id"))
            if row is None:
                index = item.get("segment_index")
                row = by_index.get(index) if type(index) is int else None
            duration = item.get("tts_duration_ms")
            if row is None or type(duration) not in (int, float) or duration <= 0:
                continue
            duration_ms = int(round(float(duration)))
            slot_ms = row.end_ms - row.start_ms
            overflow_ms = item.get("timing_overflow_ms")
            if type(overflow_ms) not in (int, float):
                # 200ms 是经确认的同步容差，容差内不提示超限。
                overflow_ms = max(0, duration_ms - slot_ms - TTS_TIMING_TOLERANCE_MS)
            overflow_ms = max(0, int(round(float(overflow_ms))))
            status = item.get("timing_fit_status")
            if status in {"overflow", "rewrite_required"}:
                # 兼容旧 Core 回调：新版不再要求用户压缩译文，直接表述为自动适配。
                status = "speed_adjusted"
            if status not in valid_statuses:
                status = "speed_adjusted" if overflow_ms > 0 else "fit"
            fitted_speed = item.get("fitted_speed", item.get("adapted_speed"))
            row.tts_duration_ms = duration_ms
            row.timing_overflow_ms = overflow_ms
            row.timing_fit_status = str(status)
            row.fitted_speed = (
                float(fitted_speed)
                if type(fitted_speed) in (int, float) and fitted_speed > 0
                else None
            )
        # 配音超时由 Core 自动加速完成，绝不将段落送回人工压缩文案关卡。
        return []

    @staticmethod
    def _complete_publish_gate(session: Session, *, workflow: Workflow) -> None:
        """渲染成功后由服务端登记产物并闭合发布门，无需虚构第二个 Core 任务。"""

        node = session.scalar(
            select(WorkflowNode)
            .where(
                WorkflowNode.workflow_id == workflow.id,
                WorkflowNode.name == PUBLISH_ARTIFACTS_NODE,
            )
            .with_for_update()
        )
        if node is not None and node.state == "queued":
            node.state = "completed"

    @staticmethod
    def _validated_render_artifacts(
        result: dict[str, Any],
    ) -> list[dict[str, object]]:
        """验证 Core Render 的完整四产物契约并去除回调/轮询重复副本。"""

        candidates: list[object] = []
        for container in (result, result.get("result")):
            if isinstance(container, dict) and isinstance(
                container.get("artifacts"), list
            ):
                candidates.extend(container["artifacts"])
        by_id: dict[str, dict[str, object]] = {}
        for raw in candidates:
            if not isinstance(raw, dict):
                raise ValueError("render artifact is invalid")
            artifact_id, kind, url = (
                raw.get("artifact_id"),
                raw.get("kind"),
                raw.get("url"),
            )
            size, content_type, checksum = (
                raw.get("size"),
                raw.get("content_type"),
                raw.get("checksum"),
            )
            try:
                parsed = urlsplit(url if isinstance(url, str) else "")
            except ValueError as error:
                raise ValueError("render artifact URL is invalid") from error
            if not (
                isinstance(artifact_id, str)
                and 1 <= len(artifact_id) <= 64
                and isinstance(kind, str)
                and kind in {"video", "subtitle", "voice", "timeline"}
                and isinstance(url, str)
                and parsed.scheme == "https"
                and bool(parsed.hostname)
                and not parsed.username
                and not parsed.password
                and not parsed.query
                and not parsed.fragment
                and isinstance(size, int)
                and not isinstance(size, bool)
                and size > 0
                and isinstance(content_type, str)
                and bool(content_type)
                and isinstance(checksum, str)
                and checksum.startswith("sha256:")
                and len(checksum) == 71
            ):
                raise ValueError("render artifact contract is invalid")
            normalized = {
                "artifact_id": artifact_id,
                "kind": kind,
                "url": url,
                "size": size,
                "content_type": content_type,
                "checksum": checksum,
                "width": raw.get("width"),
                "height": raw.get("height"),
                "duration": raw.get("duration"),
            }
            existing = by_id.get(artifact_id)
            if existing is not None:
                # 轮询接口的公开产物列表不携带视频的宽高和时长，而 Core
                # result.artifacts 会携带它们。两者是同一成片的两种投影，
                # 只要不可变身份字段相同即可合并可选元数据，不能误判失败。
                identity_fields = (
                    "artifact_id",
                    "kind",
                    "url",
                    "size",
                    "content_type",
                    "checksum",
                )
                if any(
                    existing[field] != normalized[field] for field in identity_fields
                ):
                    raise ValueError("render artifact identity is inconsistent")
                for field in ("width", "height", "duration"):
                    if (
                        existing[field] is not None
                        and normalized[field] is not None
                        and existing[field] != normalized[field]
                    ):
                        raise ValueError("render artifact identity is inconsistent")
                    if existing[field] is None:
                        existing[field] = normalized[field]
                continue
            by_id[artifact_id] = normalized
        required_kinds = {
            "video",
            "subtitle",
            "voice",
            "timeline",
        }
        if (
            len(by_id) != len(required_kinds)
            or {item["kind"] for item in by_id.values()} != required_kinds
        ):
            raise ValueError("render artifacts are incomplete")
        return list(by_id.values())

    @staticmethod
    def _register_render_artifacts(
        session: Session,
        *,
        project_id: str,
        artifacts: list[dict[str, object]],
    ) -> None:
        """只登记已验证的最终渲染产物；重复事件必须保持同一项目归属。"""

        for raw in artifacts:
            artifact_id = str(raw["artifact_id"])
            existing = session.get(RegisteredArtifact, artifact_id)
            if existing is not None:
                if (
                    existing.project_id != project_id
                    or existing.kind != raw["kind"]
                    or existing.cdn_url != raw["url"]
                ):
                    raise ValueError("render artifact identity is already owned")
                continue
            register_artifact(
                session,
                artifact_id=artifact_id,
                project_id=project_id,
                kind=str(raw["kind"]),
                cdn_url=str(raw["url"]),
                size=raw.get("size") if isinstance(raw.get("size"), int) else None,
                checksum=raw.get("checksum")
                if isinstance(raw.get("checksum"), str)
                else None,
                content_type=raw.get("content_type")
                if isinstance(raw.get("content_type"), str)
                else None,
                width=raw.get("width") if isinstance(raw.get("width"), int) else None,
                height=raw.get("height")
                if isinstance(raw.get("height"), int)
                else None,
                duration=float(raw["duration"])
                if isinstance(raw.get("duration"), (int, float))
                and not isinstance(raw.get("duration"), bool)
                else None,
            )

    @staticmethod
    def _cancel_blocked_descendants(
        session: Session, workflow_id: str, failed_name: str
    ) -> None:
        """将依赖失败/取消节点的所有未启动后继标为取消，保留因果链。"""

        nodes = list(
            session.scalars(
                select(WorkflowNode)
                .where(WorkflowNode.workflow_id == workflow_id)
                .with_for_update()
            )
        )
        blocked = {failed_name}
        changed = True
        while changed:
            changed = False
            for candidate in nodes:
                if candidate.state == "queued" and any(
                    dependency in blocked for dependency in candidate.depends_on
                ):
                    candidate.state = "cancelled"
                    blocked.add(candidate.name)
                    changed = True
