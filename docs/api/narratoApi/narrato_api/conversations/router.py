"""认证用户的助手会话 API。

这里是唯一可由会话模式触发产品任务的入口。模式在 thread 和 message 上均
冻结，所有分支只调用各自白名单中的产品服务，不能藉由自然语言跨模式调用。
"""

from __future__ import annotations

import gzip
import io
import random
import re
import secrets
import time
import json
import threading
from collections.abc import Iterator
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_FLOOR
from typing import Annotated, Literal
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request as UrlRequest, urlopen

from fastapi import APIRouter, Depends, Header, Query, Request, status
from fastapi.responses import StreamingResponse
from pydantic import AliasChoices, Field, model_validator
from sqlalchemy import and_, delete, or_, select
from sqlalchemy.orm import Session

from narrato_api.api.dependencies import get_request_id, get_settings
from narrato_api.api.errors import ApiError
from narrato_api.api.responses import ApiResponse, StrictModel
from narrato_api.artifacts.models import RegisteredArtifact
from narrato_api.assets.models import Asset
from narrato_api.auth.router import bearer_token, get_auth_service
from narrato_api.auth.service import AuthService
from narrato_api.conversations.models import (
    AgentRun,
    ConversationMessage,
    ConversationThread,
)
from narrato_api.products.ai_video import (
    AI_VIDEO_MODEL_TYPES,
    LlmCompletionRequest,
    TaskCreateRequest,
    _create_model_task,
    _fail_task,
    _mark_completed,
    _stage_provider_result,
    _submit_task,
    _task_assets_payload,
    get_provider_registry,
)
from narrato_api.products.model_generation import (
    Model,
    ModelPlayMode,
    ModelPlayModeProvider,
    ModelPlayModeProviderPrice,
    ModelPlayModeRule,
    ModelTask,
    ModelTaskOutput,
    utc_now,
)
from narrato_api.products.providers import ProviderError, ProviderOutput, ProviderResult
from narrato_api.products.video_translation import (
    SUPPORTED_LANGUAGES,
    SUPPORTED_SUBTITLE_STYLES,
    VideoTranslationSettings,
    _start_translation,
)
from narrato_api.projects.models import Project
from narrato_api.projects.service import (
    ProjectLifecycleConflict,
    ProjectNotFoundError,
    create_project,
    save_settings_and_start_analysis,
)
from narrato_api.workflows.models import Workflow, WorkflowNode, WorkflowNodeAttempt
from narrato_api.config import Settings
from narrato_api.integrations.core_client import CoreClientError, HttpCoreClient

router = APIRouter()

Mode = Literal["chat", "short_drama_narration", "video_translation", "video_generation"]
GenerationMode = Literal[
    "text_to_video",
    "first_frame",
    "first_last_frame",
    "multi_subject_reference_audio_visual",
]
AssistantLocale = Literal["zh-CN", "en", "ja"]
_CHAT_STREAM_LEASE_SECONDS = 15 * 60
_CHAT_STREAM_POLL_SECONDS = 0.35
_AGENT_RUN_STREAM_POLL_SECONDS = 0.35
_CHAT_CONTEXT_INPUT_TOKEN_BUDGET = 12000
_CHAT_CONTEXT_RECENT_MESSAGE_LIMIT = 12
_CHAT_CONTEXT_RECALL_TURN_LIMIT = 4
_CHAT_CONTEXT_RECALL_TOKEN_BUDGET = 2200
_CHAT_CONTEXT_AGENT_RUN_LIMIT = 6
_CHAT_CONTEXT_AGENT_RUN_CHAR_BUDGET = 4200
_CHAT_SUMMARY_CHAR_BUDGET = 6000
_CHAT_MEMORY_FACT_LIMIT = 12
_CHAT_SYSTEM_PROMPT = (
    "你是 NarratoAI 的普通聊天助手。直接、简洁地回答用户；"
    "不要创建项目、工作流或视频生成任务。"
)
_ASSISTANT_LOCALE_INSTRUCTIONS: dict[AssistantLocale, str] = {
    "zh-CN": "所有面向用户的自然语言内容必须使用简体中文。",
    "en": "All user-facing natural-language content must be written in English.",
    "ja": "ユーザー向けの自然言語コンテンツはすべて日本語で出力してください。",
}


def _id(prefix: str) -> str:
    return f"{prefix}_{time.time_ns():x}{secrets.token_hex(6)}"


class ThreadCreateRequest(StrictModel):
    mode: Mode = "chat"
    title: str | None = Field(default=None, max_length=200)


class ThreadTitleUpdateRequest(StrictModel):
    title: str = Field(min_length=1, max_length=200)


class AttachmentInput(StrictModel):
    asset_id: str = Field(min_length=1, max_length=64)


class MessageOptions(StrictModel):
    # 所有任务模式均引用预先创建的产品草稿；素材仍按现有 OSS + 探测合同上传。
    project_id: str | None = Field(default=None, max_length=64)
    target_language: str | None = Field(default=None, max_length=16)
    response_locale: AssistantLocale = Field(
        default="zh-CN", validation_alias=AliasChoices("locale", "response_locale")
    )
    generation_mode: GenerationMode | None = None
    model_id: str | None = Field(
        default=None, max_length=64, validation_alias=AliasChoices("model", "model_id")
    )
    play_mode_id: str | None = Field(default=None, max_length=64)
    ratio: str | None = Field(default=None, max_length=16)
    duration_seconds: int | None = Field(
        default=None,
        ge=-1,
        le=3600,
        validation_alias=AliasChoices("duration", "duration_seconds"),
    )
    resolution: str | None = Field(default=None, max_length=32)
    audio_enabled: bool | None = Field(
        default=None, validation_alias=AliasChoices("audio", "audio_enabled")
    )
    model_parameters: dict[str, object] = Field(
        default_factory=dict,
        validation_alias=AliasChoices("model_params", "model_parameters"),
    )
    # 短剧解说 Agent 在浏览器上传阶段自动定位并确认硬字幕区域；该字段由
    # 确定性检测器提供，绝不交给 LLM 推断或修改。
    source_subtitle_layouts: dict[str, dict[str, object]] = Field(
        default_factory=dict
    )


class MessageCreateRequest(StrictModel):
    mode: Mode
    content: str = Field(default="", max_length=16000)
    attachments: list[AttachmentInput] = Field(default_factory=list, max_length=50)
    options: MessageOptions = Field(default_factory=MessageOptions)
    # `input` 是前端公开协议名称；保留 options 兼容已经接入的调用方。
    input: MessageOptions | None = None

    @model_validator(mode="after")
    def needs_content_or_attachment(self) -> "MessageCreateRequest":
        if not self.content.strip() and not self.attachments:
            raise ValueError("content or attachment is required")
        if self.input is not None:
            if self.options.model_dump(exclude_none=True, exclude_defaults=True):
                raise ValueError("input and options cannot be supplied together")
            self.options = self.input
        return self


class DraftCreateRequest(StrictModel):
    # chat 草稿仅复用现有受控图片 OSS 上传；普通文件不是当前 Asset/LLM 合同。
    mode: Literal[
        "chat", "short_drama_narration", "video_translation", "video_generation"
    ]


class ThreadData(StrictModel):
    id: str
    mode: Mode
    title: str | None = None
    created_at: str
    updated_at: str


class MessageData(StrictModel):
    id: str
    role: Literal["user", "assistant", "system"]
    mode: Mode
    content: str
    attachments: list[dict[str, object]]
    # Public progress state only. The underlying model task ID remains private.
    stream_status: Literal["running", "completed", "failed"] | None = None
    created_at: str


class RunStepOutputData(StrictModel):
    """A user-safe projection of one workflow result."""

    type: Literal["markdown", "file", "video"]
    content: str | None = None
    artifact_id: str | None = None
    kind: str | None = None
    filename: str | None = None
    content_type: str | None = None
    url: str | None = None
    preview_text: str | None = None
    preview_truncated: bool = False


class RunStepData(StrictModel):
    """One stable, reloadable step in the public Agent conversation timeline."""

    id: str
    title: str
    status: str
    outputs: list[RunStepOutputData] = Field(default_factory=list)
    error_code: str | None = None
    updated_at: str | None = None


class RunData(StrictModel):
    """Public Agent Run projection; never expose orchestration or model payloads."""

    id: str
    message_id: str
    assistant_message_id: str | None = None
    mode: Literal["short_drama_narration", "video_translation", "video_generation"]
    status: str
    project_id: str | None = None
    display_config: dict[str, str] = Field(default_factory=dict)
    steps: list[RunStepData] = Field(default_factory=list)
    video_url: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    created_at: str
    updated_at: str


class ThreadDetailData(ThreadData):
    messages: list[MessageData]
    has_more: bool = False
    next_before: str | None = None


class ThreadDeleteData(StrictModel):
    id: str


class MessageSubmitData(StrictModel):
    message: MessageData
    assistant_message: MessageData
    run: RunData | None = None
    thread_title: str | None = None


class ChatModelData(StrictModel):
    id: str
    display_name: str
    provider_code: str


class DraftData(StrictModel):
    project_id: str
    mode: Mode


def _thread(
    session: Session, *, user_id: str, thread_id: str, lock: bool = False
) -> ConversationThread:
    stmt = select(ConversationThread).where(
        ConversationThread.id == thread_id, ConversationThread.user_id == user_id
    )
    if lock:
        stmt = stmt.with_for_update()
    row = session.scalar(stmt)
    if row is None:
        raise ApiError("ASSISTANT_THREAD_NOT_FOUND", "Assistant thread not found", 404)
    return row


def _message_data(session: Session, row: ConversationMessage) -> MessageData:
    """Resolve the assets referenced by a message into safe display metadata."""
    attachments = list(row.attachments or [])
    asset_ids = [
        item.get("asset_id")
        for item in attachments
        if isinstance(item, dict) and isinstance(item.get("asset_id"), str)
    ]
    assets = (
        list(
            session.scalars(
                select(Asset).where(
                    Asset.user_id == row.user_id, Asset.id.in_(asset_ids)
                )
            )
        )
        if asset_ids
        else []
    )
    by_id = {asset.id: asset for asset in assets}
    display_attachments: list[dict[str, object]] = []
    for item in attachments:
        if not isinstance(item, dict):
            continue
        value = dict(item)
        asset_id = value.get("asset_id")
        asset = by_id.get(asset_id) if isinstance(asset_id, str) else None
        if asset is not None:
            value.update(
                {
                    "filename": asset.filename,
                    "asset_type": asset.asset_type,
                    "status": asset.status,
                    "url": asset.cdn_url,
                    "size_bytes": asset.size_bytes,
                }
            )
        display_attachments.append(value)
    stream_status: Literal["running", "completed", "failed"] | None = None
    if row.role == "assistant" and row.mode == "chat":
        task_id = _chat_task_id(row)
        task = session.get(ModelTask, task_id) if task_id else None
        if task is not None:
            stream_status = (
                "completed"
                if task.status in {"succeeded", "succeeded_with_partial_output"}
                else "failed"
                if task.status == "failed"
                else "running"
            )
    return MessageData(
        id=row.id,
        role=row.role,
        mode=row.mode,
        content=row.content,
        attachments=display_attachments,
        stream_status=stream_status,
        created_at=row.created_at.isoformat(),
    )


def _locale_instruction(locale: AssistantLocale) -> str:
    return _ASSISTANT_LOCALE_INSTRUCTIONS[locale]


def _chat_system_prompt(locale: AssistantLocale) -> str:
    return f"{_CHAT_SYSTEM_PROMPT}{_locale_instruction(locale)}"


def _chat_task_prompt(content: str, *, locale: AssistantLocale = "zh-CN") -> str:
    """保留单回合 prompt，供旧任务兼容和无历史上下文时降级使用。"""

    return f"{_chat_system_prompt(locale)}用户消息：{content.strip()}"


def _chat_token_estimate(value: object) -> int:
    """稳定的本地 Token 近似，用于不同 Provider 的统一上下文预算。"""

    text = str(value or "")
    chinese_count = len(re.findall(r"[\u3400-\u9fff\uf900-\ufaff]", text))
    latin_count = sum(len(item) for item in re.findall(r"[A-Za-z0-9_'-]+", text))
    punctuation_count = max(0, len(text) - chinese_count - latin_count)
    return chinese_count + (latin_count + 3) // 4 + (punctuation_count + 7) // 8


def _compact_chat_text(value: str, *, limit: int) -> str:
    normalized = re.sub(r"\s+", " ", value).strip()
    return normalized if len(normalized) <= limit else f"{normalized[: limit - 1]}…"


def _chat_terms(value: str) -> set[str]:
    normalized = value.lower()
    terms = set(re.findall(r"[a-z0-9_'-]{2,}", normalized))
    for phrase in re.findall(r"[\u3400-\u9fff\uf900-\ufaff]{2,}", normalized):
        terms.update(phrase[index : index + 2] for index in range(len(phrase) - 1))
    return terms


def _chat_turns(rows: list[ConversationMessage]) -> list[list[ConversationMessage]]:
    turns: list[list[ConversationMessage]] = []
    current: list[ConversationMessage] = []
    for row in rows:
        if row.role == "user":
            if current:
                turns.append(current)
            current = [row]
        elif current:
            current.append(row)
    if current:
        turns.append(current)
    return turns


def _relevant_chat_turns(
    rows: list[ConversationMessage], *, query: str, asset_ids: set[str]
) -> list[list[ConversationMessage]]:
    query_terms = _chat_terms(query)
    scored: list[tuple[int, int, list[ConversationMessage]]] = []
    for index, turn in enumerate(_chat_turns(rows)):
        text = "\n".join(row.content for row in turn)
        overlap = len(query_terms & _chat_terms(text))
        contains_task_asset = any(
            isinstance(item, dict) and item.get("asset_id") in asset_ids
            for row in turn
            for item in row.attachments or []
        )
        if overlap or contains_task_asset:
            scored.append((overlap + (1000 if contains_task_asset else 0), index, turn))
    selected = sorted(scored, key=lambda item: (-item[0], -item[1]))[
        :_CHAT_CONTEXT_RECALL_TURN_LIMIT
    ]
    return [item[2] for item in sorted(selected, key=lambda item: item[1])]


def _chat_summary(rows: list[ConversationMessage]) -> str | None:
    chunks: list[str] = []
    used = 0
    for row in reversed(rows):
        content = _compact_chat_text(row.content, limit=420)
        if not content or content == "正在生成回复…":
            continue
        prefix = "用户" if row.role == "user" else "助手"
        chunk = f"{prefix}：{content}"
        if used + len(chunk) + 1 > _CHAT_SUMMARY_CHAR_BUDGET:
            break
        chunks.append(chunk)
        used += len(chunk) + 1
    return "\n".join(reversed(chunks)) or None


