from __future__ import annotations

import json
import logging
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from core_api.api.errors import ApiError
from core_api.capabilities.models import CoreModel, CoreProvider, CoreVoice
from core_api.capabilities.seed import (
    ModelSeed,
    ProviderSeed,
    VoiceSeed,
    seed_capabilities,
)
from core_api.capabilities.service import CapabilityService
from core_api.database import Base, create_database_engine, get_engine
from core_api.logging import configure_logging


CATALOG_SEEDS = (
    ProviderSeed(
        code="alpha",
        name="甲供应商",
        secret_ref="alpha_key",
        settings={"internal_region": "cn-test"},
        models=(
            ModelSeed(
                provider_model_code="alpha-raw-model",
                name="甲大模型",
                capability_types=("llm",),
                languages=("zh-CN",),
                limits={"max_input_chars": 4000},
            ),
            ModelSeed(
                provider_model_code="alpha-disabled-model",
                name="停用模型",
                capability_types=("llm",),
                languages=("zh-CN",),
                enabled=False,
            ),
        ),
        voices=(
            VoiceSeed(
                provider_voice_code="alpha-raw-voice",
                name="温柔女声",
                languages=("zh-CN",),
                gender="female",
                styles=("gentle",),
                sample_url="https://cdn.example.test/alpha.mp3",
                supported_formats=("mp3", "wav"),
                supported_sample_rates=(24000, 48000),
            ),
            VoiceSeed(
                provider_voice_code="alpha-disabled-voice",
                name="停用音色",
                languages=("zh-CN",),
                supported_formats=("mp3",),
                supported_sample_rates=(24000,),
                enabled=False,
            ),
        ),
    ),
    ProviderSeed(
        code="beta",
        name="乙供应商",
        secret_ref="beta_key",
        models=(
            ModelSeed(
                provider_model_code="beta-raw-model",
                name="乙大模型",
                capability_types=("analysis", "llm"),
                languages=("en-US", "zh-CN"),
            ),
        ),
        voices=(
            VoiceSeed(
                provider_voice_code="beta-raw-voice",
                name="清朗男声",
                languages=("en-US", "zh-CN"),
                gender="male",
                styles=("news",),
                sample_url=None,
                supported_formats=("wav",),
                supported_sample_rates=(48000,),
            ),
        ),
    ),
    ProviderSeed(
        code="disabled",
        name="停用供应商",
        secret_ref="disabled_key",
        enabled=False,
        voices=(
            VoiceSeed(
                provider_voice_code="disabled-raw-voice",
                name="不可见音色",
                languages=("zh-CN",),
                supported_formats=("mp3",),
                supported_sample_rates=(24000,),
            ),
        ),
    ),
    ProviderSeed(
        code="missing",
        name="缺失密钥供应商",
        secret_ref="missing_key",
        models=(
            ModelSeed(
                provider_model_code="missing-raw-model",
                name="不可见模型",
                capability_types=("llm",),
                languages=("zh-CN",),
            ),
        ),
    ),
    ProviderSeed(
        code="empty",
        name="空密钥供应商",
        secret_ref="empty_key",
        voices=(
            VoiceSeed(
                provider_voice_code="empty-raw-voice",
                name="不可见空密钥音色",
                languages=("zh-CN",),
                supported_formats=("mp3",),
                supported_sample_rates=(24000,),
            ),
        ),
    ),
)


@pytest.fixture
def catalog_settings(settings):
    """提供只包含可调用测试供应商的密钥注册表。"""

    return settings.model_copy(
        update={
            "provider_secrets": {
                "alpha_key": "alpha-real-secret",
                "beta_key": "beta-real-secret",
                "disabled_key": "disabled-real-secret",
                "empty_key": "   ",
            }
        }
    )


@pytest.fixture
def catalog_session(catalog_settings):
    """创建 HTTP 路由和服务测试共用的文件数据库。"""

    engine = get_engine(catalog_settings)
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as database_session:
        seed_capabilities(database_session, CATALOG_SEEDS)
        database_session.commit()
        yield database_session
    Base.metadata.drop_all(engine)


