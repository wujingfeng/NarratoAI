from narrato_api.products.video_translation import (
    PRODUCT,
    PREVIEW_CREDITS,
    RATIOS,
    SUPPORTED_LANGUAGES,
    TranslationSettings,
    VideoTranslationSegment,
    _digest,
    _serialize,
    _text_units,
    _preview_caller_task_id,
    normalize_original_sound_mode,
)


def test_translation_product_contract_is_independent():
    assert PRODUCT == "video_translation"
    assert "original" in RATIOS and "3:4" in RATIOS
    assert set(("en", "ja", "ar")) <= set(SUPPORTED_LANGUAGES)
    assert PREVIEW_CREDITS == 12


def test_segment_limit_counts_cjk_characters_and_other_languages_words():
    assert _text_units("你 " * 100, "ja") == 100
    assert _text_units("one two three", "en") == 3


def test_preview_digest_changes_for_voice_and_text():
    segment = VideoTranslationSegment(
        id="s",
        project_id="p",
        segment_index=0,
        start_ms=0,
        end_ms=1000,
        source_text="a",
        translated_text="one",
        voice_id="v",
        speed=1,
        volume=100,
        keep_original_sound=False,
    )
    original = _digest(segment)
    segment.voice_id = "other"
    assert _digest(segment) != original


def test_translation_defaults_to_translated_voice_only_and_maps_legacy_values():
    assert TranslationSettings().original_sound_mode == "translated_voice_only"
    assert (
        TranslationSettings(original_sound_mode="keep").original_sound_mode
        == "voice_replacement"
    )
    assert (
        TranslationSettings(original_sound_mode="preserve").original_sound_mode
        == "voice_replacement"
    )
    assert (
        TranslationSettings(original_sound_mode="mute").original_sound_mode
        == "translated_voice_only"
    )
    assert normalize_original_sound_mode("unknown") == "translated_voice_only"


def test_segment_contract_exposes_actual_tts_timing_and_overflow():
    segment = VideoTranslationSegment(
        id="s",
        project_id="p",
        segment_index=0,
        start_ms=1000,
        end_ms=2500,
        source_text="a",
        translated_text="one",
        voice_id="v",
        speed=1,
        volume=100,
        keep_original_sound=False,
        tts_duration_ms=1900,
        timing_fit_status="rewrite_required",
        timing_overflow_ms=400,
        fitted_speed=1.2,
    )
    data = _serialize(segment)
    assert data.tts_duration_ms == 1900
    assert data.timing_fit_status == "rewrite_required"
    assert data.timing_overflow_ms == 400
    assert data.fitted_speed == 1.2


def test_reconciler_materializes_core_actual_tts_timing():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from narrato_api.auth.models import User
    from narrato_api.database import Base
    from narrato_api.projects.models import Project
    from narrato_api.workflows.reconciler import WorkflowReconciler

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        with session.begin():
            session.add(
                User(id="usr_timing", email="timing@example.com", password_hash="hash")
            )
            session.add(Project(id="prj_timing", user_id="usr_timing", product=PRODUCT))
            session.add(
                VideoTranslationSegment(
                    id="seg_timing",
                    project_id="prj_timing",
                    segment_index=0,
                    start_ms=0,
                    end_ms=1000,
                    source_text="a",
                    translated_text="one",
                    voice_id="v",
                    speed=1,
                    volume=100,
                    keep_original_sound=False,
                )
            )
        with session.begin():
            WorkflowReconciler._materialize_translation_tts_timings(
                session,
                project_id="prj_timing",
                result={
                    "metadata": {
                        "segment_timings": [
                            {
                                "segment_index": 0,
                                "tts_duration_ms": 1250,
                                "fitted_speed": 1.2,
                            }
                        ]
                    }
                },
            )
        row = session.get(VideoTranslationSegment, "seg_timing")
        assert row is not None
        assert row.tts_duration_ms == 1250
        assert row.timing_fit_status == "speed_adjusted"
        assert row.timing_overflow_ms == 50
        assert row.fitted_speed == 1.2