def _memory_fact_candidates(message: ConversationMessage) -> list[tuple[str, str]]:
    text = re.sub(r"\s+", " ", message.content).strip()
    candidates: list[tuple[str, str]] = []
    for key, pattern in (
        (
            "preferred_name",
            r"(?:我叫|我的名字是|称呼我)[：: ]*([^，。！？,.!？]{1,40})",
        ),
        (
            "preferred_language",
            r"(?:请|以后请|后续请)?(?:用|使用)[：: ]*(中文|英文|日文|繁体中文)(?:回复|回答)?",
        ),
        (
            "response_style",
            r"(?:请|以后请|后续请)?(?:回复|回答)(?:得)?[：: ]*([^，。！？,.!？]{2,60})",
        ),
    ):
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            candidates.append((key, _compact_chat_text(match.group(1), limit=120)))
    return candidates


def _refresh_chat_memory(session: Session, *, thread_id: str, user_id: str) -> None:
    """在每个聊天回合完成后更新可审计、无需额外模型调用的长期记忆。"""

    thread = session.get(ConversationThread, thread_id)
    if thread is None:
        return
    rows = list(
        session.scalars(
            select(ConversationMessage)
            .where(
                ConversationMessage.thread_id == thread_id,
                ConversationMessage.user_id == user_id,
                ConversationMessage.mode == "chat",
            )
            .order_by(ConversationMessage.created_at)
        )
    )
    previous_memory = thread.chat_memory if isinstance(thread.chat_memory, dict) else {}
    facts_by_key = {
        str(item.get("key")): item
        for item in previous_memory.get("facts", [])
        if isinstance(item, dict) and isinstance(item.get("key"), str)
    }
    for row in rows:
        if row.role != "user":
            continue
        for key, value in _memory_fact_candidates(row):
            facts_by_key[key] = {
                "key": key,
                "value": value,
                "source_message_id": row.id,
                "updated_at": row.created_at.isoformat(),
            }
    user_rows = [row for row in rows if row.role == "user" and row.content.strip()]
    thread.chat_memory = {
        "facts": list(facts_by_key.values())[-_CHAT_MEMORY_FACT_LIMIT:],
        "active_goal": _compact_chat_text(user_rows[-1].content, limit=320)
        if user_rows
        else None,
    }
    thread.chat_summary = _chat_summary(rows[:-_CHAT_CONTEXT_RECENT_MESSAGE_LIMIT])
    thread.chat_memory_updated_at = utc_now()


def _memory_context(thread: ConversationThread) -> str | None:
    memory = thread.chat_memory if isinstance(thread.chat_memory, dict) else {}
    facts = [
        item
        for item in memory.get("facts", [])
        if isinstance(item, dict)
        and isinstance(item.get("key"), str)
        and isinstance(item.get("value"), str)
    ]
    active_goal = memory.get("active_goal")
    if not facts and not isinstance(active_goal, str):
        return None
    lines = ["以下是已确认的长期记忆；仅在与当前问题相关时使用："]
    lines.extend(f"- {item['key']}: {item['value']}" for item in facts)
    if isinstance(active_goal, str) and active_goal:
        lines.append(f"- active_goal: {active_goal}")
    return "\n".join(lines)


def _agent_run_context(
    session: Session,
    *,
    thread_id: str,
    assistant_created_at: datetime,
) -> str | None:
    """Return a compact, safe summary of prior non-chat runs in this thread.

    Agent runs stay operationally isolated: this is context only, never a tool
    grant.  It deliberately contains the user request and public result/config
    rather than provider payloads, task IDs, billing data, or internal project
    state.
    """

    rows = list(
        session.scalars(
            select(AgentRun)
            .where(
                AgentRun.thread_id == thread_id,
                AgentRun.created_at <= assistant_created_at,
            )
            .order_by(AgentRun.created_at.desc(), AgentRun.id.desc())
            .limit(_CHAT_CONTEXT_AGENT_RUN_LIMIT)
        )
    )
    if not rows:
        return None

    summaries: list[dict[str, object]] = []
    for row in reversed(rows):
        data = _run_data(session, row, include_steps=False)
        source = row.input_config if isinstance(row.input_config, dict) else {}
        item: dict[str, object] = {
            "mode": row.mode,
            "status": data.status,
        }
        content = source.get("content")
        if isinstance(content, str) and content.strip():
            item["user_request"] = _compact_chat_text(content, limit=1200)
        if data.display_config:
            item["selected_or_resolved_settings"] = data.display_config
        resolved = row.resolved_config if isinstance(row.resolved_config, dict) else {}
        requirements = resolved.get("requirements")
        if isinstance(requirements, str) and requirements.strip():
            item["inferred_requirements"] = _compact_chat_text(requirements, limit=700)
        if data.video_url:
            item["result_video_url"] = data.video_url
        if data.status == "failed" and data.error_message:
            item["error"] = _compact_chat_text(data.error_message, limit=240)
        summaries.append(item)

    rendered = json.dumps(summaries, ensure_ascii=False, separators=(",", ":"))
    rendered = _compact_chat_text(rendered, limit=_CHAT_CONTEXT_AGENT_RUN_CHAR_BUDGET)
    return (
        "以下是同一会话此前已执行的 Agent 任务摘要。仅在用户引用“刚才、上一个、"
        "该任务、生成的视频”等内容时使用；这些摘要不授予你创建、重试、修改或操作"
        "任何任务的能力：\n"
        f"{rendered}"
    )


def _chat_context_messages(
    session: Session,
    *,
    thread_id: str,
    user_id: str,
    assistant_message_id: str,
    task: ModelTask | None = None,
) -> list[dict[str, object]]:
    """按摘要、记忆、相关召回和 Token 预算构造冻结的聊天上下文。"""

    assistant = session.get(ConversationMessage, assistant_message_id)
    if assistant is None:
        raise ApiError(
            "ASSISTANT_STREAM_MESSAGE_MISSING",
            "Assistant stream message is unavailable",
            500,
        )
    thread = _thread(session, user_id=user_id, thread_id=thread_id)
    rows = list(
        session.scalars(
            select(ConversationMessage)
            .where(
                ConversationMessage.thread_id == thread_id,
                ConversationMessage.mode == "chat",
                ConversationMessage.created_at <= assistant.created_at,
                ConversationMessage.id != assistant_message_id,
            )
            .order_by(ConversationMessage.created_at)
        )
    )
    rows = [
        row for row in rows if row.content.strip() and row.content != "正在生成回复…"
    ]
    task_assets = (
        _task_assets_payload(session, task) if task is not None else {"image": []}
    )
    task_image_ids = {
        str(item["asset_id"])
        for item in task_assets["image"]
        if isinstance(item.get("asset_id"), str)
    }
    query = (
        task.prompt
        if task is not None and task.prompt
        else (rows[-1].content if rows else "")
    )
    memory = _memory_context(thread)
    summary = thread.chat_summary
    agent_runs = _agent_run_context(
        session,
        thread_id=thread_id,
        assistant_created_at=assistant.created_at,
    )
    locale = _task_output_locale(task)
    system_prompt = _chat_system_prompt(locale)
    base_tokens = _chat_token_estimate(system_prompt)
    base_tokens += _chat_token_estimate(memory) + _chat_token_estimate(summary)
    base_tokens += _chat_token_estimate(agent_runs)
    base_tokens += _CHAT_CONTEXT_RECALL_TOKEN_BUDGET
    recent_budget = max(1200, _CHAT_CONTEXT_INPUT_TOKEN_BUDGET - base_tokens)
    recent_rows: list[ConversationMessage] = []
    used_tokens = 0
    for row in reversed(rows):
        row_tokens = _chat_token_estimate(row.content)
        if recent_rows and (
            len(recent_rows) >= _CHAT_CONTEXT_RECENT_MESSAGE_LIMIT
            or used_tokens + row_tokens > recent_budget
        ):
            break
        recent_rows.append(row)
        used_tokens += row_tokens
    recent_rows.reverse()
    while recent_rows and recent_rows[0].role == "assistant":
        recent_rows.pop(0)
    recent_ids = {row.id for row in recent_rows}
    recalled_turns = _relevant_chat_turns(
        [row for row in rows if row.id not in recent_ids],
        query=query,
        asset_ids=task_image_ids,
    )
    recall_text = "\n".join(
        "\n".join(
            f"{'用户' if row.role == 'user' else '助手'}：{_compact_chat_text(row.content, limit=480)}"
            for row in turn
        )
        for turn in recalled_turns
    )
    recall_text = _compact_chat_text(
        recall_text, limit=_CHAT_CONTEXT_RECALL_TOKEN_BUDGET
    )

    asset_ids = [
        item.get("asset_id")
        for row in recent_rows
        if row.role == "user"
        for item in row.attachments or []
        if isinstance(item, dict) and isinstance(item.get("asset_id"), str)
    ]
    assets = (
        list(
            session.scalars(
                select(Asset).where(
                    Asset.user_id == user_id,
                    Asset.id.in_(asset_ids),
                    Asset.asset_type == "image",
                    Asset.status == "ready",
                )
            )
        )
        if asset_ids
        else []
    )
    assets_by_id = {asset.id: asset for asset in assets}
    current_text = rows[-1].content if rows else ""
    recheck_images = bool(
        re.search(r"看图|图片|画面|截图|ocr|识别图|图中", current_text, re.IGNORECASE)
    )
    historical_images_left = 2 if recheck_images else 0
    injected_task_image_ids: set[str] = set()

    messages: list[dict[str, object]] = [{"role": "system", "content": system_prompt}]
    if memory:
        messages.append({"role": "system", "content": memory})
    if summary:
        messages.append(
            {
                "role": "system",
                "content": f"以下是较早对话的滚动摘要：\n{summary}",
            }
        )
    if agent_runs:
        messages.append({"role": "system", "content": agent_runs})
    if recall_text:
        messages.append(
            {
                "role": "system",
                "content": f"以下是与当前问题相关的历史摘录：\n{recall_text}",
            }
        )
    for row in recent_rows:
        content = row.content.strip()
        if row.role == "assistant":
            messages.append({"role": "assistant", "content": content})
            continue
        parts: list[dict[str, object]] = [{"type": "text", "text": content}]
        for item in row.attachments or []:
            asset_id = item.get("asset_id") if isinstance(item, dict) else None
            asset = assets_by_id.get(asset_id) if isinstance(asset_id, str) else None
            include_image = isinstance(asset_id, str) and asset_id in task_image_ids
            if not include_image and recheck_images and historical_images_left:
                include_image = True
                historical_images_left -= 1
            if include_image and asset is not None and asset.cdn_url:
                parts.append({"type": "image_url", "image_url": {"url": asset.cdn_url}})
                if isinstance(asset_id, str) and asset_id in task_image_ids:
                    injected_task_image_ids.add(asset_id)
        messages.append({"role": "user", "content": parts})
    missing_task_images = [
        item
        for item in task_assets["image"]
        if isinstance(item.get("asset_id"), str)
        and item["asset_id"] not in injected_task_image_ids
        and isinstance(item.get("url"), str)
        and item["url"]
    ]
    if missing_task_images:
        messages.append(
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "请结合本次对话关联的图片继续回答。"},
                    *[
                        {"type": "image_url", "image_url": {"url": item["url"]}}
                        for item in missing_task_images
                    ],
                ],
            }
        )
    return messages


def _freeze_chat_context(
    session: Session,
    *,
    task: ModelTask,
    thread_id: str,
    assistant_message_id: str,
) -> None:
    """把提交时的会话快照写入任务，避免 Worker 恢复时丢失上下文。"""

    task.provider_request = {
        **(task.provider_request or {}),
        "chat_context_messages": _chat_context_messages(
            session,
            thread_id=thread_id,
            user_id=task.user_id,
            assistant_message_id=assistant_message_id,
            task=task,
        ),
    }


def _task_output_locale(task: ModelTask | None) -> AssistantLocale:
    if task is None:
        return "zh-CN"
    value = (
        task.provider_request.get("assistant_output_locale")
        if isinstance(task.provider_request, dict)
        else None
    )
    return value if value in _ASSISTANT_LOCALE_INSTRUCTIONS else "zh-CN"


def _frozen_chat_context(task: ModelTask) -> list[dict[str, object]] | None:
    context = (
        task.provider_request.get("chat_context_messages")
        if isinstance(task.provider_request, dict)
        else None
    )
    if (
        not isinstance(context, list)
        or not context
        or not all(isinstance(message, dict) for message in context)
    ):
        return None
    return context


def _conversation_title(content: str) -> str | None:
    normalized = re.sub(r"\s+", " ", content).strip()
    if not normalized:
        return None
    return normalized[:30] + ("…" if len(normalized) > 30 else "")


def _set_initial_thread_title(thread: ConversationThread, content: str) -> None:
    """Persist the first user prompt as a compact, stable conversation title."""

    if thread.title and thread.title.strip() != "新的 AI 对话":
        return
    title = _conversation_title(content)
    if title:
        thread.title = title


_DISPLAY_CONFIG_KEYS: dict[str, tuple[str, ...]] = {
    "short_drama_narration": (
        "narration_style",
        "video_ratio",
        "voice_id",
        "subtitle_style",
    ),
    "video_translation": (
        "target_language",
        "video_ratio",
        "voice_id",
        "subtitle_style",
    ),
    "video_generation": (
        "generation_mode",
        "ratio",
        "duration_seconds",
        "resolution",
        "audio_enabled",
    ),
}


def _run_display_config(session: Session, row: AgentRun) -> dict[str, str]:
    config = row.resolved_config if isinstance(row.resolved_config, dict) else {}
    display = {
        key: str(config[key])
        for key in _DISPLAY_CONFIG_KEYS[row.mode]
        if isinstance(config.get(key), (str, int, float, bool))
    }
    if row.mode == "video_generation" and isinstance(config.get("model_id"), str):
        model = session.get(Model, config["model_id"])
        display = {
            "model": model.display_name if model is not None else config["model_id"],
            **display,
        }
    return display


def _run_video_url(session: Session, row: AgentRun) -> str | None:
    result = row.result if isinstance(row.result, dict) else {}
    for key in ("video_url", "videoUrl", "url"):
        value = result.get(key)
        if isinstance(value, str) and value.startswith(("https://", "http://")):
            return value
    if row.project_id:
        artifact = session.scalar(
            select(RegisteredArtifact)
            .where(
                RegisteredArtifact.project_id == row.project_id,
                RegisteredArtifact.kind == "video",
            )
            .order_by(RegisteredArtifact.created_at.desc())
        )
        if artifact is not None and artifact.cdn_url.startswith(("https://", "http://")):
            return artifact.cdn_url
    if not row.model_task_id:
        return None
    output = session.scalar(
        select(ModelTaskOutput)
        .where(
            ModelTaskOutput.task_id == row.model_task_id,
            ModelTaskOutput.output_type == "video",
        )
        .order_by(ModelTaskOutput.sort_order)
    )
    return output.cdn_url if output is not None and output.cdn_url else None


