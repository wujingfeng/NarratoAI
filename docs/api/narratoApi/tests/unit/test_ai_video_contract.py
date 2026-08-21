from __future__ import annotations

from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from narrato_api.assets.models import Asset
from narrato_api.auth.models import User
from narrato_api.database import Base
from narrato_api.products.ai_video import _locked_prices, _model_summary, _public_model, _task_data, _text_units, _validate_input, list_tasks
from narrato_api.products.model_generation import (
    Model,
    ModelPlayMode,
    ModelPlayModeProvider,
    ModelPlayModeProviderPrice,
    ModelPlayModeRule,
    ModelTask,
)
from narrato_api.projects.models import Project


def _seed(session: Session, *, model_type: str = "video") -> tuple[Model, ModelPlayMode]:
    model = Model(id=f"model_{model_type}", display_name="Test model", model_type=model_type, is_default=True)
    mode = ModelPlayMode(id=f"mode_{model_type}", model_id=model.id, code="reference", display_name="Reference", active_provider_id=f"provider_{model_type}", default_credits=11, supports_generate_audio=model_type == "video")
    provider = ModelPlayModeProvider(id=f"provider_{model_type}", play_mode_id=mode.id, provider_code="volcengine", provider_model_id="endpoint", submit_url="https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks" if model_type == "video" else "https://ark.cn-beijing.volces.com/api/v3/images/generations", status_query_url="https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks/{task_id}" if model_type == "video" else None, api_key="test")
    session.add_all([model, mode, provider])
    for kind, required, count in (("text", False, None), ("image", False, 30), ("video", False, 10), ("audio", False, 10)):
        session.add(ModelPlayModeRule(id=f"rule_{model_type}_{kind}", play_mode_id=mode.id, rule_kind="input_constraint", input_type=kind, is_supported=True, is_required=required, max_count=count, max_text_units=1000 if kind == "text" else None, max_file_size_bytes=30 * 1024 * 1024 if kind == "image" else None, max_duration_seconds=30 if kind in {"video", "audio"} else None, supports_mention=kind == "image"))
    session.add_all([
        ModelPlayModeRule(id=f"rule_{model_type}_resolution", play_mode_id=mode.id, rule_kind="output_option", output_option_type="resolution", resolution=["480p", "720p"], sort_order=2),
        ModelPlayModeRule(id=f"rule_{model_type}_ratio", play_mode_id=mode.id, rule_kind="output_option", output_option_type="ratio", ratio=["adaptive", "16:9"], sort_order=2),
        ModelPlayModeRule(id=f"rule_{model_type}_duration", play_mode_id=mode.id, rule_kind="output_option", output_option_type="duration", duration_seconds=["4", "5", "30"], sort_order=2),
        ModelPlayModeProviderPrice(
            id=f"price_{model_type}",
            provider_id=provider.id,
            billing_unit="second" if model_type == "video" else "usage",
            per_second_credits=2 if model_type == "video" else None,
            per_usage_credits=4 if model_type == "image" else None,
        ),
    ])
    return model, mode


def test_normalized_model_schema_has_no_config_json_columns() -> None:
    assert "provider_config" not in Model.__table__.c
    assert "capabilities" not in Model.__table__.c
    assert "price_config" not in Model.__table__.c
    assert "provider_request" in __import__("narrato_api.products.model_generation", fromlist=["ModelTask"]).ModelTask.__table__.c


def test_model_catalog_is_derived_from_rules_without_leaking_api_key() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        model, _mode = _seed(session)
        session.commit()
        public = _public_model(session, model)
    assert public.capabilities["image_upload"] == {"enabled": True, "max_count": 30}
    assert public.capabilities["duration"]["options"] == ["4", "5", "30"]
    assert next(item for item in public.play_modes[0].output_options if item.type == "resolution").values == ["480p", "720p"]
    assert "test" not in public.model_dump_json()


def test_model_catalog_summary_excludes_play_modes_rules_and_pricing() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        model, _mode = _seed(session)
        session.commit()
        summary = _model_summary(session, model)
    assert summary.display_name == "Test model"
    assert "play_modes" not in summary.model_dump()
    assert "capabilities" not in summary.model_dump()
    assert "price" not in summary.model_dump()


