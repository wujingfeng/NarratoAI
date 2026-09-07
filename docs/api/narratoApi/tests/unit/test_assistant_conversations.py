from __future__ import annotations

import gzip
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from narrato_api.api.errors import ApiError
from narrato_api.artifacts.models import RegisteredArtifact
from narrato_api.auth.models import User
from narrato_api.assets.models import Asset
from narrato_api.billing.models import CreditAccount, CreditLedger
from narrato_api.conversations.models import (
    AgentRun,
    ConversationMessage,
    ConversationThread,
)
from narrato_api.config import Settings
from narrato_api.conversations.router import (
    DraftCreateRequest,
    MessageCreateRequest,
    ThreadTitleUpdateRequest,
    ThreadCreateRequest,
    _assert_generation_mode,
    _agent_stream_step_snapshot,
    _assert_agent_task_draft,
    _advance_inference_run,
    _advance_chat_message,
    _chat_task_prompt,
    _chat_context_messages,
    _inference_prompt,
    _normalized_original_sound_ratio,
    _refresh_chat_memory,
    _run_data,
    _parse_inference,
    _prepare_chat_retry,
    _start_llm_task,
    _stream_chat_task,
    _submit_inference_task_after_commit,
    _submit_model_task_in_background,
    _submit_video_task_after_commit,
    _watch_chat_stream,
    get_thread,
    list_threads,
    create_draft,
    create_thread,
    delete_thread,
    submit_message,
    update_thread_title,
)
from narrato_api.database import Base
from narrato_api.projects.models import Project
from narrato_api.products.ai_video import (
    _fail_task,
    _mark_completed,
    _precharge,
    _submit_task,
)
from narrato_api.products.model_generation import (
    Model,
    ModelPlayMode,
    ModelPlayModeProvider,
    ModelPlayModeProviderPrice,
    ModelPlayModeRule,
    ModelTask,
    ModelTaskAsset,
    ModelTaskOutput,
)
from narrato_api.products.providers import (
    LlmStreamDelta,
    ProviderError,
    ProviderOutput,
    ProviderResult,
)
from narrato_api.workflows.models import (
    Workflow,
    WorkflowNode,
    WorkflowNodeAttempt,
    WorkflowTemplateSnapshot,
)


class Auth:
    def resolve_user(self, _token: str) -> SimpleNamespace:
        return SimpleNamespace(id="usr")


def test_agent_stream_snapshot_maps_only_public_short_drama_stages() -> None:
    analysis = _agent_stream_step_snapshot(
        run_id="run",
        node_name="plot_structure",
        core_task_id="core",
        result={
            "stream": {
                "sequence": 2,
                "stage": "analysis",
                "outputs": {"analysis": "剧情结构草稿"},
            }
        },
    )
    matching = _agent_stream_step_snapshot(
        run_id="run",
        node_name="script_generation",
        core_task_id="core",
        result={
            "stream": {
                "sequence": 4,
                "stage": "matching",
                "outputs": {"generation": "解说文案草稿"},
            }
        },
    )

    assert analysis == {
        "run_id": "run",
        "event_id": "core:2",
        "sequence": 2,
        "step_id": "plot_structure",
        "phase": "analysis",
        "status_label": "正在理解剧情结构…",
        "content": "剧情结构草稿",
        "draft": True,
        "completed": False,
    }
    assert matching is not None
    assert matching["step_id"] == "script_generation"
    assert matching["status_label"] == "正在匹配解说文案与视频画面…"
    assert matching["content"] == "## 解说文案草稿\n\n解说文案草稿"
    assert (
        _agent_stream_step_snapshot(
            run_id="run",
            node_name="plot_structure",
            core_task_id="core",
            result={"stream": {"sequence": 1, "stage": "private_reasoning"}},
        )
        is None
    )


def _request(engine):
    return SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(database_engine=engine))
    )


def test_assistant_llm_output_language_follows_site_locale() -> None:
    assert "English" in _chat_task_prompt("hello", locale="en")
    assert "日本語" in _chat_task_prompt("こんにちは", locale="ja")
    assert "English" in _inference_prompt(
        mode="short_drama_narration",
        content="Create a fast-paced narration.",
        target_language=None,
        voice_ids=["voice"],
        locale="en",
    )
    request = MessageCreateRequest(mode="chat", content="hello", input={"locale": "ja"})
    assert request.options.response_locale == "ja"


def test_chat_message_is_persisted_and_never_creates_agent_run(monkeypatch) -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(User(id="usr", email="user@example.test", password_hash="hash"))
        session.commit()
    request, auth = _request(engine), Auth()
    monkeypatch.setattr(
        "narrato_api.conversations.router._start_llm_task",
        lambda *_args, **_kwargs: "chat-task",
    )
    monkeypatch.setattr(
        "narrato_api.conversations.router._submit_inference_task_after_commit",
        lambda *_args, **_kwargs: None,
    )
    thread = create_thread(
        ThreadCreateRequest(mode="chat", title="测试"),
        request,
        "token",
        auth,
        "req-thread",
    ).data
    assert thread is not None

    result = submit_message(
        thread.id,
        MessageCreateRequest(mode="chat", content="给我一个脚本建议"),
        request,
        "token",
        auth,
        SimpleNamespace(),
        "req-message",
        "message-key",
    ).data
    assert result is not None
    assert result.run is None
    assert result.assistant_message.mode == "chat"
    assert result.assistant_message.content == "正在生成回复…"
    with Session(engine) as session:
        assert session.query(ConversationMessage).count() == 2
        assert session.query(AgentRun).count() == 0


def test_thread_message_attachment_includes_display_metadata() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(User(id="usr", email="user@example.test", password_hash="hash"))
        session.add(
            Project(id="project", user_id="usr", product="short_drama_narration")
        )
        session.add(ConversationThread(id="thread", user_id="usr", mode="chat"))
        session.add(
            Asset(
                id="asset",
                user_id="usr",
                project_id="project",
                asset_type="video",
                status="ready",
                filename="episode-01.mp4",
                bucket="bucket",
                object_key="uploads/episode-01.mp4",
                cdn_url="https://cdn.example.test/episode-01.mp4",
                size_bytes=1024,
            )
        )
        session.add(
            ConversationMessage(
                id="message",
                thread_id="thread",
                user_id="usr",
                role="user",
                mode="short_drama_narration",
                content="生成解说",
                attachments=[{"asset_id": "asset"}],
            )
        )
        session.commit()

    response = get_thread("thread", _request(engine), "token", Auth(), "req-thread")
    assert response.data is not None
    attachment = response.data.messages[0].attachments[0]
    assert attachment == {
        "asset_id": "asset",
        "filename": "episode-01.mp4",
        "asset_type": "video",
        "status": "ready",
        "url": "https://cdn.example.test/episode-01.mp4",
        "size_bytes": 1024,
    }


def test_thread_title_can_be_renamed_and_thread_can_be_deleted() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(User(id="usr", email="user@example.test", password_hash="hash"))
        session.add(Project(id="project", user_id="usr", product="ai_video"))
        session.add(
            ConversationThread(id="thread", user_id="usr", mode="chat", title="旧名称")
        )
        session.add(
            ConversationMessage(
                id="message",
                thread_id="thread",
                user_id="usr",
                role="user",
                mode="chat",
                content="你好",
            )
        )
        session.add(
            AgentRun(
                id="run",
                thread_id="thread",
                message_id="message",
                user_id="usr",
                mode="video_generation",
                status="completed",
                idempotency_key="run-key",
                project_id="project",
            )
        )
        session.commit()

    request, auth = _request(engine), Auth()
    renamed = update_thread_title(
        "thread",
        ThreadTitleUpdateRequest(title="  我的聊天记录  "),
        request,
        "token",
        auth,
        "req-rename",
    ).data
    assert renamed is not None and renamed.title == "我的聊天记录"

    deleted = delete_thread("thread", request, "token", auth, "req-delete").data
    assert deleted is not None and deleted.id == "thread"
    with Session(engine) as session:
        assert session.get(ConversationThread, "thread") is None
        assert session.get(ConversationMessage, "message") is None
        assert session.get(AgentRun, "run") is None
        assert session.get(Project, "project") is not None