@pytest.fixture
def catalog_client(app, catalog_settings, catalog_session):
    """让应用通过真实数据库依赖读取能力目录。"""

    from core_api.api.dependencies import get_settings

    app.state.settings = catalog_settings
    app.dependency_overrides[get_settings] = lambda: catalog_settings
    from fastapi.testclient import TestClient

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def auth_header(catalog_settings):
    """返回 Core 固定 Bearer 认证 Header。"""

    return {"Authorization": f"Bearer {catalog_settings.service_token}"}


def test_voice_catalog_has_same_shape_for_all_providers(catalog_client, auth_header):
    items = catalog_client.get("/api/v1/capabilities", headers=auth_header).json()[
        "data"
    ]["voices"]
    expected = {
        "voice_id",
        "provider_code",
        "name",
        "languages",
        "gender",
        "styles",
        "sample_url",
        "supported_formats",
        "supported_sample_rates",
    }
    assert items and all(set(item) == expected for item in items)
    assert {item["provider_code"] for item in items} == {"alpha", "beta"}


@pytest.mark.parametrize(
    "headers",
    [{}, {"Authorization": "Bearer wrong"}, {"Authorization": "Basic wrong"}],
)
def test_catalog_requires_fixed_bearer(catalog_client, headers):
    response = catalog_client.get("/api/v1/capabilities", headers=headers)
    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHORIZED"


def test_catalog_hides_disabled_and_unresolved_capabilities(
    catalog_client, auth_header
):
    response = catalog_client.get("/api/v1/capabilities", headers=auth_header)
    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == {"code", "message", "data", "request_id"}
    data = payload["data"]
    assert set(data) == {"version", "providers", "models", "voices"}
    assert [item["provider_code"] for item in data["providers"]] == ["alpha", "beta"]
    assert [item["name"] for item in data["models"]] == ["甲大模型", "乙大模型"]
    assert [item["name"] for item in data["voices"]] == ["温柔女声", "清朗男声"]

    serialized = json.dumps(data, ensure_ascii=False, sort_keys=True)
    for forbidden in (
        "secret_ref",
        "provider_model_code",
        "provider_voice_code",
        "alpha-raw-model",
        "alpha-raw-voice",
        "alpha-real-secret",
        "beta-real-secret",
        "internal_region",
    ):
        assert forbidden not in serialized


def test_model_catalog_uses_normalized_shape(catalog_client, auth_header):
    items = catalog_client.get("/api/v1/capabilities", headers=auth_header).json()[
        "data"
    ]["models"]
    assert items and all(
        set(item)
        == {
            "model_id",
            "provider_code",
            "name",
            "capability_types",
            "languages",
            "limits",
        }
        for item in items
    )
    assert all(item["model_id"].startswith("model_") for item in items)


def test_require_capability_never_falls_back(catalog_session, catalog_settings):
    service = CapabilityService(catalog_session, catalog_settings.provider_secrets)
    visible_model = catalog_session.scalar(
        select(CoreModel).where(CoreModel.provider_model_code == "alpha-raw-model")
    )
    visible_voice = catalog_session.scalar(
        select(CoreVoice).where(CoreVoice.provider_voice_code == "alpha-raw-voice")
    )
    assert service.require_model(visible_model.id, "llm").id == visible_model.id
    assert (
        service.require_voice(
            visible_voice.id, language="zh-CN", output_format="wav", sample_rate=48000
        ).id
        == visible_voice.id
    )

    disabled_model = catalog_session.scalar(
        select(CoreModel).where(CoreModel.provider_model_code == "alpha-disabled-model")
    )
    disabled_voice = catalog_session.scalar(
        select(CoreVoice).where(CoreVoice.provider_voice_code == "alpha-disabled-voice")
    )
    failing_calls = (
        lambda: service.require_model("model_unknown"),
        lambda: service.require_model(disabled_model.id),
        lambda: service.require_model(visible_model.id, "tts"),
        lambda: service.require_voice("voice_unknown"),
        lambda: service.require_voice(disabled_voice.id),
        lambda: service.require_voice(visible_voice.id, language="en-US"),
        lambda: service.require_voice(visible_voice.id, output_format="aac"),
        lambda: service.require_voice(visible_voice.id, sample_rate=44100),
    )
    for call in failing_calls:
        with pytest.raises(ApiError) as captured:
            call()
        assert captured.value.code == "CAPABILITY_UNAVAILABLE"