_SHORT_DRAMA_PUBLIC_STEPS: tuple[tuple[str, str], ...] = (
    ("subtitle_recognition", "字幕识别"),
    ("plot_structure", "剧情结构理解"),
    ("conflict_highlights", "冲突与爽点定位"),
    ("highlight_scoring", "高光片段分析"),
    ("script_generation", "生成解说文案"),
    ("video_render", "生成解说视频"),
)
_SHORT_DRAMA_CONFIG_LABELS = {
    "narration_style": "解说类型",
    "video_ratio": "画面比例",
    "voice_id": "解说音色",
    "subtitle_style": "字幕样式",
}
_SHORT_DRAMA_RESULT_TEXT_LIMIT = 30_000
_ANALYSIS_ARTIFACT_MAX_BYTES = 1_048_576
_ANALYSIS_ARTIFACT_CACHE_LIMIT = 128
_analysis_artifact_cache: dict[str, str] = {}
_analysis_artifact_cache_lock = threading.Lock()


def _run_step_time(value: object) -> str | None:
    return value.isoformat() if isinstance(value, datetime) else None


def _run_step_status(value: str | None) -> str:
    normalized = str(value or "queued").lower()
    if normalized in {"succeeded", "succeeded_with_partial_output", "completed"}:
        return "completed"
    if normalized in {
        "submitting",
        "submitted",
        "processing",
        "analyzing",
        "rendering",
        "finalizing",
        "retrying",
    }:
        return "running"
    return normalized


def _result_containers(value: object) -> list[dict[str, object]]:
    """Unwrap the callback/polling envelopes without exposing the raw response."""

    containers: list[dict[str, object]] = []
    current = value
    for _ in range(3):
        if not isinstance(current, dict):
            break
        containers.append(current)
        nested = current.get("result")
        if not isinstance(nested, dict) or nested is current:
            break
        current = nested
    return containers


def _latest_workflow_attempts(
    session: Session, nodes: list[WorkflowNode]
) -> dict[str, WorkflowNodeAttempt]:
    if not nodes:
        return {}
    attempts = list(
        session.scalars(
            select(WorkflowNodeAttempt)
            .where(WorkflowNodeAttempt.workflow_node_id.in_([node.id for node in nodes]))
            .order_by(
                WorkflowNodeAttempt.workflow_node_id,
                WorkflowNodeAttempt.attempt_number.desc(),
            )
        )
    )
    latest_by_node_id: dict[str, WorkflowNodeAttempt] = {}
    for attempt in attempts:
        latest_by_node_id.setdefault(attempt.workflow_node_id, attempt)
    return latest_by_node_id


def _trusted_analysis_artifact_url(url: str, settings: Settings) -> bool:
    """Only read immutable analysis JSON from this deployment's public CDN."""

    if not settings.cdn_public_base_url:
        return False
    try:
        target = urlsplit(url)
        base = urlsplit(settings.cdn_public_base_url)
        same_port = target.port == base.port
    except ValueError:
        return False
    base_path = f"{base.path.rstrip('/')}/"
    return (
        target.scheme == "https"
        and target.hostname == base.hostname
        and same_port
        and not target.username
        and not target.password
        and target.path.startswith(base_path)
        and not target.fragment
    )


def _analysis_artifact_urls(value: object) -> list[str]:
    urls: list[str] = []
    for container in _result_containers(value):
        artifacts = container.get("artifacts")
        if not isinstance(artifacts, list):
            continue
        for artifact in artifacts:
            if not isinstance(artifact, dict) or artifact.get("kind") != "analysis":
                continue
            url = artifact.get("url")
            if isinstance(url, str) and url not in urls:
                urls.append(url)
    return urls


def _analysis_artifact_markdown(url: str, settings: Settings) -> str:
    """Read a validated public analysis artifact for pre-inline historical runs."""

    if not _trusted_analysis_artifact_url(url, settings):
        return ""
    with _analysis_artifact_cache_lock:
        cached = _analysis_artifact_cache.get(url)
    if cached is not None:
        return cached
    request = UrlRequest(url, method="GET", headers={"Accept": "application/json"})
    try:
        with urlopen(request, timeout=2) as response:
            final_url = response.geturl()
            if not _trusted_analysis_artifact_url(final_url, settings):
                return ""
            declared_length = response.headers.get("Content-Length")
            if declared_length and int(declared_length) > _ANALYSIS_ARTIFACT_MAX_BYTES:
                return ""
            raw = response.read(_ANALYSIS_ARTIFACT_MAX_BYTES + 1)
            content_encoding = str(response.headers.get("Content-Encoding") or "")
    except (HTTPError, URLError, TimeoutError, OSError, ValueError):
        return ""
    if len(raw) > _ANALYSIS_ARTIFACT_MAX_BYTES:
        return ""
    if content_encoding.lower() == "gzip":
        try:
            with gzip.GzipFile(fileobj=io.BytesIO(raw)) as stream:
                raw = stream.read(_ANALYSIS_ARTIFACT_MAX_BYTES + 1)
        except (gzip.BadGzipFile, EOFError, OSError):
            return ""
        if len(raw) > _ANALYSIS_ARTIFACT_MAX_BYTES:
            return ""
    elif content_encoding:
        return ""
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return ""
    analysis = payload.get("analysis") if isinstance(payload, dict) else None
    summary = analysis.get("summary") if isinstance(analysis, dict) else None
    if payload.get("schema_version") != "short-drama-analysis.v1" or not isinstance(
        summary, str
    ):
        return ""
    content = summary.strip()[:_SHORT_DRAMA_RESULT_TEXT_LIMIT]
    if not content:
        return ""
    with _analysis_artifact_cache_lock:
        if len(_analysis_artifact_cache) >= _ANALYSIS_ARTIFACT_CACHE_LIMIT:
            _analysis_artifact_cache.pop(next(iter(_analysis_artifact_cache)))
        _analysis_artifact_cache[url] = content
    return content


def _analysis_markdown(value: object, *, settings: Settings | None = None) -> str:
    for container in _result_containers(value):
        analysis = container.get("analysis")
        if isinstance(analysis, dict) and isinstance(analysis.get("summary"), str):
            return analysis["summary"].strip()[:_SHORT_DRAMA_RESULT_TEXT_LIMIT]
        preview = container.get("analysis_preview")
        if isinstance(preview, str):
            return preview.strip()[:_SHORT_DRAMA_RESULT_TEXT_LIMIT]
    if settings is not None:
        for url in _analysis_artifact_urls(value):
            content = _analysis_artifact_markdown(url, settings)
            if content:
                return content
    return ""


def _analysis_step_markdown(summary: str, step_name: str) -> str:
    if not summary:
        return ""
    section_five = re.search(r"(?m)^##\s*五[、.]", summary)
    section_six = re.search(r"(?m)^##\s*六[、.]", summary)
    if step_name == "plot_structure":
        return summary[: section_five.start()].strip() if section_five else summary
    if not section_five:
        return ""
    focus_end = section_six.start() if section_six else len(summary)
    focus = summary[section_five.start() : focus_end].strip()
    original_sound = re.search(r"(?m)^-\s*建议保留原声片段[：:]", focus)
    if step_name == "conflict_highlights":
        return focus[: original_sound.start()].strip() if original_sound else focus
    if step_name == "highlight_scoring" and original_sound:
        return ("## 高光片段与原声建议\n" + focus[original_sound.start() :].strip())[
            :_SHORT_DRAMA_RESULT_TEXT_LIMIT
        ]
    return ""


def _subtitle_step_outputs(
    value: object, *, video_filenames: dict[str, str]
) -> list[RunStepOutputData]:
    records: list[object] = []
    for container in _result_containers(value):
        if isinstance(container.get("subtitles"), list):
            records = list(container["subtitles"])
            break
    outputs: list[RunStepOutputData] = []
    for index, record in enumerate(records, 1):
        if not isinstance(record, dict):
            continue
        artifact = record.get("artifact")
        artifact = artifact if isinstance(artifact, dict) else {}
        url = artifact.get("url") or record.get("subtitle_url")
        if not isinstance(url, str) or not url.startswith(("https://", "http://")):
            continue
        source_id = record.get("source_asset_id")
        source_filename = (
            video_filenames.get(source_id, "") if isinstance(source_id, str) else ""
        )
        fallback_name = (
            f"{source_filename.rsplit('.', 1)[0]}.srt"
            if source_filename
            else f"subtitle-{index}.srt"
        )
        filename = record.get("subtitle_name") or fallback_name
        artifact_id = artifact.get("artifact_id") or record.get("asset_id")
        preview = record.get("preview_text")
        outputs.append(
            RunStepOutputData(
                type="file",
                artifact_id=artifact_id if isinstance(artifact_id, str) else None,
                kind="subtitle",
                filename=str(filename),
                content_type="application/x-subrip; charset=utf-8",
                url=url,
                preview_text=(
                    preview[:_SHORT_DRAMA_RESULT_TEXT_LIMIT]
                    if isinstance(preview, str)
                    else None
                ),
                preview_truncated=bool(record.get("preview_truncated")),
            )
        )
    return outputs


def _script_step_markdown(value: object) -> str:
    editor: dict[str, object] | None = None
    for container in _result_containers(value):
        candidate = container.get("editor_draft")
        if isinstance(candidate, dict):
            editor = candidate
            break
    tracks = editor.get("tracks") if editor is not None else None
    items = (
        tracks[0].get("items")
        if isinstance(tracks, list) and tracks and isinstance(tracks[0], dict)
        else None
    )
    if not isinstance(items, list):
        return ""
    lines = ["## 解说文案"]
    for index, item in enumerate(items[:120], 1):
        if not isinstance(item, dict):
            continue
        narration = item.get("narration")
        if not isinstance(narration, str) or not narration.strip():
            continue
        timestamp = item.get("timestamp")
        if not isinstance(timestamp, str):
            start, end = item.get("start"), item.get("end")
            timestamp = (
                f"{start:g}s–{end:g}s"
                if type(start) in {int, float} and type(end) in {int, float}
                else ""
            )
        prefix = f"**{index}. {timestamp}**" if timestamp else f"**{index}.**"
        lines.append(f"{prefix}\n{narration.strip()}")
    content = "\n\n".join(lines)
    if len(items) > 120:
        content += "\n\n_文案较长，聊天框仅展示前 120 个片段；完整内容可在项目中查看。_"
    return content[:_SHORT_DRAMA_RESULT_TEXT_LIMIT]


def _registered_result_outputs(
    session: Session, *, project_id: str | None
) -> list[RunStepOutputData]:
    if not project_id:
        return []
    artifacts = list(
        session.scalars(
            select(RegisteredArtifact)
            .where(RegisteredArtifact.project_id == project_id)
            .order_by(RegisteredArtifact.created_at, RegisteredArtifact.id)
        )
    )
    names = {
        "video": "短剧解说成片.mp4",
        "subtitle": "短剧解说字幕.srt",
        "voice": "短剧解说音频.wav",
        "timeline": "短剧解说时间线.json",
    }
    content_types = {
        "video": "video/mp4",
        "subtitle": "application/x-subrip; charset=utf-8",
        "voice": "audio/wav",
        "timeline": "application/json; charset=utf-8",
    }
    return [
        RunStepOutputData(
            type="video" if artifact.kind == "video" else "file",
            artifact_id=artifact.id,
            kind=artifact.kind,
            filename=names.get(artifact.kind, f"{artifact.kind}.bin"),
            content_type=artifact.content_type or content_types.get(artifact.kind),
            url=artifact.cdn_url,
        )
        for artifact in artifacts
        if artifact.cdn_url.startswith(("https://", "http://"))
    ]


def _step_error_code(attempt: WorkflowNodeAttempt | None) -> str | None:
    if attempt is None:
        return None
    for container in _result_containers(attempt.result):
        error = container.get("error")
        if isinstance(error, dict) and isinstance(error.get("code"), str):
            return error["code"]
    return None


def _short_drama_run_steps(
    session: Session,
    *,
    row: AgentRun,
    workflow: Workflow | None,
    settings: Settings | None = None,
) -> list[RunStepData]:
    task = session.get(ModelTask, row.model_task_id) if row.model_task_id else None
    if workflow is not None:
        inference_status = "completed"
    elif row.status == "failed":
        inference_status = "failed"
    else:
        inference_status = _run_step_status(task.status if task is not None else row.status)
    inference_outputs: list[RunStepOutputData] = []
    if inference_status == "completed":
        display = _run_display_config(session, row)
        if display:
            content = "已理解你的需求，并冻结本次执行参数：\n\n" + "\n".join(
                f"- {_SHORT_DRAMA_CONFIG_LABELS.get(key, key)}：{value}"
                for key, value in display.items()
            )
            inference_outputs.append(RunStepOutputData(type="markdown", content=content))
    steps = [
        RunStepData(
            id="requirements_inference",
            title="理解需求与确定参数",
            status=inference_status,
            outputs=inference_outputs,
            error_code=row.error_code if inference_status == "failed" else None,
            updated_at=_run_step_time(
                getattr(task, "updated_at", None) or row.updated_at
            ),
        )
    ]
    if workflow is None:
        return steps

    nodes = list(
        session.scalars(
            select(WorkflowNode)
            .where(WorkflowNode.workflow_id == workflow.id)
            .order_by(WorkflowNode.created_at, WorkflowNode.id)
        )
    )
    nodes_by_name = {node.name: node for node in nodes}
    attempts = _latest_workflow_attempts(session, nodes)
    video_filenames = {
        asset.id: asset.filename
        for asset in session.scalars(
            select(Asset).where(
                Asset.project_id == workflow.project_id,
                Asset.asset_type == "video",
            )
        )
    }
    for name, title in _SHORT_DRAMA_PUBLIC_STEPS:
        node = nodes_by_name.get(name)
        if node is None:
            continue
        attempt = attempts.get(node.id)
        outputs: list[RunStepOutputData] = []
        if attempt is not None and node.state == "completed":
            if name == "subtitle_recognition":
                outputs = _subtitle_step_outputs(
                    attempt.result, video_filenames=video_filenames
                )
            elif name in {
                "plot_structure",
                "conflict_highlights",
                "highlight_scoring",
            }:
                content = _analysis_step_markdown(
                    _analysis_markdown(attempt.result, settings=settings), name
                )
                if content:
                    outputs = [RunStepOutputData(type="markdown", content=content)]
            elif name == "script_generation":
                content = _script_step_markdown(attempt.result)
                if content:
                    outputs = [RunStepOutputData(type="markdown", content=content)]
            elif name == "video_render":
                outputs = _registered_result_outputs(
                    session, project_id=row.project_id or workflow.project_id
                )
        steps.append(
            RunStepData(
                id=name,
                title=title,
                status=_run_step_status(node.state),
                outputs=outputs,
                error_code=_step_error_code(attempt),
                updated_at=_run_step_time(
                    (attempt.completed_at or attempt.created_at)
                    if attempt is not None
                    else node.updated_at
                ),
            )
        )
    return steps