def test_first_user_prompt_becomes_persisted_thread_title(monkeypatch) -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(User(id="usr", email="user@example.test", password_hash="hash"))
        session.commit()
    request, auth = _request(engine), Auth()
    monkeypatch.setattr(
        "narrato_api.conversations.router._start_llm_task",
        lambda *_args, **_kwargs: "chat-task",
    )
    monkeypatch.setattr(
        "narrato_api.conversations.router._submit_inference_task_after_commit",
        lambda *_args, **_kwargs: None,
    )
    thread = create_thread(
        ThreadCreateRequest(mode="chat"), request, "token", auth, "req-thread"
    ).data
    assert thread is not None

    result = submit_message(
        thread.id,
        MessageCreateRequest(mode="chat", content="  帮我写一段短剧解说文案  "),
        request,
        "token",
        auth,
        SimpleNamespace(),
        "req-message",
        "message-key",
    ).data

    assert result is not None
    assert result.thread_title == "帮我写一段短剧解说文案"
    assert (
        list_threads(request, "token", auth, "req-list").data[0].title
        == "帮我写一段短剧解说文案"
    )


def test_chat_respects_explicit_model_id(monkeypatch) -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(User(id="usr", email="user@example.test", password_hash="hash"))
        session.commit()
    request, auth = _request(engine), Auth()
    received: dict[str, object] = {}
    monkeypatch.setattr(
        "narrato_api.conversations.router._start_llm_task",
        lambda *_args, **kwargs: received.update(kwargs) or "chat-task",
    )
    monkeypatch.setattr(
        "narrato_api.conversations.router._submit_inference_task_after_commit",
        lambda *_args, **_kwargs: None,
    )
    thread = create_thread(
        ThreadCreateRequest(mode="chat"), request, "token", auth, "req-thread"
    ).data
    assert thread is not None

    submit_message(
        thread.id,
        MessageCreateRequest(
            mode="chat", content="你好", input={"model_id": "selected-llm"}
        ),
        request,
        "token",
        auth,
        SimpleNamespace(),
        "req-message",
        "message-key",
    )

    assert received["model_id"] == "selected-llm"


def test_stream_chat_task_persists_deltas_and_completes_model_task(monkeypatch) -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(User(id="usr", email="user@example.test", password_hash="hash"))
        session.add(ConversationThread(id="thread", user_id="usr", mode="chat"))
        session.add(Model(id="model", display_name="LLM", model_type="llm"))
        session.add(
            ModelPlayMode(
                id="mode",
                model_id="model",
                code="chat",
                display_name="Chat",
                active_provider_id="provider",
            )
        )
        session.add(
            ModelPlayModeProvider(
                id="provider",
                play_mode_id="mode",
                provider_code="duoyuanx",
                provider_model_id="llm",
                submit_url="https://duoyuanx.com/v1/chat/completions",
                api_key="key",
            )
        )
        session.add(
            ModelTask(
                id="task",
                user_id="usr",
                model_id="model",
                play_mode_id="mode",
                provider_id="provider",
                task_type="llm",
                status="submitting",
                idempotency_key="key",
                prompt="你好",
            )
        )
        session.add(
            ConversationMessage(
                id="assistant",
                thread_id="thread",
                user_id="usr",
                role="assistant",
                mode="chat",
                content="正在生成回复…",
                idempotency_key="chat_llm:task",
            )
        )
        session.commit()

    class Adapter:
        def stream_chat(self, **_kwargs):
            with Session(engine) as session:
                task = session.get(ModelTask, "task")
                assert task is not None
                assert task.poll_lease_token == "assistant-stream:assistant"
                assert task.poll_lease_until is not None
            yield LlmStreamDelta(text="你")
            yield LlmStreamDelta(
                text="好",
                input_token=5,
                output_token=2,
                raw={"usage": {"prompt_tokens": 5, "completion_tokens": 2}},
            )

    monkeypatch.setattr(
        "narrato_api.conversations.router.get_provider_registry",
        lambda _request: SimpleNamespace(get=lambda _code: Adapter()),
    )
    events = b"".join(
        _stream_chat_task(
            _request(engine), task_id="task", assistant_message_id="assistant"
        )
    ).decode("utf-8")

    assert "event: message_start" in events
    assert "event: delta" in events
    assert "event: completed" in events
    with Session(engine) as session:
        assert session.get(ConversationMessage, "assistant").content == "你好"
        task = session.get(ModelTask, "task")
        assert task is not None and task.status == "succeeded"
        assert task.poll_lease_token is None
        assert task.poll_lease_until is None
        assert (
            session.query(ModelTaskOutput).filter_by(task_id="task").one().text_content
            == "你好"
        )


def test_stream_chat_submits_prior_chat_context_to_provider(monkeypatch) -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    started_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
    with Session(engine) as session:
        session.add(User(id="usr", email="user@example.test", password_hash="hash"))
        session.add(ConversationThread(id="thread", user_id="usr", mode="chat"))
        session.add(Model(id="model", display_name="LLM", model_type="llm"))
        session.add(
            ModelPlayMode(
                id="mode",
                model_id="model",
                code="chat",
                display_name="Chat",
                active_provider_id="provider",
            )
        )
        session.add(
            ModelPlayModeProvider(
                id="provider",
                play_mode_id="mode",
                provider_code="duoyuanx",
                provider_model_id="llm",
                submit_url="https://duoyuanx.com/v1/chat/completions",
                api_key="key",
            )
        )
        session.add(
            ModelTask(
                id="task",
                user_id="usr",
                model_id="model",
                play_mode_id="mode",
                provider_id="provider",
                task_type="llm",
                status="submitting",
                idempotency_key="key",
                prompt="兼容 prompt",
            )
        )
        session.add_all(
            [
                ConversationMessage(
                    id="first-user",
                    thread_id="thread",
                    user_id="usr",
                    role="user",
                    mode="chat",
                    content="我叫小明",
                    created_at=started_at,
                ),
                ConversationMessage(
                    id="first-assistant",
                    thread_id="thread",
                    user_id="usr",
                    role="assistant",
                    mode="chat",
                    content="好的，小明。",
                    created_at=started_at + timedelta(seconds=1),
                ),
                ConversationMessage(
                    id="current-user",
                    thread_id="thread",
                    user_id="usr",
                    role="user",
                    mode="chat",
                    content="我叫什么名字？",
                    created_at=started_at + timedelta(seconds=2),
                ),
                ConversationMessage(
                    id="assistant",
                    thread_id="thread",
                    user_id="usr",
                    role="assistant",
                    mode="chat",
                    content="正在生成回复…",
                    idempotency_key="chat_llm:task",
                    created_at=started_at + timedelta(seconds=3),
                ),
            ]
        )
        session.flush()
        task = session.get(ModelTask, "task")
        assert task is not None
        task.provider_request = {
            "chat_context_messages": _chat_context_messages(
                session,
                thread_id="thread",
                user_id="usr",
                assistant_message_id="assistant",
            )
        }
        session.commit()

    received: dict[str, object] = {}

    class Adapter:
        def stream_chat(self, **kwargs):
            received.update(kwargs)
            yield LlmStreamDelta(text="你叫小明。", input_token=5, output_token=3)

    monkeypatch.setattr(
        "narrato_api.conversations.router.get_provider_registry",
        lambda _request: SimpleNamespace(get=lambda _code: Adapter()),
    )
    b"".join(
        _stream_chat_task(
            _request(engine), task_id="task", assistant_message_id="assistant"
        )
    )

    assert received["messages"] == [
        {
            "role": "system",
            "content": "你是 NarratoAI 的普通聊天助手。直接、简洁地回答用户；不要创建项目、工作流或视频生成任务。所有面向用户的自然语言内容必须使用简体中文。",
        },
        {"role": "user", "content": [{"type": "text", "text": "我叫小明"}]},
        {"role": "assistant", "content": "好的，小明。"},
        {"role": "user", "content": [{"type": "text", "text": "我叫什么名字？"}]},
    ]