def test_seed_is_idempotent_updates_config_and_preserves_operator_disable(session):
    initial = ProviderSeed(
        code="seed-provider",
        name="初始名称",
        secret_ref="seed-key",
        models=(
            ModelSeed(
                provider_model_code="raw-model",
                name="初始模型",
                capability_types=("llm",),
                languages=("zh-CN",),
            ),
        ),
        voices=(
            VoiceSeed(
                provider_voice_code="raw-voice",
                name="初始音色",
                languages=("zh-CN",),
                supported_formats=("mp3",),
                supported_sample_rates=(24000,),
            ),
        ),
    )
    seed_capabilities(session, (initial,))
    provider = session.scalar(
        select(CoreProvider).where(CoreProvider.code == "seed-provider")
    )
    model = session.scalar(select(CoreModel))
    voice = session.scalar(select(CoreVoice))
    original_ids = (provider.id, model.id, voice.id)
    provider.enabled = model.enabled = voice.enabled = False
    session.commit()

    updated = ProviderSeed(
        code="seed-provider",
        name="更新名称",
        secret_ref="seed-key-v2",
        models=(
            ModelSeed(
                provider_model_code="raw-model",
                name="更新模型",
                capability_types=("analysis", "llm"),
                languages=("en-US", "zh-CN"),
            ),
        ),
        voices=(
            VoiceSeed(
                provider_voice_code="raw-voice",
                name="更新音色",
                languages=("zh-CN",),
                supported_formats=("mp3", "wav"),
                supported_sample_rates=(24000, 48000),
            ),
        ),
    )
    seed_capabilities(session, (updated,))
    seed_capabilities(session, (updated,))

    provider = session.scalar(
        select(CoreProvider).where(CoreProvider.code == "seed-provider")
    )
    model = session.scalar(select(CoreModel))
    voice = session.scalar(select(CoreVoice))
    assert (provider.id, model.id, voice.id) == original_ids
    assert (provider.name, model.name, voice.name) == (
        "更新名称",
        "更新模型",
        "更新音色",
    )
    assert provider.secret_ref == "seed-key-v2"
    assert provider.enabled is model.enabled is voice.enabled is False
    assert session.scalar(select(func.count()).select_from(CoreProvider)) == 1
    assert session.scalar(select(func.count()).select_from(CoreModel)) == 1
    assert session.scalar(select(func.count()).select_from(CoreVoice)) == 1


def test_catalog_version_is_stable_and_excludes_secret_value(
    catalog_session, catalog_settings
):
    first = CapabilityService(
        catalog_session, catalog_settings.provider_secrets
    ).catalog()
    second = CapabilityService(
        catalog_session,
        {**catalog_settings.provider_secrets, "alpha_key": "rotated-secret-value"},
    ).catalog()
    assert first.version == second.version
    assert "alpha-real-secret" not in json.dumps(first.model_dump())
    assert "rotated-secret-value" not in first.version

    voice = catalog_session.scalar(
        select(CoreVoice).where(CoreVoice.provider_voice_code == "alpha-raw-voice")
    )
    voice.name = "温柔女声新版"
    catalog_session.commit()
    changed = CapabilityService(
        catalog_session, catalog_settings.provider_secrets
    ).catalog()
    assert changed.version != first.version


def test_unresolved_provider_ids_are_unavailable(catalog_session, catalog_settings):
    service = CapabilityService(catalog_session, catalog_settings.provider_secrets)
    missing_model = catalog_session.scalar(
        select(CoreModel).where(CoreModel.provider_model_code == "missing-raw-model")
    )
    with pytest.raises(ApiError) as captured:
        service.require_model(missing_model.id)
    assert captured.value.code == "CAPABILITY_UNAVAILABLE"