def _run_data(
    session: Session,
    row: AgentRun,
    *,
    include_steps: bool = True,
    settings: Settings | None = None,
) -> RunData:
    status_value = row.status
    error_code = row.error_code
    error_message = row.error_message
    # 推导 LLM task 只用于进入工作流；一旦 workflow 已创建，进度卡必须展示
    # 真实产品工作流，而非已完成的推导任务。
    workflow: Workflow | None = None
    if row.workflow_id:
        workflow = session.get(Workflow, row.workflow_id)
        if workflow is not None:
            status_value = workflow.state
    elif row.model_task_id and row.status != "failed":
        task = session.get(ModelTask, row.model_task_id)
        if task is not None:
            # ModelTask 的 submitting/finalizing 等内部状态不能直接泄漏为
            # 前端未知 Run 状态，否则浏览器会误判任务已结束并停止 SSE/轮询。
            status_value = _run_step_status(task.status)
            # 兼容历史 Run：即使旧任务尚未经过 Run 对账，也不能向前端隐藏
            # 已发生的 Provider 或推导错误。
            if task.status == "failed":
                error_code = task.error_code or error_code
                error_message = task.error_message or error_message
    assistant_message_id = (
        row.input_config.get("assistant_message_id")
        if isinstance(row.input_config.get("assistant_message_id"), str)
        else None
    )
    return RunData(
        id=row.id,
        message_id=row.message_id,
        assistant_message_id=assistant_message_id,
        mode=row.mode,
        status=status_value,
        project_id=row.project_id,
        display_config=_run_display_config(session, row),
        steps=(
            _short_drama_run_steps(
                session, row=row, workflow=workflow, settings=settings
            )
            if include_steps and row.mode == "short_drama_narration"
            else []
        ),
        video_url=_run_video_url(session, row),
        error_code=error_code,
        error_message=error_message,
        created_at=row.created_at.isoformat(),
        updated_at=row.updated_at.isoformat(),
    )


def _active_run_core_attempt(
    session: Session, row: AgentRun
) -> tuple[str, str] | None:
    """Return the current public step and Core task without exposing it in DTOs."""

    if not row.workflow_id:
        return None
    node = session.scalar(
        select(WorkflowNode)
        .where(
            WorkflowNode.workflow_id == row.workflow_id,
            WorkflowNode.state == "running",
        )
        .order_by(WorkflowNode.updated_at.desc(), WorkflowNode.id)
        .limit(1)
    )
    if node is None:
        return None
    attempt = session.scalar(
        select(WorkflowNodeAttempt)
        .where(
            WorkflowNodeAttempt.workflow_node_id == node.id,
            WorkflowNodeAttempt.state == "running",
            WorkflowNodeAttempt.core_task_id.is_not(None),
        )
        .order_by(WorkflowNodeAttempt.attempt_number.desc())
        .limit(1)
    )
    if attempt is None or not attempt.core_task_id:
        return None
    return node.name, attempt.core_task_id


def _agent_stream_step_snapshot(
    *,
    run_id: str,
    node_name: str,
    core_task_id: str,
    result: object,
) -> dict[str, object] | None:
    """Map a Core public stream snapshot into the assistant step allowlist."""

    if not isinstance(result, dict) or not isinstance(result.get("stream"), dict):
        return None
    stream = result["stream"]
    sequence = stream.get("sequence")
    stage = stream.get("stage")
    outputs = stream.get("outputs")
    if type(sequence) is not int or sequence < 1 or not isinstance(stage, str):
        return None
    outputs = outputs if isinstance(outputs, dict) else {}
    if stage == "analysis":
        step_id = node_name if node_name in {
            "plot_structure",
            "conflict_highlights",
            "highlight_scoring",
        } else "plot_structure"
        content = outputs.get("analysis")
        label = "正在理解剧情结构…"
    elif stage == "generation":
        step_id = "script_generation"
        draft = outputs.get("generation")
        content = f"## 解说文案草稿\n\n{draft}" if isinstance(draft, str) else ""
        label = "正在生成解说文案…"
    elif stage == "matching":
        step_id = "script_generation"
        draft = outputs.get("generation")
        content = f"## 解说文案草稿\n\n{draft}" if isinstance(draft, str) else ""
        label = "正在匹配解说文案与视频画面…"
    elif stage == "repair":
        step_id = "script_generation"
        draft = outputs.get("generation")
        content = f"## 解说文案草稿\n\n{draft}" if isinstance(draft, str) else ""
        label = "正在校正文案时间线…"
    else:
        return None
    return {
        "run_id": run_id,
        "event_id": f"{core_task_id}:{sequence}",
        "sequence": sequence,
        "step_id": step_id,
        "phase": stage,
        "status_label": label,
        "content": content if isinstance(content, str) else "",
        "draft": True,
        "completed": bool(stream.get("completed")),
    }
def _asset_rows(
    session: Session, *, user_id: str, project_id: str, attachment_ids: list[str]
) -> list[Asset]:
    if not attachment_ids:
        return []
    rows = list(
        session.scalars(
            select(Asset).where(
                Asset.user_id == user_id,
                Asset.project_id == project_id,
                Asset.id.in_(attachment_ids),
            )
        )
    )
    if len(rows) != len(attachment_ids):
        raise ApiError(
            "ASSISTANT_ASSET_INVALID", "Attachment does not belong to this project", 422
        )
    if any(row.status != "ready" for row in rows):
        raise ApiError("ASSISTANT_ASSET_NOT_READY", "Attachment is not ready", 409)
    return rows


def _require_project(
    session: Session, *, user_id: str, project_id: str | None, product: str
) -> Project:
    if not project_id:
        raise ApiError(
            "ASSISTANT_PROJECT_REQUIRED",
            "Create an assistant draft and upload media before submitting",
            422,
        )
    project = session.scalar(
        select(Project)
        .where(
            Project.id == project_id,
            Project.user_id == user_id,
            Project.product == product,
        )
        .with_for_update()
    )
    if project is None:
        raise ApiError(
            "ASSISTANT_PROJECT_INVALID", "Assistant project is not available", 404
        )
    return project


def _assert_agent_task_draft(project: Project) -> None:
    """Agent 任务必须独占一个未执行过的产品草稿。"""

    if project.status not in {"draft", "ready"}:
        raise ApiError(
            "ASSISTANT_TASK_DRAFT_LOCKED",
            "Each agent task must use a new draft project",
            409,
        )


def _assert_short_drama_input(rows: list[Asset]) -> None:
    if not rows or any(item.asset_type != "video" for item in rows):
        raise ApiError(
            "SHORT_DRAMA_VIDEO_REQUIRED",
            "Short drama narration requires a ready video attachment",
            422,
        )


def _assert_translation_input(rows: list[Asset], target_language: str | None) -> None:
    if len(rows) != 1 or rows[0].asset_type != "video":
        raise ApiError(
            "VIDEO_TRANSLATION_VIDEO_REQUIRED",
            "Video translation requires exactly one ready video attachment",
            422,
        )
    if target_language not in SUPPORTED_LANGUAGES:
        raise ApiError(
            "TARGET_LANGUAGE_UNSUPPORTED", "Target language is unsupported", 422
        )


def _assert_generation_mode(mode: str, rows: list[Asset]) -> None:
    images = [row for row in rows if row.asset_type == "image"]
    if mode == "text_to_video" and rows:
        raise ApiError(
            "GENERATION_MODE_ATTACHMENTS_INVALID",
            "Text-to-video does not accept reference attachments",
            422,
        )
    if mode == "first_frame" and (len(images) != 1 or len(rows) != 1):
        raise ApiError(
            "GENERATION_MODE_ATTACHMENTS_INVALID",
            "First-frame generation requires exactly one image",
            422,
        )
    if mode == "first_last_frame" and (len(images) != 2 or len(rows) != 2):
        raise ApiError(
            "GENERATION_MODE_ATTACHMENTS_INVALID",
            "First-last-frame generation requires exactly two images",
            422,
        )
    if mode == "multi_subject_reference_audio_visual" and not rows:
        raise ApiError(
            "GENERATION_MODE_ATTACHMENTS_INVALID",
            "Multi-subject reference generation requires media attachments",
            422,
        )


def _inference_voice_ids(
    settings: Settings, *, target_language: str | None = None
) -> list[str]:
    """读取 LLM 可选择的实时可用音色，不生成虚构 voice ID。"""
    try:
        voices = HttpCoreClient(
            base_url=str(settings.core_base_url),
            request_token=settings.core_request_token,
        ).get_voice_capabilities()
    except CoreClientError as error:
        raise ApiError(
            "CORE_CAPABILITIES_UNAVAILABLE",
            "Core voice capabilities are unavailable",
            503,
        ) from error
    if not voices:
        raise ApiError(
            "CORE_VOICE_UNAVAILABLE", "No callable Core voice is configured", 503
        )
    selected = [
        item.voice_id
        for item in voices
        if not target_language or target_language in item.languages
    ]
    return selected or [item.voice_id for item in voices]


def _inference_prompt(
    *,
    mode: str,
    content: str,
    target_language: str | None,
    voice_ids: list[str],
    locale: AssistantLocale,
) -> str:
    fixed = ""
    if mode == "video_translation":
        fixed = f" target_language 必须为 {target_language!r}；不要输出 original_sound_mode 或 subtitle_style。"
    return (
        "你是受控视频产品参数规划器。只输出一个 JSON object，禁止 Markdown、解释和额外字段。"
        f" {_locale_instruction(locale)} JSON 的字段名、枚举值和 ID 必须保持规定的原样；仅自然语言字段值遵循该语种。"
        f" 当前模式={mode}。用户需求：{content!r}。可选 voice_id 只能是：{voice_ids!r}。{fixed}"
        " short_drama_narration 输出字段：narration_style（从 霸总/甜宠、逆袭/复仇、家庭伦理、古装/权谋、悬疑/犯罪、都市情感、年代/乡村 选一）、video_ratio（original/9:16/16:9/4:3/3:4/1:1；除非用户明确要求固定比例，否则必须输出 original）、voice_id、requirements、target_duration_seconds（10 到 1800 的整数秒；用户明确时长时必须严格提取，否则根据需求给出合理目标）、original_sound_ratio（0 到 100 之间的整数）。不要输出 subtitle_style。"
        " video_translation 输出字段：voice_id、video_ratio（original/9:16/16:9/1:1/4:3/3:4）、preserve_source_subtitles（boolean）。"
    )


def _start_llm_task(
    session: Session,
    *,
    user_id: str,
    idempotency_key: str,
    prompt: str,
    project_id: str | None = None,
    image_asset_ids: list[str] | None = None,
    model_id: str | None = None,
    locale: AssistantLocale = "zh-CN",
) -> str:
    statement = select(Model).where(
        Model.model_type == "llm", Model.is_enabled.is_(True)
    )
    if model_id:
        statement = statement.where(Model.id == model_id)
    else:
        statement = statement.order_by(
            Model.is_default.desc(), Model.sort_order.desc(), Model.id
        )
    model = session.scalar(statement)
    if model is None:
        raise ApiError(
            "ASSISTANT_LLM_UNAVAILABLE",
            "No callable LLM is configured for assistant inference",
            503,
        )
    task = _create_model_task(
        session=session,
        user_id=user_id,
        project_id=project_id,
        body=LlmCompletionRequest(
            model_id=model.id,
            project_id=project_id,
            prompt=prompt,
            image_asset_ids=image_asset_ids or [],
        ),
        task_type="llm",
    )
    task.idempotency_key = idempotency_key
    task.provider_request = {
        **(task.provider_request or {}),
        "assistant_output_locale": locale,
    }
    return task.id


def _start_inference_task(
    session: Session, *, user_id: str, run: AgentRun, prompt: str
) -> str:
    locale = (
        run.input_config.get("response_locale")
        if isinstance(run.input_config, dict)
        else None
    )
    task_id = _start_llm_task(
        session,
        user_id=user_id,
        idempotency_key=run.idempotency_key,
        prompt=prompt,
        locale=locale if locale in _ASSISTANT_LOCALE_INSTRUCTIONS else "zh-CN",
    )
    run.model_task_id = task_id
    run.status = "running"
    return task_id


def _parse_inference(text: str) -> dict[str, object]:
    candidate = text.strip()
    if candidate.startswith("```"):
        candidate = candidate.split("\n", 1)[1] if "\n" in candidate else ""
        candidate = candidate.rsplit("```", 1)[0].strip()
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError as error:
        raise ApiError(
            "ASSISTANT_INFERENCE_INVALID",
            "LLM did not return valid structured parameters",
            502,
        ) from error
    if not isinstance(parsed, dict):
        raise ApiError(
            "ASSISTANT_INFERENCE_INVALID", "LLM did not return a parameter object", 502
        )
    return parsed


def _chat_task_id(message: ConversationMessage) -> str | None:
    if message.idempotency_key and message.idempotency_key.startswith("chat_llm:"):
        return message.idempotency_key.removeprefix("chat_llm:") or None
    for item in message.attachments or []:
        if (
            isinstance(item, dict)
            and item.get("internal_type") == "chat_llm"
            and isinstance(item.get("task_id"), str)
        ):
            return item["task_id"]
    return None


def _prepare_chat_retry(
    session: Session,
    *,
    thread: ConversationThread,
    user_id: str,
    assistant_message_id: str,
    idempotency_key: str,
) -> tuple[ConversationMessage, str]:
    """基于已有回复重新执行，但只新增当前时间的 assistant 消息。"""

    previous_assistant = session.get(ConversationMessage, assistant_message_id)
    if (
        previous_assistant is None
        or previous_assistant.thread_id != thread.id
        or previous_assistant.user_id != user_id
        or previous_assistant.role != "assistant"
        or previous_assistant.mode != "chat"
    ):
        raise ApiError(
            "ASSISTANT_RETRY_MESSAGE_INVALID",
            "The assistant message cannot be retried",
            404,
        )
    previous_task_id = _chat_task_id(previous_assistant)
    previous_task = (
        session.get(ModelTask, previous_task_id) if previous_task_id else None
    )
    if previous_task is None:
        raise ApiError(
            "ASSISTANT_RETRY_TASK_MISSING",
            "The original model task is unavailable",
            409,
        )

    prompt = (previous_task.prompt or "").strip()
    if not prompt:
        raise ApiError(
            "ASSISTANT_RETRY_SOURCE_MISSING",
            "The original user message is unavailable",
            409,
        )
    task_assets = _task_assets_payload(session, previous_task)
    if task_assets["video"] or task_assets["audio"]:
        raise ApiError(
            "ASSISTANT_RETRY_ATTACHMENT_INVALID",
            "The original image attachment is unavailable",
            409,
        )
    attachment_ids = [str(item["asset_id"]) for item in task_assets["image"]]
    project_id = previous_task.project_id if attachment_ids else None
    if attachment_ids:
        if project_id is None:
            raise ApiError(
                "ASSISTANT_RETRY_ATTACHMENT_INVALID",
                "The original image attachment is unavailable",
                409,
            )
        _require_project(
            session,
            user_id=user_id,
            project_id=project_id,
            product="ai_video",
        )

    task_id = _start_llm_task(
        session,
        user_id=user_id,
        idempotency_key=f"chat-retry:{idempotency_key}",
        prompt=prompt,
        project_id=project_id,
        image_asset_ids=attachment_ids,
        model_id=previous_task.model_id,
        locale=_task_output_locale(previous_task),
    )
    assistant = ConversationMessage(
        id=_id("ams"),
        thread_id=thread.id,
        user_id=user_id,
        role="assistant",
        mode="chat",
        content="正在生成回复…",
        attachments=[],
        idempotency_key=f"chat_llm:{task_id}",
    )
    session.add(assistant)
    session.flush()
    stream_task = session.get(ModelTask, task_id)
    if stream_task is None:
        raise ApiError(
            "ASSISTANT_STREAM_TASK_MISSING",
            "Assistant stream task is unavailable",
            500,
        )
    stream_task.poll_lease_token = f"assistant-stream:{assistant.id}"
    stream_task.poll_lease_until = utc_now() + timedelta(
        seconds=_CHAT_STREAM_LEASE_SECONDS
    )
    _freeze_chat_context(
        session,
        task=stream_task,
        thread_id=thread.id,
        assistant_message_id=assistant.id,
    )
    return assistant, task_id