def test_chat_context_uses_structured_memory_summary_and_relevant_history() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    started_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
    with Session(engine) as session:
        session.add(User(id="usr", email="user@example.test", password_hash="hash"))
        session.add(
            ConversationThread(
                id="thread",
                user_id="usr",
                mode="chat",
                chat_summary="用户此前在规划一次日本旅行。",
                chat_memory={
                    "facts": [{"key": "preferred_language", "value": "中文"}],
                    "active_goal": "完成日本旅行规划",
                },
            )
        )
        session.add_all(
            [
                ConversationMessage(
                    id="tokyo-user",
                    thread_id="thread",
                    user_id="usr",
                    role="user",
                    mode="chat",
                    content="我计划去东京旅行。",
                    created_at=started_at,
                ),
                ConversationMessage(
                    id="tokyo-assistant",
                    thread_id="thread",
                    user_id="usr",
                    role="assistant",
                    mode="chat",
                    content="东京适合安排四天行程。",
                    created_at=started_at + timedelta(seconds=1),
                ),
            ]
        )
        for index in range(7):
            offset = 10 + index * 2
            session.add(
                ConversationMessage(
                    id=f"noise-user-{index}",
                    thread_id="thread",
                    user_id="usr",
                    role="user",
                    mode="chat",
                    content=f"无关事项 {index}",
                    created_at=started_at + timedelta(seconds=offset),
                )
            )
            session.add(
                ConversationMessage(
                    id=f"noise-assistant-{index}",
                    thread_id="thread",
                    user_id="usr",
                    role="assistant",
                    mode="chat",
                    content=f"无关回复 {index}",
                    created_at=started_at + timedelta(seconds=offset + 1),
                )
            )
        session.add(
            ConversationMessage(
                id="current-user",
                thread_id="thread",
                user_id="usr",
                role="user",
                mode="chat",
                content="继续安排东京旅行。",
                created_at=started_at + timedelta(seconds=40),
            )
        )
        session.add(
            ConversationMessage(
                id="assistant",
                thread_id="thread",
                user_id="usr",
                role="assistant",
                mode="chat",
                content="正在生成回复…",
                idempotency_key="chat_llm:task",
                created_at=started_at + timedelta(seconds=41),
            )
        )
        session.flush()

        messages = _chat_context_messages(
            session,
            thread_id="thread",
            user_id="usr",
            assistant_message_id="assistant",
        )

    system_texts = [item["content"] for item in messages if item["role"] == "system"]
    assert any("preferred_language: 中文" in text for text in system_texts)
    assert any("日本旅行" in text for text in system_texts)
    assert any("我计划去东京旅行" in text for text in system_texts)
    assert messages[-1] == {
        "role": "user",
        "content": [{"type": "text", "text": "继续安排东京旅行。"}],
    }


def test_chat_context_includes_prior_agent_run_summary_without_granting_tools() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    started_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
    with Session(engine) as session:
        session.add(User(id="usr", email="user@example.test", password_hash="hash"))
        session.add(ConversationThread(id="thread", user_id="usr", mode="chat"))
        session.add(
            ConversationMessage(
                id="video-request",
                thread_id="thread",
                user_id="usr",
                role="user",
                mode="video_generation",
                content="舞蹈教室里，一位女孩跳现代舞，电影质感。",
                created_at=started_at,
            )
        )
        session.add(
            AgentRun(
                id="video-run",
                thread_id="thread",
                message_id="video-request",
                user_id="usr",
                mode="video_generation",
                status="completed",
                idempotency_key="video-run-key",
                input_config={"content": "舞蹈教室里，一位女孩跳现代舞，电影质感。"},
                resolved_config={
                    "generation_mode": "text_to_video",
                    "ratio": "9:16",
                    "duration_seconds": 4,
                    "resolution": "480p",
                    "audio_enabled": False,
                },
                result={"video_url": "https://cdn.example.test/generated.mp4"},
                created_at=started_at + timedelta(seconds=1),
            )
        )
        session.add(
            ConversationMessage(
                id="chat-request",
                thread_id="thread",
                user_id="usr",
                role="user",
                mode="chat",
                content="帮我优化上面那个任务的提示词。",
                created_at=started_at + timedelta(seconds=2),
            )
        )
        session.add(
            ConversationMessage(
                id="assistant",
                thread_id="thread",
                user_id="usr",
                role="assistant",
                mode="chat",
                content="正在生成回复…",
                idempotency_key="chat_llm:task",
                created_at=started_at + timedelta(seconds=3),
            )
        )
        session.flush()

        messages = _chat_context_messages(
            session,
            thread_id="thread",
            user_id="usr",
            assistant_message_id="assistant",
        )

    agent_context = next(
        item["content"]
        for item in messages
        if item["role"] == "system" and "Agent 任务摘要" in item["content"]
    )
    assert "舞蹈教室里，一位女孩跳现代舞，电影质感。" in agent_context
    assert '"mode":"video_generation"' in agent_context
    assert '"ratio":"9:16"' in agent_context
    assert "https://cdn.example.test/generated.mp4" in agent_context
    assert "不授予你创建、重试、修改或操作任何任务的能力" in agent_context


def test_chat_memory_refresh_keeps_confirmed_facts_and_compacts_old_turns() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    started_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
    with Session(engine) as session:
        session.add(User(id="usr", email="user@example.test", password_hash="hash"))
        session.add(ConversationThread(id="thread", user_id="usr", mode="chat"))
        for index in range(7):
            offset = index * 2
            content = (
                "我叫小明，请用中文回复。"
                if index == 0
                else f"第 {index} 个长期讨论主题"
            )
            session.add(
                ConversationMessage(
                    id=f"user-{index}",
                    thread_id="thread",
                    user_id="usr",
                    role="user",
                    mode="chat",
                    content=content,
                    created_at=started_at + timedelta(seconds=offset),
                )
            )
            session.add(
                ConversationMessage(
                    id=f"assistant-{index}",
                    thread_id="thread",
                    user_id="usr",
                    role="assistant",
                    mode="chat",
                    content=f"第 {index} 个回答",
                    created_at=started_at + timedelta(seconds=offset + 1),
                )
            )
        session.flush()

        _refresh_chat_memory(session, thread_id="thread", user_id="usr")
        thread = session.get(ConversationThread, "thread")
        assert thread is not None
        facts = {item["key"]: item["value"] for item in thread.chat_memory["facts"]}
        assert facts["preferred_name"] == "小明"
        assert facts["preferred_language"] == "中文"
        assert thread.chat_memory["active_goal"] == "第 6 个长期讨论主题"
        assert thread.chat_summary is not None and "我叫小明" in thread.chat_summary
        assert thread.chat_memory_updated_at is not None


def test_stream_chat_replaces_output_written_by_racing_worker(monkeypatch) -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(User(id="usr", email="user@example.test", password_hash="hash"))
        session.add(ConversationThread(id="thread", user_id="usr", mode="chat"))
        session.add(Model(id="model", display_name="LLM", model_type="llm"))
        session.add(
            ModelPlayMode(
                id="mode",
                model_id="model",
                code="chat",
                display_name="Chat",
                active_provider_id="provider",
            )
        )
        session.add(
            ModelPlayModeProvider(
                id="provider",
                play_mode_id="mode",
                provider_code="duoyuanx",
                provider_model_id="llm",
                submit_url="https://duoyuanx.com/v1/chat/completions",
                api_key="key",
            )
        )
        session.add(
            ModelTask(
                id="task",
                user_id="usr",
                model_id="model",
                play_mode_id="mode",
                provider_id="provider",
                task_type="llm",
                status="processing",
                idempotency_key="key",
                prompt="分析图片",
            )
        )
        session.add(
            ConversationMessage(
                id="assistant",
                thread_id="thread",
                user_id="usr",
                role="assistant",
                mode="chat",
                content="正在生成回复…",
                idempotency_key="chat_llm:task",
            )
        )
        session.add(
            ModelTaskOutput(
                id="stale",
                task_id="task",
                output_type="text",
                text_content="我没有收到图片",
                sort_order=0,
            )
        )
        session.commit()

    class Adapter:
        def stream_chat(self, **_kwargs):
            yield LlmStreamDelta(text="图片中是一张产品宣传图")

    monkeypatch.setattr(
        "narrato_api.conversations.router.get_provider_registry",
        lambda _request: SimpleNamespace(get=lambda _code: Adapter()),
    )
    b"".join(
        _stream_chat_task(
            _request(engine), task_id="task", assistant_message_id="assistant"
        )
    )

    with Session(engine) as session:
        output = (
            session.query(ModelTaskOutput).filter_by(task_id="task", sort_order=0).one()
        )
        assert output.text_content == "图片中是一张产品宣传图"
        assert (
            session.get(ConversationMessage, "assistant").content
            == "图片中是一张产品宣传图"
        )