def test_provider_secret_registry_values_are_redacted_from_logs(
    catalog_settings, capsys
):
    configure_logging(catalog_settings)
    logging.getLogger("capability-test").warning(
        "provider failed with value %s", "alpha-real-secret"
    )
    assert "alpha-real-secret" not in capsys.readouterr().err


def test_sqlite_engine_enforces_capability_foreign_keys(tmp_path):
    engine = create_database_engine(f"sqlite:///{tmp_path / 'fk.db'}")
    Base.metadata.create_all(engine)
    with engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1
    engine.dispose()
    with engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1

    with Session(engine) as database_session:
        database_session.add(
            CoreModel(
                id="model_orphan",
                provider_id="provider_missing",
                provider_model_code="orphan-raw-model",
                name="孤儿模型",
                capability_types=["llm"],
                languages=["zh-CN"],
                limits={},
                enabled=True,
            )
        )
        with pytest.raises(IntegrityError):
            database_session.commit()


def test_catalog_safely_handles_legacy_orphan_capabilities():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as database_session:
        orphan_model = CoreModel(
            id="model_orphan_legacy",
            provider_id="provider_missing",
            provider_model_code="orphan-raw-model",
            name="孤儿模型",
            capability_types=["llm"],
            languages=["zh-CN"],
            limits={},
            enabled=True,
        )
        orphan_voice = CoreVoice(
            id="voice_orphan_legacy",
            provider_id="provider_missing",
            provider_voice_code="orphan-raw-voice",
            name="孤儿音色",
            languages=["zh-CN"],
            gender=None,
            styles=[],
            sample_url=None,
            supported_formats=["mp3"],
            supported_sample_rates=[24000],
            enabled=True,
        )
        database_session.add_all((orphan_model, orphan_voice))
        database_session.commit()

        service = CapabilityService(database_session, {"unused": "secret"})
        catalog = service.catalog()
        assert catalog.providers == catalog.models == catalog.voices == []
        for call in (
            lambda: service.require_model(orphan_model.id),
            lambda: service.require_voice(orphan_voice.id),
        ):
            with pytest.raises(ApiError) as captured:
                call()
            assert captured.value.code == "CAPABILITY_UNAVAILABLE"