def _advance_chat_message(session: Session, message: ConversationMessage) -> None:
    """把已有异步 LLM task 的终态回复写回 assistant message；不创建 AgentRun。"""
    task_id = _chat_task_id(message)
    if not task_id:
        return
    task = session.get(ModelTask, task_id)
    if task is None or task.status not in {"succeeded", "failed"}:
        return
    # 流式回复已经逐段持久化到消息本身。后续线程刷新不得再用另一条迟到的
    # ModelTaskOutput 覆盖用户已经看到的完整回答。
    if message.content not in {"正在生成回复…", "对话回复生成失败，请重试。"}:
        return
    if task.status == "failed":
        message.content = "对话回复生成失败，请重试。"
    else:
        output = session.scalar(
            select(ModelTaskOutput)
            .where(
                ModelTaskOutput.task_id == task.id,
                ModelTaskOutput.output_type == "text",
            )
            .order_by(ModelTaskOutput.sort_order)
        )
        message.content = (
            output.text_content
            if output is not None and output.text_content
            else "对话回复生成失败，请重试。"
        )
    message.attachments = []
    if task.status == "succeeded" and message.content != "对话回复生成失败，请重试。":
        _refresh_chat_memory(
            session, thread_id=message.thread_id, user_id=message.user_id
        )


def _required_string(
    payload: dict[str, object], key: str, allowed: set[str] | None = None
) -> str:
    value = payload.get(key)
    if (
        not isinstance(value, str)
        or not value.strip()
        or (allowed is not None and value not in allowed)
    ):
        raise ApiError(
            "ASSISTANT_INFERENCE_INVALID", f"LLM returned an invalid {key}", 502
        )
    return value


def _normalized_original_sound_ratio(payload: dict[str, object]) -> int:
    """将模型返回的数值向下取整，并收敛到产品支持的 0..100 区间。"""
    value = payload.get("original_sound_ratio")
    if isinstance(value, bool):
        raise ApiError(
            "ASSISTANT_INFERENCE_INVALID",
            "LLM returned an invalid original_sound_ratio",
            502,
        )
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        number = Decimal("NaN")
    if not number.is_finite():
        raise ApiError(
            "ASSISTANT_INFERENCE_INVALID",
            "LLM returned an invalid original_sound_ratio",
            502,
        )
    floored = int(number.to_integral_value(rounding=ROUND_FLOOR))
    return max(0, min(100, floored))


def _normalized_target_duration_seconds(
    payload: dict[str, object], rows: list[Asset]
) -> int:
    """校验 Agent 提取的目标时长，并限制在已探测的素材总时长内。"""

    value = payload.get("target_duration_seconds")
    if isinstance(value, bool):
        raise ApiError(
            "ASSISTANT_INFERENCE_INVALID",
            "LLM returned an invalid target_duration_seconds",
            502,
        )
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        number = Decimal("NaN")
    if not number.is_finite():
        raise ApiError(
            "ASSISTANT_INFERENCE_INVALID",
            "LLM returned an invalid target_duration_seconds",
            502,
        )
    target = int(number.to_integral_value(rounding=ROUND_FLOOR))
    if not 10 <= target <= 1800:
        raise ApiError(
            "ASSISTANT_INFERENCE_INVALID",
            "LLM returned an invalid target_duration_seconds",
            502,
        )
    known_total = sum(
        float(row.duration_seconds)
        for row in rows
        if isinstance(row.duration_seconds, (int, float))
        and not isinstance(row.duration_seconds, bool)
        and float(row.duration_seconds) > 0
    )
    if known_total > 0:
        target = min(target, max(10, int(known_total)))
    return target


_ASSISTANT_DEFAULT_SOURCE_SUBTITLE_REGION = {
    "x": 0.0,
    "y": 0.78,
    "width": 1.0,
    "height": 0.12,
}


def _assistant_source_subtitle_layouts(
    rows: list[Asset], value: object
) -> dict[str, dict[str, object]]:
    """将本地检测坐标冻结为 confirmed；缺失或异常时使用默认遮罩。"""

    supplied = value if isinstance(value, dict) else {}
    resolved: dict[str, dict[str, object]] = {}
    for asset in rows:
        raw = supplied.get(asset.id)
        raw = raw if isinstance(raw, dict) else {}
        region = raw.get("region")
        region = region if isinstance(region, dict) else {}
        try:
            normalized = {
                key: float(region[key])
                for key in ("x", "y", "width", "height")
            }
        except (KeyError, TypeError, ValueError):
            normalized = dict(_ASSISTANT_DEFAULT_SOURCE_SUBTITLE_REGION)
        if not (
            0 <= normalized["x"] <= 1
            and 0 <= normalized["y"] <= 1
            and 0 < normalized["width"] <= 1
            and 0 < normalized["height"] <= 1
            and normalized["x"] + normalized["width"] <= 1
            and normalized["y"] + normalized["height"] <= 1
        ):
            normalized = dict(_ASSISTANT_DEFAULT_SOURCE_SUBTITLE_REGION)
        resolved[asset.id] = {
            "status": "confirmed",
            "region": normalized,
            **(
                {"detected_confidence": float(raw["detected_confidence"])}
                if isinstance(raw.get("detected_confidence"), (int, float))
                and not isinstance(raw.get("detected_confidence"), bool)
                and 0 <= float(raw["detected_confidence"]) <= 1
                else {}
            ),
        }
    return resolved


def _assistant_narration_subtitle_position(
    layouts: dict[str, dict[str, object]],
) -> dict[str, float]:
    """默认把解说字幕中心放到原字幕中心，而不是固定堆叠在其上方。"""

    centers: list[float] = []
    for layout in layouts.values():
        region = layout.get("region")
        if layout.get("status") != "confirmed" or not isinstance(region, dict):
            continue
        try:
            centers.append(float(region["y"]) + float(region["height"]) / 2)
        except (KeyError, TypeError, ValueError):
            continue
    centers.sort()
    y = centers[len(centers) // 2] if centers else 0.84
    return {"y": min(0.96, max(0.04, y)), "font_scale": 0.9}


def _advance_inference_run(session: Session, row: AgentRun) -> None:
    """仅在 LLM task 已完成后创建产品工作流，防止占位默认值直接启动任务。"""
    if (
        row.mode not in {"short_drama_narration", "video_translation"}
        or row.workflow_id
        or not row.model_task_id
    ):
        return
    task = session.get(ModelTask, row.model_task_id)
    if task is None:
        row.status, row.error_code, row.error_message = (
            "failed",
            "ASSISTANT_INFERENCE_NOT_FOUND",
            "Assistant inference task is missing",
        )
        return
    # LLM 的结果在提交响应中已经完整落库，无需像图片/视频一样等待 OSS
    # 转存或媒体探测。历史遗留的 finalizing 任务也在读取 Run 时安全自愈。
    if task.task_type == "llm" and task.status == "finalizing":
        _mark_completed(session, task)
    if task.status == "failed":
        row.status, row.error_code, row.error_message = (
            "failed",
            task.error_code or "ASSISTANT_INFERENCE_FAILED",
            task.error_message or "Assistant inference failed",
        )
        return
    if task.status != "succeeded":
        return
    output = session.scalar(
        select(ModelTaskOutput)
        .where(
            ModelTaskOutput.task_id == task.id, ModelTaskOutput.output_type == "text"
        )
        .order_by(ModelTaskOutput.sort_order)
    )
    if output is None or not output.text_content:
        row.status, row.error_code, row.error_message = (
            "failed",
            "ASSISTANT_INFERENCE_OUTPUT_MISSING",
            "Assistant inference returned no text",
        )
        return
    try:
        inferred = _parse_inference(output.text_content)
        data = dict(row.input_config or {})
        options = data.get("options") if isinstance(data.get("options"), dict) else {}
        project = _require_project(
            session,
            user_id=row.user_id,
            project_id=row.project_id,
            product="short_drama_narration"
            if row.mode == "short_drama_narration"
            else "video_translation",
        )
        attachment_ids = [
            item.get("asset_id")
            for item in data.get("attachments", [])
            if isinstance(item, dict) and isinstance(item.get("asset_id"), str)
        ]
        rows = _asset_rows(
            session,
            user_id=row.user_id,
            project_id=project.id,
            attachment_ids=attachment_ids,
        )
        voice_ids = {
            item
            for item in data.get("inference_voice_ids", [])
            if isinstance(item, str)
        }
        if row.mode == "short_drama_narration":
            _assert_short_drama_input(rows)
            ratio = _required_string(
                inferred,
                "video_ratio",
                {"original", "9:16", "16:9", "4:3", "3:4", "1:1"},
            )
            voice = _required_string(inferred, "voice_id", voice_ids)
            layouts = _assistant_source_subtitle_layouts(
                rows, options.get("source_subtitle_layouts")
            )
            settings = {
                "narration_style": _required_string(
                    inferred,
                    "narration_style",
                    {
                        "霸总/甜宠",
                        "逆袭/复仇",
                        "家庭伦理",
                        "古装/权谋",
                        "悬疑/犯罪",
                        "都市情感",
                        "年代/乡村",
                    },
                ),
                "video_ratio": ratio,
                "voice_id": voice,
                "subtitle_style": random.choice(SUPPORTED_SUBTITLE_STYLES),
                "requirements": _required_string(inferred, "requirements"),
                "target_duration_seconds": _normalized_target_duration_seconds(
                    inferred, rows
                ),
                "original_sound_ratio": _normalized_original_sound_ratio(inferred),
                "execution_mode": "auto",
                "source_subtitle_layouts": layouts,
                "narration_subtitle_position": _assistant_narration_subtitle_position(
                    layouts
                ),
            }
            row.workflow_id = save_settings_and_start_analysis(
                session, user_id=row.user_id, project_id=project.id, settings=settings
            )
        else:
            _assert_translation_input(
                rows,
                options.get("target_language") if isinstance(options, dict) else None,
            )
            target = str(options["target_language"])
            settings = {
                "target_language": target,
                "voice_id": _required_string(inferred, "voice_id", voice_ids),
                "video_ratio": _required_string(
                    inferred,
                    "video_ratio",
                    {"original", "9:16", "16:9", "1:1", "4:3", "3:4"},
                ),
                "preserve_source_subtitles": inferred.get("preserve_source_subtitles"),
                "execution_mode": "auto",
                "original_sound_mode": "voice_replacement",
                "subtitle_style": random.choice(SUPPORTED_SUBTITLE_STYLES),
            }
            if type(settings["preserve_source_subtitles"]) is not bool:
                raise ApiError(
                    "ASSISTANT_INFERENCE_INVALID",
                    "LLM returned an invalid preserve_source_subtitles",
                    502,
                )
            session.merge(
                VideoTranslationSettings(project_id=project.id, settings=settings)
            )
            row.workflow_id = _start_translation(
                session, user_id=row.user_id, project_id=project.id
            )
        row.resolved_config, row.status = settings, "queued"
    except (ProjectLifecycleConflict, ProjectNotFoundError) as error:
        row.status, row.error_code, row.error_message = "failed", error.code, str(error)
    except ApiError as error:
        row.status, row.error_code, row.error_message = (
            "failed",
            error.code,
            error.message,
        )


def _advance_inference_runs_for_task(session: Session, *, task_id: str) -> None:
    """在模型任务落库的同一事务内同步关联 Agent Run。

    不能把状态推进依赖到用户下一次打开助手页；否则 Provider 已失败或
    LLM 已成功时，项目和 Agent Run 都会停在过期的中间状态。
    """

    runs = list(
        session.scalars(
            select(AgentRun)
            .where(
                AgentRun.model_task_id == task_id,
                AgentRun.mode.in_(("short_drama_narration", "video_translation")),
            )
            .with_for_update()
        )
    )
    for run in runs:
        _advance_inference_run(session, run)


def _execute_video_task(
    session: Session,
    *,
    request: Request,
    user_id: str,
    options: MessageOptions,
    rows: list[Asset],
    run: AgentRun,
) -> None:
    if (
        not options.generation_mode
        or not options.model_id
        or not options.ratio
        or options.duration_seconds is None
        or not options.resolution
        or options.audio_enabled is None
    ):
        raise ApiError(
            "VIDEO_GENERATION_OPTIONS_REQUIRED",
            "Generation mode, model, ratio, duration, resolution, and audio setting are required",
            422,
        )
    model = session.scalar(
        select(Model).where(
            Model.id == options.model_id,
            Model.model_type.in_(AI_VIDEO_MODEL_TYPES),
            Model.is_enabled.is_(True),
        )
    )
    play_mode = (
        session.get(ModelPlayMode, options.play_mode_id)
        if options.play_mode_id
        else _play_mode_for_generation(session, model, options.generation_mode)
    )
    if (
        model is None
        or play_mode is None
        or play_mode.model_id != model.id
        or not play_mode.is_enabled
    ):
        raise ApiError(
            "VIDEO_GENERATION_CAPABILITY_INVALID",
            "Selected model or play mode is unavailable",
            422,
        )
    _assert_generation_mode(options.generation_mode, rows)
    ids = {
        kind: [row.id for row in rows if row.asset_type == kind]
        for kind in ("image", "video", "audio")
    }
    task = _create_model_task(
        session=session,
        user_id=user_id,
        project_id=options.project_id,
        body=TaskCreateRequest(
            project_id=options.project_id or "",
            model_id=options.model_id,
            play_mode_id=play_mode.id,
            prompt=run.input_config.get("content")
            if isinstance(run.input_config.get("content"), str)
            else None,
            image_asset_ids=ids["image"],
            video_asset_ids=ids["video"],
            audio_asset_ids=ids["audio"],
            ratio=options.ratio,
            duration_seconds=options.duration_seconds,
            resolution=options.resolution,
            audio_enabled=options.audio_enabled,
            provider_options=options.model_parameters,
            multi_subject_references=[row.id for row in rows]
            if options.generation_mode == "multi_subject_reference_audio_visual"
            else [],
        ),
        task_type="ai_video",
    )
    task.idempotency_key = run.idempotency_key
    run.model_task_id = task.id
    run.status = "queued"
    run.resolved_config = {
        **run.resolved_config,
        "generation_mode": options.generation_mode,
        "model_id": options.model_id,
        "play_mode_id": play_mode.id,
        "ratio": options.ratio,
        "duration_seconds": options.duration_seconds,
        "resolution": options.resolution,
        "audio_enabled": options.audio_enabled,
    }


def _play_mode_for_generation(
    session: Session, model: Model | None, generation_mode: str
) -> ModelPlayMode | None:
    """由用户选定的生成模式映射到模型公开玩法，不读取/推断其它参数。"""
    if model is None:
        return None
    modes = list(
        session.scalars(
            select(ModelPlayMode).where(
                ModelPlayMode.model_id == model.id, ModelPlayMode.is_enabled.is_(True)
            )
        )
    )
    aliases = {
        "text_to_video": {"text_to_video", "text2video", "t2v"},
        "first_frame": {"first_frame", "image_to_video", "i2v"},
        "first_last_frame": {"first_last_frame", "first_and_last_frame"},
        "multi_subject_reference_audio_visual": {
            "multi_subject_reference_audio_visual",
            "multimodal_reference",
            "multi_subject_reference",
        },
    }[generation_mode]
    exact = [mode for mode in modes if mode.code.lower().replace("-", "_") in aliases]
    if len(exact) == 1:
        return exact[0]
    # 老目录可能没有规范玩法 code；只接受能唯一满足参考媒体形态的玩法。
    candidates: list[ModelPlayMode] = []
    for mode in modes:
        rules = list(
            session.scalars(
                select(ModelPlayModeRule).where(
                    ModelPlayModeRule.play_mode_id == mode.id,
                    ModelPlayModeRule.rule_kind == "input_constraint",
                )
            )
        )
        image = next(
            (
                rule
                for rule in rules
                if rule.input_type == "image" and rule.is_supported
            ),
            None,
        )
        media = [
            rule
            for rule in rules
            if rule.input_type in {"image", "video", "audio"} and rule.is_supported
        ]
        if generation_mode == "text_to_video" and not media:
            candidates.append(mode)
        elif (
            generation_mode == "first_frame"
            and image is not None
            and (image.max_count or 1) == 1
        ):
            candidates.append(mode)
        elif (
            generation_mode == "first_last_frame"
            and image is not None
            and (image.max_count or 0) >= 2
        ):
            candidates.append(mode)
        elif generation_mode == "multi_subject_reference_audio_visual" and media:
            candidates.append(mode)
    return candidates[0] if len(candidates) == 1 else None


def _submit_video_task_after_commit(request: Request, task_id: str) -> None:
    registry = get_provider_registry(request)
    try:
        with Session(request.app.state.database_engine) as session:
            task = session.get(ModelTask, task_id)
            if task is None:
                return
            result = _submit_task(registry, session, task)
        with Session(request.app.state.database_engine) as session:
            with session.begin():
                task = session.get(ModelTask, task_id)
                if task is not None:
                    _stage_provider_result(session, task, result)
    except ProviderError:
        with Session(request.app.state.database_engine) as session:
            with session.begin():
                task = session.get(ModelTask, task_id)
                if task is not None:
                    _fail_task(
                        session,
                        task,
                        code="MODEL_PROVIDER_UNAVAILABLE",
                        message="Model provider submission failed",
                    )


def _submit_inference_task_after_commit(request: Request, task_id: str) -> None:
    """走既有 ModelTask/Provider LLM 链路，不在会话服务内伪造推导结果。"""
    registry = get_provider_registry(request)
    try:
        with Session(request.app.state.database_engine) as session:
            task = session.get(ModelTask, task_id)
            if task is None:
                return
            messages = _frozen_chat_context(task)
            if messages is None:
                assets = _task_assets_payload(session, task)
                content: list[dict[str, object]] = [
                    {"type": "text", "text": task.prompt or ""}
                ]
                for item in assets["image"]:
                    content.append(
                        {"type": "image_url", "image_url": {"url": item["url"]}}
                    )
                messages = [{"role": "user", "content": content}]
            result = _submit_task(registry, session, task, messages=messages)
        with Session(request.app.state.database_engine) as session:
            with session.begin():
                task = session.get(ModelTask, task_id)
                if task is not None:
                    _stage_provider_result(session, task, result)
                    if task.task_type == "llm" and task.status == "finalizing":
                        _mark_completed(session, task)
                    _advance_inference_runs_for_task(session, task_id=task.id)
    except ProviderError:
        with Session(request.app.state.database_engine) as session:
            with session.begin():
                task = session.get(ModelTask, task_id)
                if task is not None:
                    _fail_task(
                        session,
                        task,
                        code="ASSISTANT_INFERENCE_PROVIDER_UNAVAILABLE",
                        message="Assistant inference provider submission failed",
                    )
                    _advance_inference_runs_for_task(session, task_id=task.id)


def _submit_model_task_in_background(
    request: Request, *, task_id: str, inference: bool
) -> None:
    """Detach provider submission from the message-creation HTTP response."""

    submit = (
        _submit_inference_task_after_commit
        if inference
        else _submit_video_task_after_commit
    )
    threading.Thread(
        target=lambda: submit(request, task_id),
        name=f"assistant-submit-{task_id}",
        daemon=True,
    ).start()


def _sse(event: str, payload: dict[str, object]) -> bytes:
    """Encode one application SSE event without exposing internal task details."""

    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False, separators=(',', ':'))}\n\n".encode(
        "utf-8"
    )