def test_thread_refresh_does_not_replace_persisted_stream_content() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(
            ModelTask(
                id="task",
                user_id="usr",
                model_id="llm",
                play_mode_id="chat",
                provider_id="provider",
                task_type="llm",
                status="succeeded",
                idempotency_key="key",
            )
        )
        session.add(
            ModelTaskOutput(
                id="stale",
                task_id="task",
                output_type="text",
                text_content="我没有收到图片",
                sort_order=0,
            )
        )
        message = ConversationMessage(
            id="assistant",
            thread_id="thread",
            user_id="usr",
            role="assistant",
            mode="chat",
            content="这是已经完成的流式图片分析。",
            idempotency_key="chat_llm:task",
        )
        session.add(message)
        session.flush()

        _advance_chat_message(session, message)

        assert message.content == "这是已经完成的流式图片分析。"


def test_chat_retry_appends_reply_by_creation_time_without_new_input(
    monkeypatch,
) -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    received: dict[str, object] = {}
    with Session(engine) as session:
        started_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
        session.add(User(id="usr", email="user@example.test", password_hash="hash"))
        session.add(Project(id="project", user_id="usr", product="ai_video"))
        session.add(
            Asset(
                id="image",
                user_id="usr",
                project_id="project",
                asset_type="image",
                status="ready",
                filename="reference.webp",
                bucket="bucket",
                object_key="reference.webp",
                cdn_url="https://cdn.example.test/reference.webp",
                size_bytes=10,
            )
        )
        session.add(ConversationThread(id="thread", user_id="usr", mode="chat"))
        session.add(
            ConversationMessage(
                id="source",
                thread_id="thread",
                user_id="usr",
                role="user",
                mode="chat",
                content="分析图片",
                attachments=[{"asset_id": "image"}],
                created_at=started_at,
            )
        )
        session.add(
            ModelTask(
                id="old-task",
                project_id="project",
                user_id="usr",
                model_id="model",
                play_mode_id="mode",
                provider_id="provider",
                task_type="llm",
                status="succeeded",
                idempotency_key="old",
                prompt="原始完整提示词",
            )
        )
        session.add(
            ModelTaskAsset(
                id="old-link",
                task_id="old-task",
                asset_id="image",
                input_type="image",
                provider_role="reference_image",
                sort_order=0,
            )
        )
        session.add(
            ConversationMessage(
                id="assistant",
                thread_id="thread",
                user_id="usr",
                role="assistant",
                mode="chat",
                content="旧回复",
                idempotency_key="chat_llm:old-task",
                created_at=started_at + timedelta(seconds=1),
            )
        )
        session.add(
            ConversationMessage(
                id="later-source",
                thread_id="thread",
                user_id="usr",
                role="user",
                mode="chat",
                content="后续输入",
                attachments=[],
                created_at=started_at + timedelta(seconds=2),
            )
        )
        session.add(
            ConversationMessage(
                id="later-assistant",
                thread_id="thread",
                user_id="usr",
                role="assistant",
                mode="chat",
                content="后续回复",
                idempotency_key="chat_llm:later-task",
                created_at=started_at + timedelta(seconds=3),
            )
        )
        session.flush()

        def start_task(current_session, **kwargs):
            received.update(kwargs)
            current_session.add(
                ModelTask(
                    id="retry-task",
                    project_id=kwargs["project_id"],
                    user_id="usr",
                    model_id=kwargs["model_id"],
                    play_mode_id="mode",
                    provider_id="provider",
                    task_type="llm",
                    status="submitting",
                    idempotency_key=kwargs["idempotency_key"],
                    prompt=kwargs["prompt"],
                )
            )
            current_session.flush()
            return "retry-task"

        monkeypatch.setattr(
            "narrato_api.conversations.router._start_llm_task", start_task
        )
        thread = session.get(ConversationThread, "thread")
        assert thread is not None
        retry_assistant, task_id = _prepare_chat_retry(
            session,
            thread=thread,
            user_id="usr",
            assistant_message_id="assistant",
            idempotency_key="retry-key",
        )

        assert session.query(ConversationMessage).count() == 5
        assert session.query(ConversationMessage).filter_by(role="user").count() == 2
        assert session.get(ConversationMessage, "assistant").content == "旧回复"
        assert retry_assistant.id not in {"assistant", "later-assistant"}
        assert retry_assistant.content == "正在生成回复…"
        assert retry_assistant.idempotency_key == "chat_llm:retry-task"
        assert retry_assistant.created_at > started_at + timedelta(seconds=3)
        assert task_id == "retry-task"
        retry_task = session.get(ModelTask, "retry-task")
        assert retry_task is not None
        assert retry_task.poll_lease_token == f"assistant-stream:{retry_assistant.id}"
        ordered_ids = list(
            session.scalars(
                select(ConversationMessage.id)
                .where(ConversationMessage.thread_id == "thread")
                .order_by(ConversationMessage.created_at)
            )
        )
        assert ordered_ids == [
            "source",
            "assistant",
            "later-source",
            "later-assistant",
            retry_assistant.id,
        ]

    assert received["prompt"] == "原始完整提示词"
    assert received["project_id"] == "project"
    assert received["image_asset_ids"] == ["image"]
    assert received["model_id"] == "model"


def test_chat_retry_reuses_completed_attachment_project_without_video_lifecycle_lock() -> (
    None
):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(User(id="usr", email="user@example.test", password_hash="hash"))
        session.add(
            Project(
                id="project",
                user_id="usr",
                product="ai_video",
                status="completed",
                current_stage="generate",
            )
        )
        session.add(
            Asset(
                id="image",
                user_id="usr",
                project_id="project",
                asset_type="image",
                status="ready",
                filename="reference.webp",
                bucket="bucket",
                object_key="reference.webp",
                cdn_url="https://cdn.example.test/reference.webp",
                size_bytes=10,
            )
        )
        session.add(
            Model(id="model", display_name="LLM", model_type="llm", is_default=True)
        )
        session.add(
            ModelPlayMode(
                id="mode",
                model_id="model",
                code="chat",
                display_name="Chat",
                active_provider_id="provider",
                default_credits=0,
                is_default=True,
            )
        )
        session.add(
            ModelPlayModeProvider(
                id="provider",
                play_mode_id="mode",
                provider_code="duoyuanx",
                provider_model_id="llm",
                submit_url="https://duoyuanx.com/v1/chat/completions",
                api_key="key",
            )
        )
        session.add_all(
            [
                ModelPlayModeRule(
                    id="rule-text",
                    play_mode_id="mode",
                    rule_kind="input_constraint",
                    input_type="text",
                    is_supported=True,
                    max_text_units=1000,
                ),
                ModelPlayModeRule(
                    id="rule-image",
                    play_mode_id="mode",
                    rule_kind="input_constraint",
                    input_type="image",
                    is_supported=True,
                    max_count=1,
                    max_file_size_bytes=1024,
                ),
                ModelPlayModeProviderPrice(
                    id="price",
                    provider_id="provider",
                    billing_unit="token",
                    per_million_input_credits=0,
                    per_million_output_credits=0,
                ),
            ]
        )
        session.flush()

        completed_task_id = _start_llm_task(
            session,
            user_id="usr",
            idempotency_key="retry-completed",
            prompt="分析图片",
            project_id="project",
            image_asset_ids=["image"],
            model_id="model",
        )
        project = session.get(Project, "project")
        completed_task = session.get(ModelTask, completed_task_id)
        assert project is not None and completed_task is not None
        assert project.status == "completed"
        assert project.current_stage == "generate"
        completed_task.input_token = 0
        completed_task.output_token = 0
        _mark_completed(session, completed_task)
        assert project.status == "completed"
        assert project.current_stage == "generate"

        failed_task_id = _start_llm_task(
            session,
            user_id="usr",
            idempotency_key="retry-failed",
            prompt="再次分析图片",
            project_id="project",
            image_asset_ids=["image"],
            model_id="model",
        )
        failed_task = session.get(ModelTask, failed_task_id)
        assert failed_task is not None
        _fail_task(session, failed_task, code="TEST_FAILED", message="test")
        assert project.status == "completed"
        assert project.current_stage == "generate"