def test_seed_is_idempotent_under_concurrent_sessions(tmp_path):
    engine = create_database_engine(f"sqlite:///{tmp_path / 'seed-race.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    for round_no in range(5):
        code = f"race-provider-{round_no}"
        raw_model = f"race-model-{round_no}"
        raw_voice = f"race-voice-{round_no}"
        seed = ProviderSeed(
            code=code,
            name="并发供应商",
            secret_ref="race-key",
            models=(
                ModelSeed(
                    provider_model_code=raw_model,
                    name="并发模型",
                    capability_types=("llm",),
                    languages=("zh-CN",),
                ),
            ),
            voices=(
                VoiceSeed(
                    provider_voice_code=raw_voice,
                    name="并发音色",
                    languages=("zh-CN",),
                    supported_formats=("mp3",),
                    supported_sample_rates=(24000,),
                ),
            ),
        )
        barrier = threading.Barrier(2)

        def run_seed() -> tuple[str, str, str]:
            """在独立 Session 中执行一次相同 seed 并回读稳定 ID。"""

            with factory() as database_session:
                barrier.wait(timeout=5)
                with database_session.begin():
                    seed_capabilities(database_session, (seed,))
                provider = database_session.scalar(
                    select(CoreProvider).where(CoreProvider.code == code)
                )
                model = database_session.scalar(
                    select(CoreModel).where(
                        CoreModel.provider_id == provider.id,
                        CoreModel.provider_model_code == raw_model,
                    )
                )
                voice = database_session.scalar(
                    select(CoreVoice).where(
                        CoreVoice.provider_id == provider.id,
                        CoreVoice.provider_voice_code == raw_voice,
                    )
                )
                return provider.id, model.id, voice.id

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = tuple(executor.map(lambda _: run_seed(), range(2)))
        assert results[0] == results[1]

    with Session(engine) as database_session:
        assert (
            database_session.scalar(select(func.count()).select_from(CoreProvider)) == 5
        )
        assert database_session.scalar(select(func.count()).select_from(CoreModel)) == 5
        assert database_session.scalar(select(func.count()).select_from(CoreVoice)) == 5
        provider = database_session.scalar(
            select(CoreProvider).where(CoreProvider.code == code)
        )
        model = database_session.scalar(
            select(CoreModel).where(CoreModel.provider_model_code == raw_model)
        )
        voice = database_session.scalar(
            select(CoreVoice).where(CoreVoice.provider_voice_code == raw_voice)
        )
        provider.enabled = model.enabled = voice.enabled = False
        database_session.commit()

    barrier = threading.Barrier(2)
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = tuple(executor.map(lambda _: run_seed(), range(2)))
    assert results[0] == results[1]
    with Session(engine) as database_session:
        provider = database_session.scalar(
            select(CoreProvider).where(CoreProvider.code == code)
        )
        model = database_session.scalar(
            select(CoreModel).where(CoreModel.provider_model_code == raw_model)
        )
        voice = database_session.scalar(
            select(CoreVoice).where(CoreVoice.provider_voice_code == raw_voice)
        )
        assert provider.enabled is model.enabled is voice.enabled is False


def test_seed_rolls_back_entire_batch_when_late_voice_insert_fails(tmp_path):
    engine = create_database_engine(f"sqlite:///{tmp_path / 'seed-atomic.db'}")
    Base.metadata.create_all(engine)
    invalid_seed = ProviderSeed(
        code="atomic-provider",
        name="原子供应商",
        secret_ref="atomic-key",
        models=(
            ModelSeed(
                provider_model_code="atomic-model",
                name="原子模型",
                capability_types=("llm",),
                languages=("zh-CN",),
            ),
        ),
        voices=(
            VoiceSeed(
                provider_voice_code="invalid-voice",
                name=None,  # type: ignore[arg-type]
                languages=("zh-CN",),
                supported_formats=("mp3",),
                supported_sample_rates=(24000,),
            ),
        ),
    )

    with Session(engine) as database_session:
        with pytest.raises(IntegrityError):
            seed_capabilities(database_session, (invalid_seed,))
        database_session.rollback()

    with Session(engine) as verification_session:
        assert (
            verification_session.scalar(select(func.count()).select_from(CoreProvider))
            == 0
        )
        assert (
            verification_session.scalar(select(func.count()).select_from(CoreModel))
            == 0
        )
        assert (
            verification_session.scalar(select(func.count()).select_from(CoreVoice))
            == 0
        )


def test_seed_composes_with_outer_transaction_and_caller_rollback(tmp_path):
    engine = create_database_engine(f"sqlite:///{tmp_path / 'seed-outer.db'}")
    Base.metadata.create_all(engine)
    seed = ProviderSeed(
        code="outer-provider",
        name="外层事务供应商",
        secret_ref="outer-key",
        models=(
            ModelSeed(
                provider_model_code="outer-model",
                name="外层事务模型",
                capability_types=("llm",),
                languages=("zh-CN",),
            ),
        ),
        voices=(
            VoiceSeed(
                provider_voice_code="outer-voice",
                name="外层事务音色",
                languages=("zh-CN",),
                supported_formats=("mp3",),
                supported_sample_rates=(24000,),
            ),
        ),
    )

    class CallerRollback(RuntimeError):
        """模拟调用方在 seed 完成后回滚外层事务。"""

    with Session(engine) as database_session:
        with pytest.raises(CallerRollback):
            with database_session.begin():
                seed_capabilities(database_session, (seed,))
                raise CallerRollback()

    with Session(engine) as verification_session:
        assert (
            verification_session.scalar(select(func.count()).select_from(CoreProvider))
            == 0
        )
        assert (
            verification_session.scalar(select(func.count()).select_from(CoreModel))
            == 0
        )
        assert (
            verification_session.scalar(select(func.count()).select_from(CoreVoice))
            == 0
        )