def _start_chat_stream_after_commit(
    request: Request, *, task_id: str, assistant_message_id: str
) -> None:
    """Run provider streaming outside an HTTP subscriber's lifecycle.

    Message text and ModelTask state are persisted by ``_stream_chat_task``.
    A process restart is still recoverable by the standard ModelTask poller once
    the lease expires, so the browser is never the owner of task completion.
    """

    def run() -> None:
        for _event in _stream_chat_task(
            request, task_id=task_id, assistant_message_id=assistant_message_id
        ):
            pass

    threading.Thread(
        target=run,
        name=f"assistant-chat-{assistant_message_id}",
        daemon=True,
    ).start()


def _watch_chat_stream(
    request: Request,
    *,
    task_id: str,
    assistant_message_id: str,
) -> Iterator[bytes]:
    """Replay persisted chat content and follow new deltas for one SSE client."""

    engine = request.app.state.database_engine
    last_content: str | None = None
    while True:
        with Session(engine) as session:
            message = session.get(ConversationMessage, assistant_message_id)
            task = session.get(ModelTask, task_id)
            if message is None or task is None:
                yield _sse(
                    "error",
                    {
                        "assistant_message_id": assistant_message_id,
                        "message": "对话回复生成失败，请重试。",
                    },
                )
                return
            content = message.content
            state = (
                "completed"
                if task.status in {"succeeded", "succeeded_with_partial_output"}
                else "failed"
                if task.status == "failed"
                else "running"
            )
        if content != last_content and content != "正在生成回复…":
            yield _sse(
                "delta",
                {"assistant_message_id": assistant_message_id, "content": content},
            )
            last_content = content
        if state == "completed":
            yield _sse(
                "completed",
                {"assistant_message_id": assistant_message_id, "content": content},
            )
            return
        if state == "failed":
            yield _sse(
                "error",
                {
                    "assistant_message_id": assistant_message_id,
                    "message": "对话回复生成失败，请重试。",
                },
            )
            return
        # Keep proxies from timing out while the provider is preparing its first
        # token. A comment frame is intentionally ignored by SSE clients.
        yield b": keep-alive\n\n"
        time.sleep(_CHAT_STREAM_POLL_SECONDS)


def _stream_chat_task(
    request: Request, *, task_id: str, assistant_message_id: str
) -> Iterator[bytes]:
    """Forward a 多元 X chat stream and persist every visible delta."""

    engine = request.app.state.database_engine
    registry = get_provider_registry(request)
    output_parts: list[str] = []
    input_token: int | None = None
    output_token: int | None = None
    last_raw: dict[str, object] | None = None

    def reserve(task: ModelTask) -> None:
        """阻止通用模型 Worker 在浏览器流仍由当前请求负责时重复提交。"""

        task.status = "processing"
        task.poll_lease_token = f"assistant-stream:{assistant_message_id}"
        task.poll_lease_until = utc_now() + timedelta(
            seconds=_CHAT_STREAM_LEASE_SECONDS
        )

    def fail() -> None:
        with Session(engine) as session:
            with session.begin():
                task = session.get(ModelTask, task_id)
                message = session.get(ConversationMessage, assistant_message_id)
                if task is not None and task.status not in {"succeeded", "failed"}:
                    _stage_provider_result(
                        session,
                        task,
                        ProviderResult(
                            status="failed",
                            provider_task_id=None,
                            error_code="ASSISTANT_INFERENCE_PROVIDER_UNAVAILABLE",
                            error_message="Assistant inference provider stream failed",
                        ),
                    )
                if message is not None:
                    message.content = "对话回复生成失败，请重试。"

    try:
        with Session(engine) as session:
            task = session.get(ModelTask, task_id)
            if task is None:
                raise ProviderError("assistant stream task is unavailable")
            model = session.get(Model, task.model_id)
            provider = session.get(ModelPlayModeProvider, task.provider_id)
            if model is None or provider is None:
                raise ProviderError("model provider configuration is unavailable")
            stream_chat = getattr(
                registry.get(provider.provider_code), "stream_chat", None
            )
            if not callable(stream_chat):
                raise ProviderError("provider does not support chat streaming")
            messages = _frozen_chat_context(task)
            if messages is None:
                assets = _task_assets_payload(session, task)
                content: list[dict[str, object]] = [
                    {"type": "text", "text": task.prompt or ""}
                ]
                for item in assets["image"]:
                    content.append(
                        {"type": "image_url", "image_url": {"url": item["url"]}}
                    )
                messages = [{"role": "user", "content": content}]
            upstream = stream_chat(
                model=model,
                provider=provider,
                task_id=task.id,
                prompt=task.prompt,
                messages=messages,
            )

        with Session(engine) as session:
            with session.begin():
                task = session.get(ModelTask, task_id)
                if task is None:
                    raise ProviderError("assistant stream task is unavailable")
                reserve(task)

        yield _sse("message_start", {"assistant_message_id": assistant_message_id})
        for chunk in upstream:
            if chunk.input_token is not None:
                input_token = chunk.input_token
            if chunk.output_token is not None:
                output_token = chunk.output_token
            if chunk.raw is not None:
                last_raw = chunk.raw
            if not chunk.text:
                continue
            output_parts.append(chunk.text)
            content = "".join(output_parts)
            with Session(engine) as session:
                with session.begin():
                    message = session.get(ConversationMessage, assistant_message_id)
                    if message is None:
                        raise ProviderError("assistant stream message is unavailable")
                    message.content = content
                    task = session.get(ModelTask, task_id)
                    if task is not None:
                        reserve(task)
            yield _sse(
                "delta",
                {
                    "assistant_message_id": assistant_message_id,
                    "content": content,
                    "delta": chunk.text,
                },
            )

        content = "".join(output_parts)
        if not content:
            raise ProviderError("provider stream returned no LLM content")
        with Session(engine) as session:
            with session.begin():
                task = session.get(ModelTask, task_id)
                message = session.get(ConversationMessage, assistant_message_id)
                if task is None or message is None:
                    raise ProviderError("assistant stream result is unavailable")
                _stage_provider_result(
                    session,
                    task,
                    ProviderResult(
                        status="succeeded",
                        provider_task_id=None,
                        outputs=(ProviderOutput(output_type="text", text=content),),
                        input_token=input_token,
                        output_token=output_token,
                        raw=last_raw,
                    ),
                )
                # 流式内容是本次聊天回合的权威结果。即使旧版本 Worker 曾在
                # lease 生效前抢先写入同一 sort_order，也必须以当前流覆盖。
                output = session.scalar(
                    select(ModelTaskOutput).where(
                        ModelTaskOutput.task_id == task.id,
                        ModelTaskOutput.sort_order == 0,
                    )
                )
                if output is not None:
                    output.output_type = "text"
                    output.provider_url = None
                    output.text_content = content
                    output.content_type = "text/plain; charset=utf-8"
                    output.duration_seconds = None
                _mark_completed(session, task)
                message.content = content
                _refresh_chat_memory(
                    session, thread_id=message.thread_id, user_id=message.user_id
                )
        yield _sse(
            "completed",
            {"assistant_message_id": assistant_message_id, "content": content},
        )
    except GeneratorExit:
        # A browser disconnect only closes an SSE subscriber.  The model task is
        # durable and may still be completed by its dedicated background runner
        # (or recovered by the existing polling worker after its lease expires).
        raise
    except ProviderError:
        fail()
        yield _sse(
            "error",
            {
                "assistant_message_id": assistant_message_id,
                "message": "对话回复生成失败，请重试。",
            },
        )
    except Exception:
        fail()
        yield _sse(
            "error",
            {
                "assistant_message_id": assistant_message_id,
                "message": "对话回复生成失败，请重试。",
            },
        )


@router.get("/assistant/threads", response_model=ApiResponse[list[ThreadData]])
def list_threads(
    request: Request,
    token: Annotated[str, Depends(bearer_token)],
    auth: Annotated[AuthService, Depends(get_auth_service)],
    request_id: Annotated[str, Depends(get_request_id)],
):
    user = auth.resolve_user(token)
    with Session(request.app.state.database_engine) as session:
        with session.begin():
            rows = list(
                session.scalars(
                    select(ConversationThread)
                    .where(ConversationThread.user_id == user.id)
                    .order_by(ConversationThread.updated_at.desc())
                )
            )
            for row in rows:
                if row.title and row.title.strip() != "新的 AI 对话":
                    continue
                first_message = session.scalar(
                    select(ConversationMessage.content)
                    .where(
                        ConversationMessage.thread_id == row.id,
                        ConversationMessage.role == "user",
                    )
                    .order_by(ConversationMessage.created_at)
                    .limit(1)
                )
                if isinstance(first_message, str):
                    _set_initial_thread_title(row, first_message)
            data = [
                ThreadData(
                    id=row.id,
                    mode=row.mode,
                    title=row.title,
                    created_at=row.created_at.isoformat(),
                    updated_at=row.updated_at.isoformat(),
                )
                for row in rows
            ]
    return ApiResponse(
        code="ASSISTANT_THREADS_LISTED",
        message="Assistant threads listed",
        data=data,
        request_id=request_id,
    )