def test_llm_worker_recovery_rebuilds_multimodal_messages() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    received: dict[str, object] = {}
    with Session(engine) as session:
        session.add(User(id="usr", email="user@example.test", password_hash="hash"))
        session.add(Project(id="project", user_id="usr", product="ai_video"))
        session.add(
            Asset(
                id="image",
                user_id="usr",
                project_id="project",
                asset_type="image",
                status="ready",
                filename="reference.webp",
                bucket="bucket",
                object_key="reference.webp",
                cdn_url="https://cdn.example.test/reference.webp",
                size_bytes=10,
            )
        )
        session.add(Model(id="model", display_name="LLM", model_type="llm"))
        session.add(
            ModelPlayMode(
                id="mode",
                model_id="model",
                code="chat",
                display_name="Chat",
                active_provider_id="provider",
            )
        )
        session.add(
            ModelPlayModeProvider(
                id="provider",
                play_mode_id="mode",
                provider_code="duoyuanx",
                provider_model_id="llm",
                submit_url="https://duoyuanx.com/v1/chat/completions",
                api_key="key",
            )
        )
        session.add(
            ModelTask(
                id="task",
                project_id="project",
                user_id="usr",
                model_id="model",
                play_mode_id="mode",
                provider_id="provider",
                task_type="llm",
                status="processing",
                idempotency_key="key",
                prompt="分析图片",
            )
        )
        session.add(
            ModelTaskAsset(
                id="link",
                task_id="task",
                asset_id="image",
                input_type="image",
                provider_role="reference_image",
                sort_order=0,
            )
        )
        session.flush()

        class Adapter:
            def submit(self, **kwargs):
                received.update(kwargs)
                return ProviderResult(status="succeeded", provider_task_id=None)

        registry = SimpleNamespace(get=lambda _code: Adapter())
        task = session.get(ModelTask, "task")
        assert task is not None
        _submit_task(registry, session, task)
        session.commit()

    assert received["messages"] == [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "分析图片"},
                {
                    "type": "image_url",
                    "image_url": {"url": "https://cdn.example.test/reference.webp"},
                },
            ],
        }
    ]
    frozen_context = [
        {"role": "system", "content": "聊天系统提示"},
        {"role": "user", "content": [{"type": "text", "text": "先前的对话"}]},
        {"role": "assistant", "content": "先前的回复"},
        {"role": "user", "content": [{"type": "text", "text": "当前问题"}]},
    ]
    with Session(engine) as session:
        task = session.get(ModelTask, "task")
        assert task is not None
        task.provider_request = {"chat_context_messages": frozen_context}
        _submit_task(registry, session, task)

    assert received["messages"] == frozen_context


def test_thread_mode_is_only_default_and_drafts_can_use_other_modes() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(User(id="usr", email="user@example.test", password_hash="hash"))
        session.commit()
    request, auth = _request(engine), Auth()
    thread = create_thread(
        ThreadCreateRequest(mode="chat"), request, "token", auth, "req-thread"
    ).data
    assert thread is not None
    video_draft = create_draft(
        thread.id,
        DraftCreateRequest(mode="video_generation"),
        request,
        "token",
        auth,
        "req-draft",
    ).data
    chat_draft = create_draft(
        thread.id,
        DraftCreateRequest(mode="chat"),
        request,
        "token",
        auth,
        "req-draft-chat",
    ).data
    translation_draft = create_draft(
        thread.id,
        DraftCreateRequest(mode="video_translation"),
        request,
        "token",
        auth,
        "req-draft-translation",
    ).data
    assert (
        video_draft is not None
        and chat_draft is not None
        and translation_draft is not None
    )
    with Session(engine) as session:
        assert session.get(Project, video_draft.project_id).product == "ai_video"
        assert session.get(Project, chat_draft.project_id).product == "ai_video"
        assert (
            session.get(Project, translation_draft.project_id).product
            == "video_translation"
        )


def test_video_generation_mode_attachment_contract_is_strict() -> None:
    assert _assert_generation_mode("text_to_video", []) is None
    with pytest.raises(ApiError) as error:
        _assert_generation_mode("first_frame", [])
    assert error.value.code == "GENERATION_MODE_ATTACHMENTS_INVALID"


@pytest.mark.parametrize("status", ["queued", "processing", "completed", "failed"])
def test_agent_task_always_requires_a_fresh_draft(status: str) -> None:
    with pytest.raises(ApiError) as error:
        _assert_agent_task_draft(
            Project(id="project", user_id="usr", product="ai_video", status=status)
        )
    assert error.value.code == "ASSISTANT_TASK_DRAFT_LOCKED"

    assert (
        _assert_agent_task_draft(
            Project(id="fresh", user_id="usr", product="ai_video", status="draft")
        )
        is None
    )


def test_inference_parser_requires_a_json_object() -> None:
    assert _parse_inference('```json\n{"voice_id":"v"}\n```') == {"voice_id": "v"}
    with pytest.raises(ApiError) as error:
        _parse_inference("not structured")
    assert error.value.code == "ASSISTANT_INFERENCE_INVALID"


@pytest.mark.parametrize(
    ("value", "expected"),
    [(0, 0), (15, 15), (15.9, 15), ("42.8", 42), (-0.1, 0), (101.9, 100)],
)
def test_original_sound_ratio_is_floored_and_bounded(value, expected) -> None:
    assert _normalized_original_sound_ratio({"original_sound_ratio": value}) == expected


@pytest.mark.parametrize("value", [True, None, "not-a-number"])
def test_original_sound_ratio_rejects_non_numeric_values(value) -> None:
    with pytest.raises(ApiError) as error:
        _normalized_original_sound_ratio({"original_sound_ratio": value})
    assert error.value.code == "ASSISTANT_INFERENCE_INVALID"


def test_failed_llm_inference_marks_run_failed_without_starting_workflow() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(User(id="usr", email="user@example.test", password_hash="hash"))
        session.add(ConversationThread(id="thread", user_id="usr", mode="chat"))
        session.add(
            ConversationMessage(
                id="message",
                thread_id="thread",
                user_id="usr",
                role="user",
                mode="short_drama_narration",
                content="解说",
            )
        )
        session.add(
            ModelTask(
                id="llm-task",
                user_id="usr",
                model_id="llm",
                play_mode_id="chat",
                provider_id="provider",
                task_type="llm",
                status="failed",
                idempotency_key="llm-key",
                error_code="MODEL_PROVIDER_FAILED",
                error_message="failed",
            )
        )
        run = AgentRun(
            id="run",
            thread_id="thread",
            message_id="message",
            user_id="usr",
            mode="short_drama_narration",
            status="running",
            idempotency_key="run-key",
            input_config={},
            resolved_config={},
            model_task_id="llm-task",
        )
        session.add(run)
        session.flush()
        _advance_inference_run(session, run)
        assert run.status == "failed"
        assert run.workflow_id is None
        assert run.error_code == "MODEL_PROVIDER_FAILED"


def test_inference_provider_failure_updates_agent_run_without_a_later_read(
    monkeypatch,
) -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(User(id="usr", email="user@example.test", password_hash="hash"))
        session.add(ConversationThread(id="thread", user_id="usr", mode="chat"))
        session.add(
            ConversationMessage(
                id="message",
                thread_id="thread",
                user_id="usr",
                role="user",
                mode="short_drama_narration",
                content="解说",
            )
        )
        session.add(
            ModelTask(
                id="llm-task",
                user_id="usr",
                model_id="llm",
                play_mode_id="chat",
                provider_id="provider",
                task_type="llm",
                status="submitting",
                idempotency_key="llm-key",
            )
        )
        session.add(
            AgentRun(
                id="run",
                thread_id="thread",
                message_id="message",
                user_id="usr",
                mode="short_drama_narration",
                status="running",
                idempotency_key="run-key",
                input_config={},
                resolved_config={},
                model_task_id="llm-task",
            )
        )
        session.commit()

    monkeypatch.setattr(
        "narrato_api.conversations.router.get_provider_registry",
        lambda _request: object(),
    )
    monkeypatch.setattr(
        "narrato_api.conversations.router._submit_task",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(ProviderError("unavailable")),
    )

    from narrato_api.conversations.router import _submit_inference_task_after_commit

    _submit_inference_task_after_commit(_request(engine), "llm-task")

    with Session(engine) as session:
        task = session.get(ModelTask, "llm-task")
        run = session.get(AgentRun, "run")
        assert task is not None and task.status == "failed"
        assert run is not None and run.status == "failed"
        assert run.error_code == "ASSISTANT_INFERENCE_PROVIDER_UNAVAILABLE"