def test_reconciler_rewrites_only_affected_segment_and_invalidates_old_audio():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from narrato_api.auth.models import User
    from narrato_api.database import Base
    from narrato_api.projects.models import Project
    from narrato_api.products.video_translation import VideoTranslationSettings
    from narrato_api.workflows.reconciler import WorkflowReconciler

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        with session.begin():
            session.add(
                User(
                    id="usr_rewrite", email="rewrite@example.com", password_hash="hash"
                )
            )
            session.add(
                Project(id="prj_rewrite", user_id="usr_rewrite", product=PRODUCT)
            )
            session.add(
                VideoTranslationSettings(
                    project_id="prj_rewrite",
                    settings={"target_language": "en", "voice_id": "v"},
                )
            )
            session.add(
                VideoTranslationSegment(
                    id="seg_rewrite",
                    project_id="prj_rewrite",
                    segment_index=0,
                    start_ms=0,
                    end_ms=1000,
                    source_text="快跑",
                    translated_text="You need to run right now",
                    voice_id="v",
                    speed=1,
                    volume=100,
                    keep_original_sound=False,
                    preview_audio_url="https://cdn.example/old.wav",
                    preview_digest="old",
                    tts_duration_ms=1600,
                    timing_fit_status="rewrite_required",
                    timing_overflow_ms=400,
                )
            )
        with session.begin():
            WorkflowReconciler._materialize_rewritten_translation_segments(
                session,
                project_id="prj_rewrite",
                result={
                    "segments": [
                        {
                            "segment_id": "seg_rewrite",
                            "translated_text": "Run now",
                        }
                    ]
                },
            )
        row = session.get(VideoTranslationSegment, "seg_rewrite")
        assert row is not None
        assert row.translated_text == "Run now"
        assert row.preview_audio_url is None
        assert row.tts_duration_ms is None
        assert row.timing_fit_status == "pending"


def test_translation_render_payload_keeps_continuous_source_and_canonical_audio_mode():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from narrato_api.assets.models import Asset
    from narrato_api.auth.models import User
    from narrato_api.database import Base
    from narrato_api.projects.models import Project
    from narrato_api.products.video_translation import VideoTranslationSettings
    from narrato_api.workflows.models import (
        Workflow,
        WorkflowNode,
        WorkflowTemplateSnapshot,
    )
    from narrato_api.workflows.orchestrator import WorkflowOrchestrator

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    with sessions.begin() as session:
        session.add(
            User(id="usr_render", email="render@example.com", password_hash="hash")
        )
        session.add(
            Project(
                id="prj_render",
                user_id="usr_render",
                product=PRODUCT,
                status="render_queued",
                current_stage="generate",
            )
        )
        session.add(
            Asset(
                id="ast_render",
                user_id="usr_render",
                project_id="prj_render",
                asset_type="video",
                status="ready",
                filename="source.mp4",
                bucket="b",
                object_key="source.mp4",
                cdn_url="https://cdn.example/source.mp4",
                size_bytes=1,
                duration_seconds=12.5,
            )
        )
        session.add(
            VideoTranslationSettings(
                project_id="prj_render",
                settings={
                    "target_language": "en",
                    "voice_id": "voice-default",
                    "video_ratio": "original",
                    "original_sound_mode": "keep",
                    "translated_subtitle_region": {
                        "x": 0.1,
                        "y": 0.7,
                        "width": 0.8,
                        "height": 0.15,
                    },
                },
            )
        )
        session.add(
            VideoTranslationSegment(
                id="seg_render",
                project_id="prj_render",
                segment_index=0,
                start_ms=1000,
                end_ms=3000,
                source_text="你好",
                translated_text="hello",
                voice_id="voice-row",
                speed=1.1,
                volume=82,
                keep_original_sound=False,
                timing_fit_status="speed_adjusted",
                timing_overflow_ms=0,
                fitted_speed=1.1,
                tts_duration_ms=1900,
            )
        )
        session.add(
            WorkflowTemplateSnapshot(
                id="tpl_render",
                template_name=PRODUCT,
                version="v1",
                definition={"nodes": []},
            )
        )
        session.add(
            Workflow(
                id="wfl_render",
                user_id="usr_render",
                project_id="prj_render",
                template_snapshot_id="tpl_render",
                state="running",
            )
        )
        session.add(
            WorkflowNode(
                id="node_tts_render",
                workflow_id="wfl_render",
                name="tts",
                state="completed",
            )
        )
        session.add(
            WorkflowNode(
                id="node_video_render",
                workflow_id="wfl_render",
                name="video_render",
                state="queued",
                depends_on=["tts"],
            )
        )

    captured = {}

    class Core:
        def submit_video_render(self, **kwargs):
            captured.update(kwargs)
            return "core_render"

    assert WorkflowOrchestrator(sessions).dispatch_ready(
        workflow_id="wfl_render", core_client=Core()
    )
    assert captured["sources"] == [
        {
            "source_asset_id": "ast_render",
            "video_url": "https://cdn.example/source.mp4",
        }
    ]
    assert captured["render_config"]["render_mode"] == "video_translation"
    assert captured["render_config"]["translation_audio_mode"] == "voice_replacement"
    assert captured["render_config"]["video_ratio"] == "original"
    expected_timing = {
        "segment_id": "seg_render",
        "voice_id": "voice-row",
        "speed": 1.1,
        "volume": 82,
        "allowed_duration_ms": 11500,
        "timing_tolerance_ms": 200,
    }
    assert {
        key: captured["timeline"][0][key] for key in expected_timing
    } == expected_timing