@router.get("/assistant/chat-models", response_model=ApiResponse[list[ChatModelData]])
def list_chat_models(
    request: Request,
    token: Annotated[str, Depends(bearer_token)],
    auth: Annotated[AuthService, Depends(get_auth_service)],
    request_id: Annotated[str, Depends(get_request_id)],
):
    """Expose only LLM models that can create a fully priced chat task."""

    auth.resolve_user(token)
    registry = get_provider_registry(request)
    with Session(request.app.state.database_engine) as session:
        models = list(
            session.scalars(
                select(Model)
                .where(Model.model_type == "llm", Model.is_enabled.is_(True))
                .order_by(Model.is_default.desc(), Model.sort_order.desc(), Model.id)
            )
        )
        items: list[ChatModelData] = []
        for model in models:
            modes = list(
                session.scalars(
                    select(ModelPlayMode)
                    .where(
                        ModelPlayMode.model_id == model.id,
                        ModelPlayMode.is_enabled.is_(True),
                    )
                    .order_by(
                        ModelPlayMode.is_default.desc(),
                        ModelPlayMode.sort_order.desc(),
                        ModelPlayMode.id,
                    )
                )
            )
            for mode in modes:
                provider = (
                    session.get(ModelPlayModeProvider, mode.active_provider_id)
                    if mode.active_provider_id
                    else None
                )
                if provider is None or not provider.is_enabled:
                    continue
                try:
                    adapter = registry.get(provider.provider_code)
                except ProviderError:
                    continue
                if not callable(getattr(adapter, "stream_chat", None)):
                    continue
                has_price = session.scalar(
                    select(ModelPlayModeProviderPrice.id)
                    .where(
                        ModelPlayModeProviderPrice.provider_id == provider.id,
                        ModelPlayModeProviderPrice.resolution.is_(None),
                        ModelPlayModeProviderPrice.is_enabled.is_(True),
                    )
                    .limit(1)
                )
                if has_price is not None:
                    items.append(
                        ChatModelData(
                            id=model.id,
                            display_name=model.display_name,
                            provider_code=provider.provider_code,
                        )
                    )
                    break
    return ApiResponse(
        code="ASSISTANT_CHAT_MODELS_LISTED",
        message="Assistant chat models listed",
        data=items,
        request_id=request_id,
    )


@router.post(
    "/assistant/threads",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiResponse[ThreadData],
)
def create_thread(
    body: ThreadCreateRequest,
    request: Request,
    token: Annotated[str, Depends(bearer_token)],
    auth: Annotated[AuthService, Depends(get_auth_service)],
    request_id: Annotated[str, Depends(get_request_id)],
):
    user = auth.resolve_user(token)
    with Session(request.app.state.database_engine) as session:
        with session.begin():
            row = ConversationThread(
                id=_id("ath"),
                user_id=user.id,
                mode=body.mode,
                title=body.title.strip() if body.title else None,
            )
            session.add(row)
            session.flush()
            data = ThreadData(
                id=row.id,
                mode=row.mode,
                title=row.title,
                created_at=row.created_at.isoformat(),
                updated_at=row.updated_at.isoformat(),
            )
    return ApiResponse(
        code="ASSISTANT_THREAD_CREATED",
        message="Assistant thread created",
        data=data,
        request_id=request_id,
    )


@router.patch("/assistant/threads/{thread_id}", response_model=ApiResponse[ThreadData])
def update_thread_title(
    thread_id: str,
    body: ThreadTitleUpdateRequest,
    request: Request,
    token: Annotated[str, Depends(bearer_token)],
    auth: Annotated[AuthService, Depends(get_auth_service)],
    request_id: Annotated[str, Depends(get_request_id)],
):
    title = body.title.strip()
    if not title:
        raise ApiError(
            "ASSISTANT_THREAD_TITLE_INVALID", "Conversation title is required", 422
        )
    user = auth.resolve_user(token)
    with Session(request.app.state.database_engine) as session:
        with session.begin():
            row = _thread(session, user_id=user.id, thread_id=thread_id, lock=True)
            row.title = title
            session.flush()
            data = ThreadData(
                id=row.id,
                mode=row.mode,
                title=row.title,
                created_at=row.created_at.isoformat(),
                updated_at=row.updated_at.isoformat(),
            )
    return ApiResponse(
        code="ASSISTANT_THREAD_UPDATED",
        message="Assistant thread updated",
        data=data,
        request_id=request_id,
    )


@router.delete(
    "/assistant/threads/{thread_id}", response_model=ApiResponse[ThreadDeleteData]
)
def delete_thread(
    thread_id: str,
    request: Request,
    token: Annotated[str, Depends(bearer_token)],
    auth: Annotated[AuthService, Depends(get_auth_service)],
    request_id: Annotated[str, Depends(get_request_id)],
):
    """删除会话展示记录，不删除已经独立创建的项目、工作流或模型计费任务。"""

    user = auth.resolve_user(token)
    with Session(request.app.state.database_engine) as session:
        with session.begin():
            _thread(session, user_id=user.id, thread_id=thread_id, lock=True)
            session.execute(
                delete(AgentRun).where(
                    AgentRun.thread_id == thread_id, AgentRun.user_id == user.id
                )
            )
            session.execute(
                delete(ConversationMessage).where(
                    ConversationMessage.thread_id == thread_id,
                    ConversationMessage.user_id == user.id,
                )
            )
            session.execute(
                delete(ConversationThread).where(
                    ConversationThread.id == thread_id,
                    ConversationThread.user_id == user.id,
                )
            )
            data = ThreadDeleteData(id=thread_id)
    return ApiResponse(
        code="ASSISTANT_THREAD_DELETED",
        message="Assistant thread deleted",
        data=data,
        request_id=request_id,
    )


@router.post(
    "/assistant/threads/{thread_id}/drafts",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiResponse[DraftData],
)
def create_draft(
    thread_id: str,
    body: DraftCreateRequest,
    request: Request,
    token: Annotated[str, Depends(bearer_token)],
    auth: Annotated[AuthService, Depends(get_auth_service)],
    request_id: Annotated[str, Depends(get_request_id)],
):
    user = auth.resolve_user(token)
    with Session(request.app.state.database_engine) as session:
        with session.begin():
            _thread(session, user_id=user.id, thread_id=thread_id)
            if body.mode == "short_drama_narration":
                project = create_project(
                    session, user_id=user.id, product="short-drama-narration"
                )
            elif body.mode == "video_translation":
                project = create_project(
                    session, user_id=user.id, product="video-translation"
                )
            else:
                project = Project(
                    id=_id("prj"),
                    user_id=user.id,
                    product="ai_video",
                    status="draft",
                    current_stage="created",
                )
                session.add(project)
            data = DraftData(project_id=project.id, mode=body.mode)
    return ApiResponse(
        code="ASSISTANT_DRAFT_CREATED",
        message="Assistant upload draft created",
        data=data,
        request_id=request_id,
    )


@router.get(
    "/assistant/threads/{thread_id}", response_model=ApiResponse[ThreadDetailData]
)
def get_thread(
    thread_id: str,
    request: Request,
    token: Annotated[str, Depends(bearer_token)],
    auth: Annotated[AuthService, Depends(get_auth_service)],
    request_id: Annotated[str, Depends(get_request_id)],
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
    before: Annotated[str | None, Query(max_length=64)] = None,
):
    """Return the newest message page, or the page immediately before a cursor."""

    user = auth.resolve_user(token)
    with Session(request.app.state.database_engine) as session:
        with session.begin():
            row = _thread(session, user_id=user.id, thread_id=thread_id)
            statement = select(ConversationMessage).where(
                ConversationMessage.thread_id == row.id,
                ConversationMessage.user_id == user.id,
            )
            if before:
                cursor = session.scalar(
                    select(ConversationMessage).where(
                        ConversationMessage.id == before,
                        ConversationMessage.thread_id == row.id,
                        ConversationMessage.user_id == user.id,
                    )
                )
                if cursor is None:
                    raise ApiError(
                        "ASSISTANT_MESSAGE_CURSOR_INVALID",
                        "Conversation message cursor is invalid",
                        422,
                    )
                statement = statement.where(
                    or_(
                        ConversationMessage.created_at < cursor.created_at,
                        and_(
                            ConversationMessage.created_at == cursor.created_at,
                            ConversationMessage.id < cursor.id,
                        ),
                    )
                )
            newest_first = list(
                session.scalars(
                    statement.order_by(
                        ConversationMessage.created_at.desc(),
                        ConversationMessage.id.desc(),
                    ).limit(limit + 1)
                )
            )
            has_more = len(newest_first) > limit
            messages = list(reversed(newest_first[:limit]))
            for message in messages:
                if message.role == "assistant" and message.mode == "chat":
                    _advance_chat_message(session, message)
            data = ThreadDetailData(
                id=row.id,
                mode=row.mode,
                title=row.title,
                created_at=row.created_at.isoformat(),
                updated_at=row.updated_at.isoformat(),
                messages=[_message_data(session, message) for message in messages],
                has_more=has_more,
                next_before=messages[0].id if has_more and messages else None,
            )
    return ApiResponse(
        code="ASSISTANT_THREAD_RETRIEVED",
        message="Assistant thread retrieved",
        data=data,
        request_id=request_id,
    )