def test_synchronous_inference_response_is_finalized_before_advancing_runs(
    monkeypatch,
) -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(User(id="usr", email="user@example.test", password_hash="hash"))
        session.add(
            ModelTask(
                id="llm-task",
                user_id="usr",
                model_id="llm",
                play_mode_id="chat",
                provider_id="provider",
                task_type="llm",
                status="submitting",
                idempotency_key="llm-key",
            )
        )
        session.commit()

    advanced: list[str] = []
    monkeypatch.setattr(
        "narrato_api.conversations.router.get_provider_registry",
        lambda _request: object(),
    )
    monkeypatch.setattr(
        "narrato_api.conversations.router._submit_task",
        lambda *_args, **_kwargs: ProviderResult(
            status="succeeded",
            provider_task_id=None,
            outputs=(ProviderOutput(output_type="text", text='{"ok":true}'),),
            input_token=1,
            output_token=1,
        ),
    )
    monkeypatch.setattr(
        "narrato_api.conversations.router._advance_inference_runs_for_task",
        lambda _session, *, task_id: advanced.append(task_id),
    )

    from narrato_api.conversations.router import _submit_inference_task_after_commit

    _submit_inference_task_after_commit(_request(engine), "llm-task")

    with Session(engine) as session:
        task = session.get(ModelTask, "llm-task")
        assert task is not None and task.status == "succeeded"
        assert (
            session.scalar(
                select(ModelTaskOutput).where(ModelTaskOutput.task_id == "llm-task")
            ).text_content
            == '{"ok":true}'
        )
    assert advanced == ["llm-task"]


def test_run_data_prefers_live_workflow_over_completed_inference_task() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(User(id="usr", email="user@example.test", password_hash="hash"))
        session.add(ConversationThread(id="thread", user_id="usr", mode="chat"))
        session.add(
            ConversationMessage(
                id="message",
                thread_id="thread",
                user_id="usr",
                role="user",
                mode="short_drama_narration",
                content="解说",
            )
        )
        session.add(
            Project(id="project", user_id="usr", product="short_drama_narration")
        )
        session.add(
            WorkflowTemplateSnapshot(
                id="template",
                template_name="short_drama_narration",
                version="v1",
                definition={},
            )
        )
        session.add(
            ModelTask(
                id="llm-task",
                user_id="usr",
                model_id="llm",
                play_mode_id="chat",
                provider_id="provider",
                task_type="llm",
                status="succeeded",
                idempotency_key="llm-key",
            )
        )
        session.add(
            Workflow(
                id="workflow",
                user_id="usr",
                project_id="project",
                template_snapshot_id="template",
                state="running",
                state_version=3,
            )
        )
        run = AgentRun(
            id="run",
            thread_id="thread",
            message_id="message",
            user_id="usr",
            mode="short_drama_narration",
            status="queued",
            idempotency_key="run-key",
            input_config={"assistant_message_id": "assistant"},
            resolved_config={
                "narration_style": "悬疑/犯罪",
                "video_ratio": "9:16",
                "requirements": "internal prompt-derived requirements",
                "execution_mode": "auto",
            },
            model_task_id="llm-task",
            workflow_id="workflow",
        )
        session.add(run)
        session.flush()
        data = _run_data(session, run)
        assert data.message_id == "message"
        assert data.assistant_message_id == "assistant"
        assert data.status == "running"
        payload = data.model_dump()
        assert data.display_config == {
            "narration_style": "悬疑/犯罪",
            "video_ratio": "9:16",
        }
        assert "requirements" not in data.display_config
        assert "input_config" not in payload
        assert "resolved_config" not in payload
        assert "task_id" not in payload
        assert "workflow_id" not in payload
        assert "result" not in payload


def test_run_data_maps_submitting_inference_to_active_public_status() -> None:
    """内部 submitting 必须投影为 running，避免浏览器停止 SSE 与轮询。"""

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(User(id="usr", email="user@example.test", password_hash="hash"))
        session.add(ConversationThread(id="thread", user_id="usr", mode="chat"))
        session.add(
            ConversationMessage(
                id="message",
                thread_id="thread",
                user_id="usr",
                role="user",
                mode="short_drama_narration",
                content="解说",
            )
        )
        session.add(
            ModelTask(
                id="llm-task",
                user_id="usr",
                model_id="llm",
                play_mode_id="chat",
                provider_id="provider",
                task_type="llm",
                status="submitting",
                idempotency_key="llm-key",
            )
        )
        run = AgentRun(
            id="run",
            thread_id="thread",
            message_id="message",
            user_id="usr",
            mode="short_drama_narration",
            status="queued",
            idempotency_key="run-key",
            input_config={},
            resolved_config={},
            model_task_id="llm-task",
        )
        session.add(run)
        session.flush()

        data = _run_data(session, run)

        assert data.status == "running"
        assert data.steps[0].id == "requirements_inference"
        assert data.steps[0].status == "running"


def test_completed_workflow_run_exposes_registered_video_preview() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(User(id="usr", email="user@example.test", password_hash="hash"))
        session.add(ConversationThread(id="thread", user_id="usr", mode="chat"))
        session.add(
            ConversationMessage(
                id="message",
                thread_id="thread",
                user_id="usr",
                role="user",
                mode="short_drama_narration",
                content="解说",
            )
        )
        session.add(
            Project(
                id="project",
                user_id="usr",
                product="short_drama_narration",
                status="completed",
                current_stage="export",
            )
        )
        session.add(
            WorkflowTemplateSnapshot(
                id="template",
                template_name="short_drama_narration",
                version="v1",
                definition={},
            )
        )
        session.add(
            Workflow(
                id="workflow",
                user_id="usr",
                project_id="project",
                template_snapshot_id="template",
                state="completed",
                state_version=7,
            )
        )
        session.add(
            RegisteredArtifact(
                id="video-artifact",
                project_id="project",
                kind="video",
                cdn_url="https://cdn.example.test/final.mp4",
            )
        )
        run = AgentRun(
            id="run",
            thread_id="thread",
            message_id="message",
            user_id="usr",
            mode="short_drama_narration",
            status="queued",
            idempotency_key="run-key",
            project_id="project",
            workflow_id="workflow",
        )
        session.add(run)
        session.flush()

        data = _run_data(session, run)

        assert data.status == "completed"
        assert data.video_url == "https://cdn.example.test/final.mp4"