def test_tts_overflow_callback_queues_render_without_rewriting_translation_text():
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import sessionmaker

    from narrato_api.auth.models import User
    from narrato_api.database import Base
    from narrato_api.projects.models import Project
    from narrato_api.products.video_translation import VideoTranslationSettings
    from narrato_api.workflows.models import (
        Workflow,
        WorkflowNode,
        WorkflowNodeAttempt,
        WorkflowOutbox,
        WorkflowTemplateSnapshot,
    )
    from narrato_api.workflows.reconciler import WorkflowReconciler

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    with sessions.begin() as session:
        session.add(
            User(
                id="usr_auto_rewrite",
                email="auto-rewrite@example.com",
                password_hash="hash",
            )
        )
        session.add(
            Project(
                id="prj_auto_rewrite",
                user_id="usr_auto_rewrite",
                product=PRODUCT,
                status="analyzing",
                current_stage="generate",
            )
        )
        session.add(
            VideoTranslationSettings(
                project_id="prj_auto_rewrite",
                settings={
                    "target_language": "en",
                    "voice_id": "v",
                    "execution_mode": "auto",
                },
            )
        )
        session.add(
            VideoTranslationSegment(
                id="seg_auto_rewrite",
                project_id="prj_auto_rewrite",
                segment_index=0,
                start_ms=0,
                end_ms=1000,
                source_text="快跑",
                translated_text="You need to run right now",
                voice_id="v",
                speed=1,
                volume=100,
                keep_original_sound=False,
            )
        )
        session.add(
            WorkflowTemplateSnapshot(
                id="tpl_auto_rewrite",
                template_name=PRODUCT,
                version="v1",
                definition={"nodes": []},
            )
        )
        session.add(
            Workflow(
                id="wfl_auto_rewrite",
                user_id="usr_auto_rewrite",
                project_id="prj_auto_rewrite",
                template_snapshot_id="tpl_auto_rewrite",
                state="running",
            )
        )
        session.add(
            WorkflowNode(
                id="node_rewrite_auto",
                workflow_id="wfl_auto_rewrite",
                name="subtitle_rewrite",
                state="completed",
                max_attempts=2,
            )
        )
        session.add(
            WorkflowNode(
                id="node_tts_auto",
                workflow_id="wfl_auto_rewrite",
                name="tts",
                state="running",
            )
        )
        session.add(
            WorkflowNode(
                id="node_render_auto",
                workflow_id="wfl_auto_rewrite",
                name="video_render",
                state="queued",
                manual_gate=True,
                depends_on=["tts"],
            )
        )
        session.add(
            WorkflowNodeAttempt(
                id="attempt_tts_auto",
                workflow_node_id="node_tts_auto",
                attempt_number=1,
                state="running",
                state_version=0,
                core_task_id="core_tts_auto",
            )
        )

    assert WorkflowReconciler(sessions).reconcile_callback(
        core_task_id="core_tts_auto",
        event_id="event_tts_auto",
        state_version=1,
        state="succeeded",
        result={
            "metadata": {
                "segment_timings": [
                    {
                        "segment_id": "seg_auto_rewrite",
                        "tts_duration_ms": 1700,
                        "timing_fit_status": "rewrite_required",
                        "timing_overflow_ms": 500,
                    }
                ]
            }
        },
    )
    with sessions() as session:
        project = session.get(Project, "prj_auto_rewrite")
        render = session.get(WorkflowNode, "node_render_auto")
        event = session.scalar(
            select(WorkflowOutbox).where(
                WorkflowOutbox.workflow_node_id == "node_render_auto"
            )
        )
    assert project is not None and (project.current_stage, project.status) == (
        "generate",
        "render_queued",
    )
    assert render is not None and (render.state, render.manual_gate) == (
        "queued",
        False,
    )
    assert event is not None