@router.post("/assistant/threads/{thread_id}/messages/stream")
def stream_chat_message(
    thread_id: str,
    body: MessageCreateRequest,
    request: Request,
    token: Annotated[str, Depends(bearer_token)],
    auth: Annotated[AuthService, Depends(get_auth_service)],
    idempotency_key: Annotated[str | None, Header(alias="X-Idempotency-Key")] = None,
) -> StreamingResponse:
    """Create one normal-chat turn and relay its provider SSE response.

    This endpoint is intentionally chat-only. Agent parameter inference remains
    non-streaming because it must validate one complete JSON object before a
    product workflow may start.
    """

    if body.mode != "chat":
        raise ApiError(
            "ASSISTANT_STREAM_MODE_UNSUPPORTED",
            "Only normal chat supports streaming",
            422,
        )
    key = idempotency_key or f"assistant-stream:{time.time_ns()}"
    if len(key) > 256:
        raise ApiError("IDEMPOTENCY_KEY_INVALID", "Idempotency key is invalid", 422)
    user = auth.resolve_user(token)
    with Session(request.app.state.database_engine) as session:
        with session.begin():
            thread = _thread(session, user_id=user.id, thread_id=thread_id, lock=True)
            existing = session.scalar(
                select(ConversationMessage).where(
                    ConversationMessage.thread_id == thread.id,
                    ConversationMessage.idempotency_key == key,
                )
            )
            if existing is not None:
                raise ApiError(
                    "ASSISTANT_STREAM_IDEMPOTENCY_CONFLICT",
                    "This streamed message has already been submitted",
                    409,
                )
            attachments = [{"asset_id": item.asset_id} for item in body.attachments]
            chat_images: list[str] = []
            if body.attachments:
                project = _require_project(
                    session,
                    user_id=user.id,
                    project_id=body.options.project_id,
                    product="ai_video",
                )
                chat_assets = _asset_rows(
                    session,
                    user_id=user.id,
                    project_id=project.id,
                    attachment_ids=[item.asset_id for item in body.attachments],
                )
                if any(asset.asset_type != "image" for asset in chat_assets):
                    raise ApiError(
                        "CHAT_ATTACHMENT_UNSUPPORTED",
                        "Normal chat currently supports ready image attachments only",
                        422,
                    )
                chat_images = [asset.id for asset in chat_assets]
            message = ConversationMessage(
                id=_id("ams"),
                thread_id=thread.id,
                user_id=user.id,
                role="user",
                mode="chat",
                content=body.content.strip(),
                attachments=attachments,
                idempotency_key=key,
            )
            session.add(message)
            session.flush()
            _set_initial_thread_title(thread, message.content)
            task_id = _start_llm_task(
                session,
                user_id=user.id,
                idempotency_key=f"chat:{key}",
                prompt=_chat_task_prompt(
                    body.content, locale=body.options.response_locale
                ),
                project_id=body.options.project_id if chat_images else None,
                image_asset_ids=chat_images,
                model_id=body.options.model_id,
                locale=body.options.response_locale,
            )
            assistant = ConversationMessage(
                id=_id("ams"),
                thread_id=thread.id,
                user_id=user.id,
                role="assistant",
                mode="chat",
                content="正在生成回复…",
                attachments=[],
                idempotency_key=f"chat_llm:{task_id}",
            )
            session.add(assistant)
            session.flush()
            stream_task = session.get(ModelTask, task_id)
            if stream_task is None:
                raise ApiError(
                    "ASSISTANT_STREAM_TASK_MISSING",
                    "Assistant stream task is unavailable",
                    500,
                )
            stream_task.poll_lease_token = f"assistant-stream:{assistant.id}"
            stream_task.poll_lease_until = utc_now() + timedelta(
                seconds=_CHAT_STREAM_LEASE_SECONDS
            )
            _freeze_chat_context(
                session,
                task=stream_task,
                thread_id=thread.id,
                assistant_message_id=assistant.id,
            )
            start_payload = {
                "message": _message_data(session, message).model_dump(),
                "assistant_message": _message_data(session, assistant).model_dump(),
                "thread_title": thread.title,
            }
            assistant_message_id = assistant.id

    _start_chat_stream_after_commit(
        request, task_id=task_id, assistant_message_id=assistant_message_id
    )

    def event_stream() -> Iterator[bytes]:
        yield _sse("message_created", start_payload)
        yield from _watch_chat_stream(
            request, task_id=task_id, assistant_message_id=assistant_message_id
        )

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/assistant/threads/{thread_id}/messages/{assistant_message_id}/stream")
def resume_chat_stream(
    thread_id: str,
    assistant_message_id: str,
    request: Request,
    token: Annotated[str, Depends(bearer_token)],
    auth: Annotated[AuthService, Depends(get_auth_service)],
) -> StreamingResponse:
    """Resume observing a persisted chat reply without starting another task."""

    user = auth.resolve_user(token)
    with Session(request.app.state.database_engine) as session:
        thread = _thread(session, user_id=user.id, thread_id=thread_id)
        assistant = session.get(ConversationMessage, assistant_message_id)
        if (
            assistant is None
            or assistant.thread_id != thread.id
            or assistant.user_id != user.id
            or assistant.role != "assistant"
            or assistant.mode != "chat"
        ):
            raise ApiError(
                "ASSISTANT_STREAM_MESSAGE_MISSING",
                "Assistant stream message is unavailable",
                404,
            )
        task_id = _chat_task_id(assistant)
        if not task_id or session.get(ModelTask, task_id) is None:
            raise ApiError(
                "ASSISTANT_STREAM_TASK_MISSING",
                "Assistant stream task is unavailable",
                404,
            )
        initial = _message_data(session, assistant).model_dump()

    def event_stream() -> Iterator[bytes]:
        yield _sse("message_created", {"assistant_message": initial})
        yield from _watch_chat_stream(
            request, task_id=task_id, assistant_message_id=assistant_message_id
        )

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post(
    "/assistant/threads/{thread_id}/messages/{assistant_message_id}/retry/stream"
)
def retry_chat_message(
    thread_id: str,
    assistant_message_id: str,
    request: Request,
    token: Annotated[str, Depends(bearer_token)],
    auth: Annotated[AuthService, Depends(get_auth_service)],
    idempotency_key: Annotated[str | None, Header(alias="X-Idempotency-Key")] = None,
) -> StreamingResponse:
    """基于原任务输入重新生成一条按当前时间追加的 assistant 回复。"""

    key = idempotency_key or f"assistant-retry:{time.time_ns()}"
    if len(key) > 256:
        raise ApiError("IDEMPOTENCY_KEY_INVALID", "Idempotency key is invalid", 422)
    user = auth.resolve_user(token)
    with Session(request.app.state.database_engine) as session:
        with session.begin():
            thread = _thread(session, user_id=user.id, thread_id=thread_id, lock=True)
            assistant, task_id = _prepare_chat_retry(
                session,
                thread=thread,
                user_id=user.id,
                assistant_message_id=assistant_message_id,
                idempotency_key=key,
            )
            start_payload = {
                "assistant_message": _message_data(session, assistant).model_dump(),
                "thread_title": thread.title,
            }
            retry_assistant_message_id = assistant.id

    _start_chat_stream_after_commit(
        request, task_id=task_id, assistant_message_id=retry_assistant_message_id
    )

    def event_stream() -> Iterator[bytes]:
        yield _sse("message_created", start_payload)
        yield from _watch_chat_stream(
            request,
            task_id=task_id,
            assistant_message_id=retry_assistant_message_id,
        )

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post(
    "/assistant/threads/{thread_id}/messages",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=ApiResponse[MessageSubmitData],
)
def submit_message(
    thread_id: str,
    body: MessageCreateRequest,
    request: Request,
    token: Annotated[str, Depends(bearer_token)],
    auth: Annotated[AuthService, Depends(get_auth_service)],
    settings: Annotated[Settings, Depends(get_settings)],
    request_id: Annotated[str, Depends(get_request_id)],
    idempotency_key: Annotated[str | None, Header(alias="X-Idempotency-Key")] = None,
):
    user = auth.resolve_user(token)
    key = idempotency_key or f"assistant:{request_id}"
    if len(key) > 256:
        raise ApiError("IDEMPOTENCY_KEY_INVALID", "Idempotency key is invalid", 422)
    task_id: str | None = None
    chat_task_id: str | None = None
    with Session(request.app.state.database_engine) as session:
        with session.begin():
            thread = _thread(session, user_id=user.id, thread_id=thread_id, lock=True)
            existing = session.scalar(
                select(ConversationMessage).where(
                    ConversationMessage.thread_id == thread_id,
                    ConversationMessage.idempotency_key == key,
                )
            )
            if existing is not None:
                assistant = session.scalar(
                    select(ConversationMessage)
                    .where(
                        ConversationMessage.thread_id == thread_id,
                        ConversationMessage.role == "assistant",
                        ConversationMessage.created_at >= existing.created_at,
                    )
                    .order_by(ConversationMessage.created_at)
                    .limit(1)
                )
                run = session.scalar(
                    select(AgentRun).where(AgentRun.message_id == existing.id)
                )
                return ApiResponse(
                    code="ASSISTANT_MESSAGE_RETRIEVED",
                    message="Assistant message retrieved",
                    data=MessageSubmitData(
                        message=_message_data(session, existing),
                        assistant_message=_message_data(session, assistant)
                        if assistant
                        else _message_data(session, existing),
                        run=_run_data(session, run, settings=settings) if run else None,
                        thread_title=thread.title,
                    ),
                    request_id=request_id,
                )
            attachments = [{"asset_id": item.asset_id} for item in body.attachments]
            message = ConversationMessage(
                id=_id("ams"),
                thread_id=thread.id,
                user_id=user.id,
                role="user",
                mode=body.mode,
                content=body.content.strip(),
                attachments=attachments,
                idempotency_key=key,
            )
            session.add(message)
            session.flush()
            _set_initial_thread_title(thread, message.content)
            if body.mode == "chat":
                chat_images: list[str] = []
                if body.attachments:
                    project = _require_project(
                        session,
                        user_id=user.id,
                        project_id=body.options.project_id,
                        product="ai_video",
                    )
                    chat_assets = _asset_rows(
                        session,
                        user_id=user.id,
                        project_id=project.id,
                        attachment_ids=[item.asset_id for item in body.attachments],
                    )
                    if any(asset.asset_type != "image" for asset in chat_assets):
                        raise ApiError(
                            "CHAT_ATTACHMENT_UNSUPPORTED",
                            "Normal chat currently supports ready image attachments only",
                            422,
                        )
                    chat_images = [asset.id for asset in chat_assets]
                chat_task_id = _start_llm_task(
                    session,
                    user_id=user.id,
                    idempotency_key=f"chat:{key}",
                    prompt=_chat_task_prompt(
                        body.content, locale=body.options.response_locale
                    ),
                    project_id=body.options.project_id if chat_images else None,
                    image_asset_ids=chat_images,
                    model_id=body.options.model_id,
                    locale=body.options.response_locale,
                )
                assistant = ConversationMessage(
                    id=_id("ams"),
                    thread_id=thread.id,
                    user_id=user.id,
                    role="assistant",
                    mode="chat",
                    content="正在生成回复…",
                    attachments=[],
                    idempotency_key=f"chat_llm:{chat_task_id}",
                )
                session.add(assistant)
                session.flush()
                chat_task = session.get(ModelTask, chat_task_id)
                if chat_task is not None:
                    _freeze_chat_context(
                        session,
                        task=chat_task,
                        thread_id=thread.id,
                        assistant_message_id=assistant.id,
                    )
                data = MessageSubmitData(
                    message=_message_data(session, message),
                    assistant_message=_message_data(session, assistant),
                    run=None,
                    thread_title=thread.title,
                )
            else:
                options = body.options
                product = {
                    "short_drama_narration": "short_drama_narration",
                    "video_translation": "video_translation",
                    "video_generation": "ai_video",
                }[body.mode]
                project = _require_project(
                    session,
                    user_id=user.id,
                    project_id=options.project_id,
                    product=product,
                )
                _assert_agent_task_draft(project)
                rows = _asset_rows(
                    session,
                    user_id=user.id,
                    project_id=project.id,
                    attachment_ids=[item.asset_id for item in body.attachments],
                )
                run = AgentRun(
                    id=_id("arun"),
                    thread_id=thread.id,
                    message_id=message.id,
                    user_id=user.id,
                    mode=body.mode,
                    status="pending",
                    idempotency_key=key,
                    input_config={
                        "content": body.content.strip(),
                        "attachments": attachments,
                        "options": body.options.model_dump(exclude_none=True),
                        "response_locale": body.options.response_locale,
                    },
                    resolved_config={},
                    project_id=project.id,
                )
                session.add(run)
                if body.mode == "short_drama_narration":
                    _assert_short_drama_input(rows)
                    voice_ids = _inference_voice_ids(settings)
                    run.input_config = {
                        **run.input_config,
                        "inference_voice_ids": voice_ids,
                    }
                    task_id = _start_inference_task(
                        session,
                        user_id=user.id,
                        run=run,
                        prompt=_inference_prompt(
                            mode=body.mode,
                            content=body.content,
                            target_language=None,
                            voice_ids=voice_ids,
                            locale=body.options.response_locale,
                        ),
                    )
                    reply = (
                        "短剧解说参数推导任务已提交；结构化推导完成后将自动创建工作流。"
                    )
                elif body.mode == "video_translation":
                    _assert_translation_input(rows, options.target_language)
                    voice_ids = _inference_voice_ids(
                        settings, target_language=options.target_language
                    )
                    run.input_config = {
                        **run.input_config,
                        "inference_voice_ids": voice_ids,
                    }
                    task_id = _start_inference_task(
                        session,
                        user_id=user.id,
                        run=run,
                        prompt=_inference_prompt(
                            mode=body.mode,
                            content=body.content,
                            target_language=options.target_language,
                            voice_ids=voice_ids,
                            locale=body.options.response_locale,
                        ),
                    )
                    reply = "视频翻译参数推导任务已提交；目标语言已固定，完成后将创建翻译工作流。"
                else:
                    _execute_video_task(
                        session,
                        request=request,
                        user_id=user.id,
                        options=options,
                        rows=rows,
                        run=run,
                    )
                    task_id = run.model_task_id
                    reply = "视频生成任务已提交，所有生成参数均使用你的固定选择。"
                assistant = ConversationMessage(
                    id=_id("ams"),
                    thread_id=thread.id,
                    user_id=user.id,
                    role="assistant",
                    mode=body.mode,
                    content=reply,
                    attachments=[],
                )
                session.add(assistant)
                session.flush()
                run.input_config = {
                    **run.input_config,
                    "assistant_message_id": assistant.id,
                }
                data = MessageSubmitData(
                    message=_message_data(session, message),
                    assistant_message=_message_data(session, assistant),
                    run=_run_data(session, run, settings=settings),
                    thread_title=thread.title,
                )
    # 供应商调用严格在事务提交后执行，避免事务重试重复发起远端任务。
    if task_id and body.mode == "video_generation":
        _submit_model_task_in_background(request, task_id=task_id, inference=False)
    if task_id and body.mode in {"short_drama_narration", "video_translation"}:
        _submit_model_task_in_background(request, task_id=task_id, inference=True)
    if chat_task_id:
        _submit_model_task_in_background(request, task_id=chat_task_id, inference=True)
    return ApiResponse(
        code="ASSISTANT_MESSAGE_ACCEPTED",
        message="Assistant message accepted",
        data=data,
        request_id=request_id,
    )


@router.get(
    "/assistant/threads/{thread_id}/runs", response_model=ApiResponse[list[RunData]]
)
def list_runs(
    thread_id: str,
    request: Request,
    token: Annotated[str, Depends(bearer_token)],
    auth: Annotated[AuthService, Depends(get_auth_service)],
    settings: Annotated[Settings, Depends(get_settings)],
    request_id: Annotated[str, Depends(get_request_id)],
):
    user = auth.resolve_user(token)
    with Session(request.app.state.database_engine) as session:
        with session.begin():
            _thread(session, user_id=user.id, thread_id=thread_id)
            rows = list(
                session.scalars(
                    select(AgentRun)
                    .where(AgentRun.thread_id == thread_id, AgentRun.user_id == user.id)
                    .order_by(AgentRun.created_at.desc())
                )
            )
            for row in rows:
                _advance_inference_run(session, row)
            data = [_run_data(session, row, settings=settings) for row in rows]
    return ApiResponse(
        code="ASSISTANT_RUNS_LISTED",
        message="Assistant runs listed",
        data=data,
        request_id=request_id,
    )


@router.get("/assistant/runs/{run_id}", response_model=ApiResponse[RunData])
def get_run(
    run_id: str,
    request: Request,
    token: Annotated[str, Depends(bearer_token)],
    auth: Annotated[AuthService, Depends(get_auth_service)],
    settings: Annotated[Settings, Depends(get_settings)],
    request_id: Annotated[str, Depends(get_request_id)],
):
    user = auth.resolve_user(token)
    with Session(request.app.state.database_engine) as session:
        with session.begin():
            row = session.scalar(
                select(AgentRun)
                .where(AgentRun.id == run_id, AgentRun.user_id == user.id)
                .with_for_update()
            )
            if row is None:
                raise ApiError(
                    "ASSISTANT_RUN_NOT_FOUND", "Assistant run not found", 404
                )
            _advance_inference_run(session, row)
            data = _run_data(session, row, settings=settings)
    return ApiResponse(
        code="ASSISTANT_RUN_RETRIEVED",
        message="Assistant run retrieved",
        data=data,
        request_id=request_id,
    )


@router.get("/assistant/runs/{run_id}/stream")
def stream_agent_run(
    run_id: str,
    request: Request,
    token: Annotated[str, Depends(bearer_token)],
    auth: Annotated[AuthService, Depends(get_auth_service)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> StreamingResponse:
    """Follow one durable Agent Run without making the browser own execution."""

    user = auth.resolve_user(token)
    with Session(request.app.state.database_engine) as session:
        row = session.scalar(
            select(AgentRun).where(AgentRun.id == run_id, AgentRun.user_id == user.id)
        )
        if row is None:
            raise ApiError("ASSISTANT_RUN_NOT_FOUND", "Assistant run not found", 404)

    def event_stream() -> Iterator[bytes]:
        core_client = HttpCoreClient(
            str(settings.core_base_url), settings.core_request_token
        )
        last_stream_event_id = ""
        last_run_signature = ""
        last_snapshot_at = 0.0
        while True:
            with Session(request.app.state.database_engine) as session:
                with session.begin():
                    row = session.scalar(
                        select(AgentRun).where(
                            AgentRun.id == run_id, AgentRun.user_id == user.id
                        )
                    )
                    if row is None:
                        yield _sse("error", {"message": "Agent Run 不存在。"})
                        return
                    _advance_inference_run(session, row)
                    active_core = _active_run_core_attempt(session, row)
                    now = time.monotonic()
                    should_snapshot = not last_run_signature or now - last_snapshot_at >= 2
                    run_payload = (
                        _run_data(session, row, settings=settings).model_dump()
                        if should_snapshot
                        else None
                    )
                    inference_running = (
                        row.workflow_id is None
                        and row.status not in {"failed", "completed", "succeeded", "cancelled"}
                    )

            if run_payload is not None:
                signature = json.dumps(
                    run_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
                )
                if signature != last_run_signature:
                    yield _sse("run_snapshot", {"run": run_payload})
                    last_run_signature = signature
                last_snapshot_at = time.monotonic()
                status_value = str(run_payload.get("status") or "").lower()
                if status_value in {"completed", "succeeded", "failed", "cancelled"}:
                    yield _sse("completed", {"run": run_payload})
                    return

            if inference_running and last_stream_event_id != "inference:1":
                yield _sse(
                    "step_snapshot",
                    {
                        "run_id": run_id,
                        "event_id": "inference:1",
                        "sequence": 1,
                        "step_id": "requirements_inference",
                        "phase": "parameter_inference",
                        "status_label": "正在理解需求并校验执行参数…",
                        "content": "",
                        "draft": True,
                        "completed": False,
                    },
                )
                last_stream_event_id = "inference:1"

            if active_core is not None:
                node_name, core_task_id = active_core
                try:
                    core_result = core_client.get_task_result(core_task_id)
                except CoreClientError:
                    core_result = None
                snapshot = (
                    _agent_stream_step_snapshot(
                        run_id=run_id,
                        node_name=node_name,
                        core_task_id=core_task_id,
                        result=core_result.result,
                    )
                    if core_result is not None
                    else None
                )
                if snapshot is not None and snapshot["event_id"] != last_stream_event_id:
                    yield _sse("step_snapshot", snapshot)
                    last_stream_event_id = str(snapshot["event_id"])

            yield b": keep-alive\n\n"
            time.sleep(_AGENT_RUN_STREAM_POLL_SECONDS)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