def test_task_data_uses_display_model_name() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(User(id="usr", email="user@example.test", password_hash="hash"))
        model, mode = _seed(session)
        task = ModelTask(
            id="task_1",
            user_id="usr",
            model_id=model.id,
            play_mode_id=mode.id,
            provider_id=mode.active_provider_id,
            task_type="video",
            status="queued",
            idempotency_key="task-key",
        )
        session.add(task)
        session.commit()
        data = _task_data(session, task)
    assert data.model_name == "Test model"


def test_task_list_defaults_to_thirty_items_and_reports_next_page() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        user = User(id="usr", email="user@example.test", password_hash="hash")
        session.add(user)
        model, mode = _seed(session)
        session.add_all([
            ModelTask(
                id=f"task_{index:02d}",
                user_id=user.id,
                model_id=model.id,
                play_mode_id=mode.id,
                provider_id=mode.active_provider_id,
                task_type="video",
                status="queued",
                idempotency_key=f"page-key-{index}",
            )
            for index in range(31)
        ])
        session.commit()

    class Auth:
        def resolve_user(self, _token: str) -> SimpleNamespace:
            return SimpleNamespace(id="usr")

    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(database_engine=engine)))
    first = list_tasks(request, "token", Auth(), "request-1", created_from=None, created_to=None, type=None, view="list", page=1, page_size=30)
    second = list_tasks(request, "token", Auth(), "request-2", created_from=None, created_to=None, type=None, view="list", page=2, page_size=30)

    assert len(first.data.items) == 30
    assert first.data.page == 1
    assert first.data.page_size == 30
    assert first.data.total == 31
    assert first.data.has_next is True
    assert len(second.data.items) == 1
    assert second.data.page == 2
    assert second.data.has_next is False


def test_mixed_chinese_characters_and_english_words_share_prompt_limit() -> None:
    assert _text_units("你好 world again") == 4


def test_rules_validate_ready_assets_and_default_first_output_options() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(User(id="usr", email="user@example.test", password_hash="hash"))
        session.add(Project(id="prj", user_id="usr", product="ai_video"))
        model, mode = _seed(session)
        session.add(Asset(id="image", user_id="usr", project_id="prj", asset_type="image", status="ready", filename="image.png", bucket="bucket", object_key="image.png", cdn_url="https://cdn.example/image.png", size_bytes=1024))
        session.commit()
        result = _validate_input(session=session, user_id="usr", project_id="prj", model=model, mode=mode, prompt="你好 world", image_asset_ids=["image"], video_asset_ids=[], audio_asset_ids=[], resolution=None, ratio=None, duration_seconds=5, audio_enabled=True, mentioned_ids=["image"])
    assert result.resolution == "480p"
    assert result.ratio == "adaptive"
    assert result.duration_seconds == 5
    assert result.mentioned_ids == {"image"}


def test_output_option_casing_is_canonical_at_api_and_submission_boundaries() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(User(id="usr", email="user@example.test", password_hash="hash"))
        session.add(Project(id="prj", user_id="usr", product="ai_video"))
        model, mode = _seed(session)
        resolution_rule = session.get(ModelPlayModeRule, "rule_video_resolution")
        ratio_rule = session.get(ModelPlayModeRule, "rule_video_ratio")
        assert resolution_rule is not None and ratio_rule is not None
        resolution_rule.resolution = ["480P", "4K"]
        ratio_rule.ratio = ["ADAPTIVE", "16:9"]
        session.commit()

        public = _public_model(session, model)
        result = _validate_input(
            session=session,
            user_id="usr",
            project_id="prj",
            model=model,
            mode=mode,
            prompt="你好",
            image_asset_ids=[],
            video_asset_ids=[],
            audio_asset_ids=[],
            resolution="480p",
            ratio="adaptive",
            duration_seconds=5,
            audio_enabled=False,
            mentioned_ids=[],
        )

    resolution_values = next(item.values for item in public.play_modes[0].output_options if item.type == "resolution")
    ratio_values = next(item.values for item in public.play_modes[0].output_options if item.type == "ratio")
    assert resolution_values == ["480p", "4k"]
    assert ratio_values == ["adaptive", "16:9"]
    assert result.resolution == "480p"
    assert result.ratio == "adaptive"