def test_preview_caller_task_id_is_stable_and_within_core_limit():
    value = _preview_caller_task_id("p" * 40, "s" * 40, "k" * 64)
    assert value.startswith("translation-preview:")
    assert len(value) <= 80


def test_preview_task_uses_core_tts_contract(monkeypatch):
    from narrato_api.integrations.core_client import HttpCoreClient

    calls = {}

    def fake_submit(self, path, body, key):
        calls.update(path=path, body=body, key=key)
        return "core_preview_1"

    monkeypatch.setattr(HttpCoreClient, "_submit_task", fake_submit)
    result = HttpCoreClient(
        base_url="http://core", request_token="token"
    ).submit_tts_preview(
        voice_id="voice-1",
        language="en",
        text="hello",
        speed=1.1,
        volume=80,
        caller_task_id="translation-preview:p:s:k",
    )
    assert result == "core_preview_1"
    assert calls["path"] == "/api/v1/tts/tasks"
    assert calls["body"]["segments"] == [{"text": "hello", "start": 0, "end": 60}]
    assert calls["body"] == {
        "voice_id": "voice-1",
        "language": "en",
        "output_format": "wav",
        "sample_rate": 16000,
        "speed": 1.1,
        "volume": 80,
        "segments": [{"text": "hello", "start": 0, "end": 60}],
        "caller_task_id": "translation-preview:p:s:k",
    }
    # Core TTS 拒绝任何未知字段；speed/volume 是其明确的顶层契约字段。
    assert "translation_preview" not in calls["body"]
    assert calls["key"] == "translation-preview:p:s:k"


def test_translation_rewrite_uses_dedicated_core_contract(monkeypatch):
    from narrato_api.integrations.core_client import HttpCoreClient

    calls = {}

    def fake_submit(self, path, body, key):
        calls.update(path=path, body=body, key=key)
        return "core_rewrite_1"

    monkeypatch.setattr(HttpCoreClient, "_submit_task", fake_submit)
    result = HttpCoreClient(
        base_url="http://core", request_token="token"
    ).submit_translation_rewrite(
        model_id="model_qwen_plus",
        target_language="en",
        segments=[
            {
                "segment_id": "seg-1",
                "segment_index": 0,
                "source_text": "快跑",
                "translated_text": "You need to run right now",
                "allowed_duration_ms": 900,
                "max_words": 3,
            }
        ],
        caller_task_id="attempt-rewrite",
    )
    assert result == "core_rewrite_1"
    assert calls == {
        "path": "/api/v1/video-translation/rewrite-tasks",
        "body": {
            "model_id": "model_qwen_plus",
            "target_language": "en",
            "segments": [
                {
                    "segment_id": "seg-1",
                    "segment_index": 0,
                    "source_text": "快跑",
                    "translated_text": "You need to run right now",
                    "allowed_duration_ms": 900,
                    "max_words": 3,
                }
            ],
            "caller_task_id": "attempt-rewrite",
        },
        "key": "attempt-rewrite",
    }