def test_short_drama_run_projects_workflow_results_as_conversation_steps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    analysis = """## 一、基础识别
- 短剧名称：测试短剧

## 三、整体剧情概括
女主发现身份被冒用，决定当众反击。

## 五、解说创作重点
- 开场钩子：她直到领奖前才发现自己的名字被换掉。
- 核心冲突：女主与冒名者争夺真实身份。
- 爽点/泪点/情绪点：女主拿出证据完成反击。
- 悬念点：幕后主使仍未现身。
- 建议保留原声片段：
  1. video 1 00:00:08,000 --> 00:00:12,000：身份揭露。

## 六、联网信息校验
- 可用于辅助理解的信息：无
"""
    with Session(engine) as session:
        session.add(User(id="usr", email="user@example.test", password_hash="hash"))
        session.add(ConversationThread(id="thread", user_id="usr", mode="chat"))
        session.add(
            ConversationMessage(
                id="message",
                thread_id="thread",
                user_id="usr",
                role="user",
                mode="short_drama_narration",
                content="解说",
            )
        )
        session.add(
            Project(
                id="project",
                user_id="usr",
                product="short_drama_narration",
                status="completed",
                current_stage="export",
            )
        )
        session.add(
            Asset(
                id="video",
                user_id="usr",
                project_id="project",
                asset_type="video",
                status="ready",
                filename="episode-01.mp4",
                bucket="bucket",
                object_key="video.mp4",
                cdn_url="https://cdn.example.test/episode-01.mp4",
                size_bytes=1,
            )
        )
        session.add(
            WorkflowTemplateSnapshot(
                id="template",
                template_name="short_drama_narration",
                version="v2",
                definition={},
            )
        )
        session.add(
            Workflow(
                id="workflow",
                user_id="usr",
                project_id="project",
                template_snapshot_id="template",
                state="completed",
                state_version=7,
            )
        )
        result_by_name = {
            "subtitle_recognition": {
                "result": {
                    "subtitles": [
                        {
                            "source_asset_id": "video",
                            "artifact": {
                                "artifact_id": "core-subtitle",
                                "url": "https://cdn.example.test/episode-01.srt",
                            },
                            "preview_text": "1\n00:00:00,000 --> 00:00:02,000\n测试字幕",
                        }
                    ]
                }
            },
            "plot_structure": {
                "result": {
                    "artifacts": [
                        {
                            "kind": "analysis",
                            "artifact_id": "core-analysis",
                            "url": "https://cdn.example.test/analysis.json",
                        }
                    ]
                }
            },
            "conflict_highlights": {"result": {"analysis": {"summary": analysis}}},
            "highlight_scoring": {"result": {"analysis": {"summary": analysis}}},
            "script_generation": {
                "result": {
                    "editor_draft": {
                        "tracks": [
                            {
                                "type": "narration",
                                "items": [
                                    {
                                        "start": 0,
                                        "end": 5,
                                        "narration": "她没想到，领奖前名字竟被人换掉。",
                                    }
                                ],
                            }
                        ]
                    }
                }
            },
        }
        for index, name in enumerate(
            (
                "subtitle_recognition",
                "plot_structure",
                "conflict_highlights",
                "highlight_scoring",
                "script_generation",
                "video_render",
            )
        ):
            node = WorkflowNode(
                id=f"node-{index}",
                workflow_id="workflow",
                name=name,
                state="completed",
            )
            session.add(node)
            session.add(
                WorkflowNodeAttempt(
                    id=f"attempt-{index}",
                    workflow_node_id=node.id,
                    attempt_number=1,
                    state="completed",
                    state_version=1,
                    result=result_by_name.get(name, {}),
                )
            )
        session.add_all(
            [
                RegisteredArtifact(
                    id="video-artifact",
                    project_id="project",
                    kind="video",
                    cdn_url="https://cdn.example.test/final.mp4",
                ),
                RegisteredArtifact(
                    id="subtitle-artifact",
                    project_id="project",
                    kind="subtitle",
                    cdn_url="https://cdn.example.test/final.srt",
                ),
            ]
        )
        run = AgentRun(
            id="run",
            thread_id="thread",
            message_id="message",
            user_id="usr",
            mode="short_drama_narration",
            status="queued",
            idempotency_key="run-key",
            project_id="project",
            workflow_id="workflow",
            resolved_config={
                "narration_style": "逆袭/复仇",
                "video_ratio": "original",
            },
        )
        session.add(run)
        session.flush()

        payload = gzip.compress(
            json.dumps(
                {
                    "schema_version": "short-drama-analysis.v1",
                    "analysis": {"summary": analysis},
                }
            ).encode()
        )

        class AnalysisResponse:
            headers = {
                "Content-Encoding": "gzip",
                "Content-Length": str(len(payload)),
            }

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def geturl(self) -> str:
                return "https://cdn.example.test/analysis.json"

            def read(self, _limit: int) -> bytes:
                return payload

        monkeypatch.setattr(
            "narrato_api.conversations.router.urlopen",
            lambda *_args, **_kwargs: AnalysisResponse(),
        )

        data = _run_data(
            session,
            run,
            settings=Settings(cdn_public_base_url="https://cdn.example.test"),
        )
        steps = {step.id: step for step in data.steps}

        assert list(steps) == [
            "requirements_inference",
            "subtitle_recognition",
            "plot_structure",
            "conflict_highlights",
            "highlight_scoring",
            "script_generation",
            "video_render",
        ]
        assert steps["requirements_inference"].outputs[0].type == "markdown"
        assert steps["subtitle_recognition"].outputs[0].filename == "episode-01.srt"
        assert "测试字幕" in (steps["subtitle_recognition"].outputs[0].preview_text or "")
        assert "整体剧情概括" in (steps["plot_structure"].outputs[0].content or "")
        assert "核心冲突" in (steps["conflict_highlights"].outputs[0].content or "")
        assert "身份揭露" in (steps["highlight_scoring"].outputs[0].content or "")
        assert "领奖前名字" in (steps["script_generation"].outputs[0].content or "")
        assert {output.type for output in steps["video_render"].outputs} == {
            "file",
            "video",
        }
        payload = data.model_dump()
        assert "provider_raw" not in str(payload)


def test_run_data_preserves_failed_run_when_inference_task_succeeded() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(User(id="usr", email="user@example.test", password_hash="hash"))
        session.add(ConversationThread(id="thread", user_id="usr", mode="chat"))
        session.add(
            ConversationMessage(
                id="message",
                thread_id="thread",
                user_id="usr",
                role="user",
                mode="short_drama_narration",
                content="解说",
            )
        )
        session.add(
            ModelTask(
                id="llm-task",
                user_id="usr",
                model_id="llm",
                play_mode_id="chat",
                provider_id="provider",
                task_type="llm",
                status="succeeded",
                idempotency_key="llm-key",
            )
        )
        run = AgentRun(
            id="run",
            thread_id="thread",
            message_id="message",
            user_id="usr",
            mode="short_drama_narration",
            status="failed",
            idempotency_key="run-key",
            input_config={},
            resolved_config={},
            model_task_id="llm-task",
            error_code="ASSISTANT_INFERENCE_INVALID",
            error_message="LLM returned an invalid original_sound_ratio",
        )
        session.add(run)
        session.flush()

        data = _run_data(session, run)

        assert data.status == "failed"
        assert data.error_code == "ASSISTANT_INFERENCE_INVALID"
        assert data.error_message == "LLM returned an invalid original_sound_ratio"


def test_completed_chat_llm_task_backfills_assistant_message_without_agent_run() -> (
    None
):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(User(id="usr", email="user@example.test", password_hash="hash"))
        session.add(ConversationThread(id="thread", user_id="usr", mode="chat"))
        session.add(
            ModelTask(
                id="chat-task",
                user_id="usr",
                model_id="llm",
                play_mode_id="chat",
                provider_id="provider",
                task_type="llm",
                status="succeeded",
                idempotency_key="chat-key",
            )
        )
        message = ConversationMessage(
            id="assistant",
            thread_id="thread",
            user_id="usr",
            role="assistant",
            mode="chat",
            content="正在生成回复…",
            attachments=[],
            idempotency_key="chat_llm:chat-task",
        )
        session.add(message)
        session.add(
            ModelTaskOutput(
                id="output",
                task_id="chat-task",
                output_type="text",
                text_content="这是实际 LLM 回复。",
                sort_order=0,
            )
        )
        session.flush()
        _advance_chat_message(session, message)
        assert message.content == "这是实际 LLM 回复。"
        assert message.attachments == []
        assert session.query(AgentRun).count() == 0


def test_successful_short_drama_llm_inference_starts_workflow_only_after_json_validation(
    monkeypatch,
) -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    started: dict[str, object] = {}

    def start_workflow(_session, *, user_id, project_id, settings):
        started.update(
            {"user_id": user_id, "project_id": project_id, "settings": settings}
        )
        return "workflow"

    monkeypatch.setattr(
        "narrato_api.conversations.router.save_settings_and_start_analysis",
        start_workflow,
    )
    with Session(engine) as session:
        session.add(User(id="usr", email="user@example.test", password_hash="hash"))
        session.add(ConversationThread(id="thread", user_id="usr", mode="chat"))
        session.add(
            ConversationMessage(
                id="message",
                thread_id="thread",
                user_id="usr",
                role="user",
                mode="short_drama_narration",
                content="解说",
            )
        )
        session.add(
            Project(id="project", user_id="usr", product="short_drama_narration")
        )
        session.add(
            Asset(
                id="video",
                user_id="usr",
                project_id="project",
                asset_type="video",
                status="ready",
                filename="source.mp4",
                bucket="assets",
                object_key="source.mp4",
                cdn_url="https://cdn.example/source.mp4",
                size_bytes=1,
            )
        )
        session.add(
            ModelTask(
                id="llm-task",
                user_id="usr",
                model_id="llm",
                play_mode_id="chat",
                provider_id="provider",
                task_type="llm",
                status="succeeded",
                idempotency_key="llm-key",
            )
        )
        session.add(
            ModelTaskOutput(
                id="output",
                task_id="llm-task",
                output_type="text",
                text_content='{"narration_style":"悬疑/犯罪","video_ratio":"original","voice_id":"voice-1","requirements":"紧凑悬疑","target_duration_seconds":60,"original_sound_ratio":15.9}',
                sort_order=0,
            )
        )
        run = AgentRun(
            id="run",
            thread_id="thread",
            message_id="message",
            user_id="usr",
            mode="short_drama_narration",
            status="running",
            idempotency_key="run-key",
            input_config={
                "attachments": [{"asset_id": "video"}],
                "options": {
                    "source_subtitle_layouts": {
                        "video": {
                            "status": "confirmed",
                            "region": {
                                "x": 0,
                                "y": 0.7,
                                "width": 1,
                                "height": 0.15,
                            },
                            "detected_confidence": 0.91,
                        }
                    }
                },
                "inference_voice_ids": ["voice-1"],
            },
            resolved_config={},
            project_id="project",
            model_task_id="llm-task",
        )
        session.add(run)
        session.flush()
        _advance_inference_run(session, run)
        assert run.workflow_id == "workflow"
        assert run.status == "queued"
        assert started["settings"]["narration_style"] == "悬疑/犯罪"
        assert started["settings"]["original_sound_ratio"] == 15
        assert started["settings"]["target_duration_seconds"] == 60
        assert started["settings"]["execution_mode"] == "auto"
        assert started["settings"]["video_ratio"] == "original"
        assert started["settings"]["source_subtitle_layouts"] == {
            "video": {
                "status": "confirmed",
                "region": {"x": 0.0, "y": 0.7, "width": 1.0, "height": 0.15},
                "detected_confidence": 0.91,
            }
        }
        assert started["settings"]["narration_subtitle_position"] == {
            "y": pytest.approx(0.775),
            "font_scale": 0.9,
        }