def test_price_lookup_tolerates_legacy_resolution_casing() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        _model, mode = _seed(session)
        price = session.get(ModelPlayModeProviderPrice, "price_video")
        assert price is not None
        price.resolution = "480P"
        session.commit()
        provider = session.get(ModelPlayModeProvider, mode.active_provider_id)
        assert provider is not None
        prices = _locked_prices(session, provider, "480p")
    assert [price.id for price in prices] == ["price_video"]


def test_seedance_reference_prompt_uses_frozen_type_order_and_mapping_text() -> None:
    from types import SimpleNamespace

    from narrato_api.products.ai_video import ReferenceMappingData, _compile_reference_prompt

    images = [
        Asset(id="img_a", user_id="usr", project_id="prj", asset_type="image", status="ready", filename="a.png", bucket="bucket", object_key="a.png", cdn_url="https://cdn.example/a.png", size_bytes=1),
        Asset(id="img_b", user_id="usr", project_id="prj", asset_type="image", status="ready", filename="b.png", bucket="bucket", object_key="b.png", cdn_url="https://cdn.example/b.png", size_bytes=1),
    ]
    videos = [Asset(id="vid_a", user_id="usr", project_id="prj", asset_type="video", status="ready", filename="motion.mp4", bucket="bucket", object_key="motion.mp4", cdn_url="https://cdn.example/motion.mp4", size_bytes=1)]
    audios = [Asset(id="aud_a", user_id="usr", project_id="prj", asset_type="audio", status="ready", filename="voice.mp3", bucket="bucket", object_key="voice.mp3", cdn_url="https://cdn.example/voice.mp3", size_bytes=1)]
    prompt, mentioned = _compile_reference_prompt(
        prompt="让 {{asset:img_a}} 按 {{asset:vid_a}} 的动作奔跑，并使用 {{asset:aud_a}} 的音色。",
        assets={"image": images, "video": videos, "audio": audios},
        rules={kind: SimpleNamespace(supports_mention=True) for kind in ("image", "video", "audio")},
        mappings=[
            ReferenceMappingData(asset_id="img_a", description="主体A「张三」的外观参考。"),
            ReferenceMappingData(asset_id="img_b", description="主体B「李四」的外观参考。"),
            ReferenceMappingData(asset_id="vid_a", description="参考主体A的跑步动作，不参考人物外观。"),
            ReferenceMappingData(asset_id="aud_a", description="主体A的音色和台词参考。"),
        ],
        legacy_mentioned_ids=[],
    )

    assert prompt == (
        "【参考素材映射】\n"
        "@image1（图1）：主体A「张三」的外观参考。\n"
        "@image2（图2）：主体B「李四」的外观参考。\n"
        "@video1（视频1）：参考主体A的跑步动作，不参考人物外观。\n"
        "@audio1（音频1）：主体A的音色和台词参考。\n\n"
        "【创作指令】\n"
        "让 @image1 按 @video1 的动作奔跑，并使用 @audio1 的音色。"
    )
    assert mentioned == {"img_a", "img_b", "vid_a", "aud_a"}


def test_seedance_reference_prompt_automatically_supplements_mapping_from_media_and_context() -> None:
    from types import SimpleNamespace

    from narrato_api.products.ai_video import _compile_reference_prompt

    image = Asset(id="img", user_id="usr", project_id="prj", asset_type="image", status="ready", filename="person.png", bucket="bucket", object_key="person.png", cdn_url="https://cdn.example/person.png", size_bytes=1)
    video = Asset(id="vid", user_id="usr", project_id="prj", asset_type="video", status="ready", filename="camera.mp4", bucket="bucket", object_key="camera.mp4", cdn_url="https://cdn.example/camera.mp4", size_bytes=1)
    prompt, mentioned = _compile_reference_prompt(
        prompt="让 {{asset:img}} 入画，镜头运镜参考 {{asset:vid}}。",
        assets={"image": [image], "video": [video], "audio": []},
        rules={kind: SimpleNamespace(supports_mention=True) for kind in ("image", "video", "audio")},
        mappings=[],
        legacy_mentioned_ids=[],
    )

    assert prompt is not None
    assert "@image1（图1）：作为主体外观、角色一致性或场景风格参考，以创作指令为准。" in prompt
    assert "@video1（视频1）：作为镜头运动、机位与运镜节奏参考。" in prompt
    assert "让 @image1 入画，镜头运镜参考 @video1。" in prompt
    assert mentioned == {"img", "vid"}