def test_manual_translation_keeps_tts_and_render_behind_confirmation_gate():
    """手动项目不能在译文审核前抢跑任何配音或渲染节点。"""
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session

    from narrato_api.assets.models import Asset
    from narrato_api.auth.models import User
    from narrato_api.billing.models import CreditAccount, CreditLedger, ProductPrice
    from narrato_api.database import Base
    from narrato_api.projects.models import Project
    from narrato_api.products.video_translation import (
        VideoTranslationCharge,
        VideoTranslationSettings,
        _start_translation,
        _translation_cost_data,
    )
    from narrato_api.workflows.models import WorkflowNode, WorkflowTemplateSnapshot

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        with session.begin():
            session.add(
                User(
                    id="usr_translation",
                    email="translation@example.com",
                    password_hash="hash",
                )
            )
            session.add(
                Project(
                    id="prj_translation", user_id="usr_translation", product=PRODUCT
                )
            )
            session.add(CreditAccount(user_id="usr_translation", balance=100))
            session.add(ProductPrice(product=PRODUCT, version=2, credits_per_minute=30))
            session.add(
                Asset(
                    id="ast_translation",
                    user_id="usr_translation",
                    project_id="prj_translation",
                    asset_type="video",
                    status="ready",
                    filename="source.mp4",
                    bucket="assets",
                    object_key="source.mp4",
                    cdn_url="https://cdn.example/source.mp4",
                    size_bytes=1,
                    duration_seconds=61,
                )
            )
            session.add(
                VideoTranslationSettings(
                    project_id="prj_translation",
                    settings={
                        "target_language": "en",
                        "voice_id": "voice-1",
                        "execution_mode": "manual",
                    },
                )
            )
            session.add(
                WorkflowTemplateSnapshot(
                    id="tpl_translation",
                    template_name=PRODUCT,
                    version="v1",
                    definition={"nodes": []},
                )
            )
            workflow_id = _start_translation(
                session, user_id="usr_translation", project_id="prj_translation"
            )
        nodes = {
            node.name: node
            for node in session.scalars(
                select(WorkflowNode).where(WorkflowNode.workflow_id == workflow_id)
            )
        }
        assert nodes["tts"].manual_gate is True
        assert nodes["video_render"].manual_gate is True
        charge = session.scalar(
            select(CreditLedger).where(CreditLedger.reference_id == "prj_translation")
        )
        assert charge is not None and charge.amount == -80
        frozen = session.get(VideoTranslationCharge, "prj_translation")
        assert frozen is not None
        assert (
            frozen.total_source_seconds,
            frozen.billed_minutes,
            frozen.base_credits,
            frozen.voice_replacement_credits,
            frozen.total_credits,
            frozen.original_sound_mode,
        ) == (61, 2, 60, 20, 80, "voice_replacement")
        # 价格表和可编辑设置即使被后续更新，已开始的工作流也只能读取它的
        # 冻结值，避免重试、项目列表或退款引用了新的价格。
        updated_price = session.scalar(
            select(ProductPrice).where(ProductPrice.product == PRODUCT)
        )
        assert updated_price is not None
        updated_price.credits_per_minute = 99
        project = session.get(Project, "prj_translation")
        assert project is not None
        data = _translation_cost_data(
            session,
            project=project,
            setting=TranslationSettings(original_sound_mode="translated_voice_only"),
        )
        assert data.credits == 80 and data.original_sound_mode == "voice_replacement"


def test_translation_quote_rejects_multiple_source_videos_before_charge():
    import pytest
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from narrato_api.api.errors import ApiError
    from narrato_api.assets.models import Asset
    from narrato_api.auth.models import User
    from narrato_api.database import Base
    from narrato_api.projects.models import Project
    from narrato_api.products.video_translation import _translation_cost_data

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        with session.begin():
            session.add(
                User(id="usr_multi", email="multi@example.com", password_hash="hash")
            )
            session.add(Project(id="prj_multi", user_id="usr_multi", product=PRODUCT))
            for index in range(2):
                session.add(
                    Asset(
                        id=f"ast_multi_{index}",
                        user_id="usr_multi",
                        project_id="prj_multi",
                        asset_type="video",
                        status="ready",
                        filename=f"source-{index}.mp4",
                        bucket="assets",
                        object_key=f"source-{index}.mp4",
                        cdn_url=f"https://cdn.example/source-{index}.mp4",
                        size_bytes=1,
                        sort_order=index,
                        duration_seconds=30,
                    )
                )
        project = session.get(Project, "prj_multi")
        assert project is not None
        with pytest.raises(ApiError) as error:
            _translation_cost_data(
                session,
                project=project,
                setting=TranslationSettings(),
            )

    assert error.value.code == "PROJECT_VIDEO_COUNT_INVALID"