def test_closing_a_stream_subscriber_does_not_fail_the_persisted_task(
    monkeypatch,
) -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(User(id="usr", email="user@example.test", password_hash="hash"))
        session.add(ConversationThread(id="thread", user_id="usr", mode="chat"))
        session.add(Model(id="model", display_name="LLM", model_type="llm"))
        session.add(
            ModelPlayMode(
                id="mode",
                model_id="model",
                code="chat",
                display_name="Chat",
                active_provider_id="provider",
            )
        )
        session.add(
            ModelPlayModeProvider(
                id="provider",
                play_mode_id="mode",
                provider_code="duoyuanx",
                provider_model_id="llm",
                submit_url="https://duoyuanx.com/v1/chat/completions",
                api_key="key",
            )
        )
        session.add(
            ModelTask(
                id="task",
                user_id="usr",
                model_id="model",
                play_mode_id="mode",
                provider_id="provider",
                task_type="llm",
                status="submitting",
                idempotency_key="key",
                prompt="你好",
            )
        )
        session.add(
            ConversationMessage(
                id="assistant",
                thread_id="thread",
                user_id="usr",
                role="assistant",
                mode="chat",
                content="正在生成回复…",
                idempotency_key="chat_llm:task",
            )
        )
        session.commit()

    class Adapter:
        def stream_chat(self, **_kwargs):
            yield LlmStreamDelta(text="已保存的前缀")
            yield LlmStreamDelta(text="后续文本")

    monkeypatch.setattr(
        "narrato_api.conversations.router.get_provider_registry",
        lambda _request: SimpleNamespace(get=lambda _code: Adapter()),
    )
    stream = _stream_chat_task(
        _request(engine), task_id="task", assistant_message_id="assistant"
    )
    next(stream)  # message_start
    next(stream)  # first persisted delta
    stream.close()  # Simulates an SSE consumer disconnecting.

    with Session(engine) as session:
        task = session.get(ModelTask, "task")
        message = session.get(ConversationMessage, "assistant")
        assert task is not None and task.status == "processing"
        assert message is not None and message.content == "已保存的前缀"


def test_resumed_stream_replays_persisted_content_and_completion() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(
            ModelTask(
                id="task",
                user_id="usr",
                model_id="model",
                play_mode_id="mode",
                provider_id="provider",
                task_type="llm",
                status="succeeded",
                idempotency_key="key",
            )
        )
        session.add(
            ConversationMessage(
                id="assistant",
                thread_id="thread",
                user_id="usr",
                role="assistant",
                mode="chat",
                content="已完成回复",
                idempotency_key="chat_llm:task",
            )
        )
        session.commit()

    events = b"".join(
        _watch_chat_stream(
            _request(engine), task_id="task", assistant_message_id="assistant"
        )
    ).decode("utf-8")
    assert "event: delta" in events
    assert "已完成回复" in events
    assert "event: completed" in events


def test_thread_messages_are_returned_as_newest_first_page_then_cursor_pages() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    started_at = datetime(2026, 8, 24, tzinfo=timezone.utc)
    with Session(engine) as session:
        session.add(User(id="usr", email="user@example.test", password_hash="hash"))
        session.add(ConversationThread(id="thread", user_id="usr", mode="chat"))
        for index in range(5):
            session.add(
                ConversationMessage(
                    id=f"message-{index}",
                    thread_id="thread",
                    user_id="usr",
                    role="user",
                    mode="chat",
                    content=str(index),
                    created_at=started_at + timedelta(seconds=index),
                )
            )
        session.commit()

    request, auth = _request(engine), Auth()
    newest = get_thread("thread", request, "token", auth, "req-latest", limit=2).data
    assert newest is not None
    assert [message.id for message in newest.messages] == ["message-3", "message-4"]
    assert newest.has_more is True and newest.next_before == "message-3"

    older = get_thread(
        "thread",
        request,
        "token",
        auth,
        "req-older",
        limit=2,
        before=newest.next_before,
    ).data
    assert older is not None
    assert [message.id for message in older.messages] == ["message-1", "message-2"]
    assert older.has_more is True and older.next_before == "message-1"

    oldest = get_thread(
        "thread",
        request,
        "token",
        auth,
        "req-oldest",
        limit=2,
        before=older.next_before,
    ).data
    assert oldest is not None
    assert [message.id for message in oldest.messages] == ["message-0"]
    assert oldest.has_more is False and oldest.next_before is None


def test_agent_submission_is_offloaded_from_the_http_request(monkeypatch) -> None:
    started: list[object] = []
    submitted: list[tuple[object, str]] = []

    class ImmediateThread:
        def __init__(self, *, target, **_kwargs):
            self.target = target

        def start(self) -> None:
            started.append(self)
            self.target()

    monkeypatch.setattr(
        "narrato_api.conversations.router.threading.Thread", ImmediateThread
    )
    monkeypatch.setattr(
        "narrato_api.conversations.router._submit_inference_task_after_commit",
        lambda request, task_id: submitted.append((request, task_id)),
    )
    request = SimpleNamespace()
    _submit_model_task_in_background(request, task_id="task", inference=True)

    assert started and submitted == [(request, "task")]


@pytest.mark.parametrize("inference", [False, True])
def test_assistant_provider_submission_failure_refunds_precharge(
    monkeypatch, inference: bool
) -> None:
    """助手异步提交的最终失败也必须走 ModelTask 统一退款。"""

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    task_type = "llm" if inference else "video"
    with Session(engine) as session:
        session.add_all(
            [
                User(id="usr", email="user@example.test", password_hash="hash"),
                CreditAccount(user_id="usr", balance=100),
                Project(id="project", user_id="usr", product="ai_video"),
                Model(id="model", display_name="Test", model_type=task_type),
                ModelPlayMode(
                    id="mode",
                    model_id="model",
                    code="text2video" if task_type == "video" else "chat",
                    display_name="Test mode",
                    active_provider_id="provider",
                ),
                ModelPlayModeProvider(
                    id="provider",
                    play_mode_id="mode",
                    provider_code="duoyuanx",
                    provider_model_id="test",
                    submit_url="https://duoyuanx.com/v1/test",
                    api_key="test",
                ),
            ]
        )
        task = ModelTask(
            id="task",
            project_id="project",
            user_id="usr",
            model_id="model",
            play_mode_id="mode",
            provider_id="provider",
            task_type=task_type,
            status="submitting",
            idempotency_key="task-key",
            default_credits_charged=10,
        )
        session.add(task)
        session.flush()
        _precharge(session, task)
        session.commit()

    class FailingProvider:
        def submit(self, **_kwargs):
            raise ProviderError("upstream rejected request")

    monkeypatch.setattr(
        "narrato_api.conversations.router.get_provider_registry",
        lambda _request: SimpleNamespace(get=lambda _code: FailingProvider()),
    )
    request = _request(engine)
    if inference:
        _submit_inference_task_after_commit(request, task_id="task")
    else:
        _submit_video_task_after_commit(request, task_id="task")

    with Session(engine) as session:
        task = session.get(ModelTask, "task")
        account = session.get(CreditAccount, "usr")
        entries = list(
            session.scalars(
                select(CreditLedger)
                .where(CreditLedger.reference_id == "task")
                .order_by(CreditLedger.id)
            )
        )
        assert task is not None and task.status == "failed"
        assert task.settlement_status == "refunded"
        assert account is not None and account.balance == 100
        assert [(entry.entry_type, entry.amount) for entry in entries] == [
            ("charge", -10),
            ("refund", 10),
        ]