def test_explicit_retry_rejects_duplicate_request_without_second_charge():
    from types import SimpleNamespace

    import pytest
    from sqlalchemy import create_engine, func, select
    from sqlalchemy.orm import Session

    from narrato_api.api.errors import ApiError
    from narrato_api.auth.models import User
    from narrato_api.billing.models import CreditAccount, CreditLedger
    from narrato_api.database import Base
    from narrato_api.projects.models import Project
    from narrato_api.products.video_translation import (
        RetryRequest,
        VideoTranslationCharge,
        render_translation,
        retry_translation,
    )
    from narrato_api.workflows.models import (
        Workflow,
        WorkflowNode,
        WorkflowNodeAttempt,
        WorkflowOutbox,
        WorkflowTemplateSnapshot,
    )

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        with session.begin():
            session.add(
                User(id="usr_retry", email="retry@example.com", password_hash="hash")
            )
            session.add(
                Project(
                    id="prj_retry",
                    user_id="usr_retry",
                    product=PRODUCT,
                    status="failed",
                    current_stage="generate",
                )
            )
            session.add(CreditAccount(user_id="usr_retry", balance=200))
            session.add(
                WorkflowTemplateSnapshot(
                    id="tpl_retry",
                    template_name=PRODUCT,
                    version="v1",
                    definition={"nodes": []},
                )
            )
            session.add(
                Workflow(
                    id="wfl_retry",
                    user_id="usr_retry",
                    project_id="prj_retry",
                    template_snapshot_id="tpl_retry",
                    state="failed",
                    state_version=7,
                )
            )
            session.add(
                WorkflowNode(
                    id="node_tts_retry",
                    workflow_id="wfl_retry",
                    name="tts",
                    state="completed",
                )
            )
            session.add(
                WorkflowNode(
                    id="node_retry",
                    workflow_id="wfl_retry",
                    name="video_render",
                    state="failed",
                )
            )
            session.add(
                WorkflowNode(
                    id="node_publish_retry",
                    workflow_id="wfl_retry",
                    name="publish_artifacts",
                    state="cancelled",
                )
            )
            session.add(
                WorkflowNodeAttempt(
                    id="attempt_retry",
                    workflow_node_id="node_retry",
                    attempt_number=1,
                    state="failed",
                    state_version=7,
                    core_task_id="core_retry",
                )
            )
            session.add(
                VideoTranslationCharge(
                    project_id="prj_retry",
                    workflow_id="wfl_retry",
                    price_version=2,
                    total_source_seconds=61,
                    billed_minutes=2,
                    base_credits_per_minute=30,
                    original_sound_mode="voice_replacement",
                    voice_replacement_credits_per_minute=10,
                    base_credits=60,
                    voice_replacement_credits=20,
                    total_credits=80,
                )
            )
            initial_charge = CreditLedger(
                user_id="usr_retry",
                entry_type="charge",
                amount=-80,
                idempotency_key="charge:prj_retry",
                reference_id="prj_retry",
                reason="video_translation_charge",
            )
            session.add(initial_charge)
            session.flush()
            session.add(
                CreditLedger(
                    user_id="usr_retry",
                    entry_type="refund",
                    amount=80,
                    idempotency_key=f"refund:prj_retry:{initial_charge.id}",
                    reference_id="prj_retry",
                    reason="project_failed_refund",
                )
            )

    class Auth:
        @staticmethod
        def resolve_user(_token):
            return SimpleNamespace(id="usr_retry")

    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(database_engine=engine))
    )
    body = RetryRequest(restart_from="video_render")

    # Render 页刷新会再次 POST /render；失败退款后该入口不能绕开付费重试。
    with pytest.raises(ApiError) as render_error:
        render_translation("prj_retry", request, "token", Auth(), "render-request")
    assert render_error.value.code == "PROJECT_RETRY_REQUIRED"

    first = retry_translation("prj_retry", body, request, "token", Auth(), "request-1")
    assert first.data is not None and first.data.resumed_from_node == "video_render"

    with pytest.raises(ApiError) as error:
        retry_translation("prj_retry", body, request, "token", Auth(), "request-2")
    assert error.value.code == "PROJECT_NOT_RETRYABLE"

    with Session(engine) as session:
        charges = session.scalars(
            select(CreditLedger)
            .where(
                CreditLedger.reference_id == "prj_retry",
                CreditLedger.reason == "video_translation_charge",
            )
            .order_by(CreditLedger.id)
        ).all()
        account = session.get(CreditAccount, "usr_retry")
        outbox_count = session.scalar(select(func.count()).select_from(WorkflowOutbox))
    assert [charge.amount for charge in charges] == [-80, -80]
    assert account is not None and account.balance == 120
    assert outbox_count == 1
