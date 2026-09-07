from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from narrato_api.auth.models import User
from narrato_api.billing.models import CreditAccount
from narrato_api.config import Settings
from narrato_api.database import Base
from narrato_api.products.ai_video_tasks import AiVideoPollingWorker
from narrato_api.products.model_generation import (
    Model,
    ModelPlayMode,
    ModelPlayModeProvider,
    ModelPlayModeProviderPrice,
    ModelPlayModeRule,
    ModelTask,
)


class _Registry:
    def get(self, provider_code: str) -> object:
        raise AssertionError("LLM finalization must not call provider again")


def _factory() -> tuple[sessionmaker[Session], ModelTask]:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    with sessions.begin() as session:
        session.add(User(id="usr", email="user@example.test", password_hash="hash"))
        session.add(CreditAccount(user_id="usr", balance=-5))
        session.add(Model(id="llm", display_name="LLM", model_type="llm"))
        session.add(ModelPlayMode(id="mode", model_id="llm", code="chat", display_name="Chat", active_provider_id="provider", default_credits=10))
        session.add(ModelPlayModeProvider(id="provider", play_mode_id="mode", provider_code="volcengine", provider_model_id="endpoint", submit_url="https://ark.cn-beijing.volces.com/api/v3/chat/completions", api_key="key"))
        session.add(ModelPlayModeRule(id="text", play_mode_id="mode", rule_kind="input_constraint", input_type="text", is_supported=True, is_required=True, max_text_units=100))
        session.add(ModelPlayModeProviderPrice(id="token", provider_id="provider", billing_unit="token", per_million_input_credits=10, per_million_output_credits=20))
        task = ModelTask(id="task", user_id="usr", model_id="llm", play_mode_id="mode", provider_id="provider", task_type="llm", status="finalizing", idempotency_key="key", prompt="hello", default_credits_charged=10, input_token=100_000, output_token=100_000)
        session.add(task)
        from narrato_api.products.model_generation import ModelTaskCharge, ModelTaskOutput
        session.add(ModelTaskCharge(id="charge_token", task_id="task", billing_unit="token", per_million_input_credits=10, per_million_output_credits=20, quantity=0, credits=0))
        session.add(ModelTaskOutput(id="output_text", task_id="task", output_type="text", text_content="hello", sort_order=0))
    with sessions() as session:
        task = session.get(ModelTask, "task")
        assert task is not None
        task.poll_lease_token = "lease"
        from datetime import timedelta
        from narrato_api.products.model_generation import utc_now
        task.poll_lease_until = utc_now() + timedelta(seconds=60)
        session.commit()
    with sessions() as session:
        task = session.get(ModelTask, "task")
        assert task is not None
        return sessions, task


def test_worker_settles_llm_actual_tokens_and_allows_current_task_debt() -> None:
    sessions, _task = _factory()
    settings = Settings(database_url="sqlite://", ai_video_poll_interval_seconds=2, ai_video_poll_lease_seconds=35, ai_video_poll_max_backoff_seconds=8, ai_video_poll_max_errors=2, ai_video_submission_recovery_delay_seconds=5)
    worker = AiVideoPollingWorker(sessions, _Registry(), settings)  # type: ignore[arg-type]
    from narrato_api.products.ai_video_tasks import PollClaim
    assert worker.process_claim(PollClaim("task", "lease"))
    with sessions() as session:
        task = session.get(ModelTask, "task")
        account = session.get(CreditAccount, "usr")
        assert task is not None and account is not None
        # 每百万输入 10 积分、输出 20 积分，各使用 0.1M Token，分别向上取整为 1 + 2 积分。
        assert task.status == "succeeded"
        assert task.final_credits == 3
        assert account.balance == 2


def test_worker_transfers_video_to_oss_and_uses_core_duration() -> None:
    from datetime import timedelta
    from narrato_api.integrations.core_client import MediaProbeResult
    from narrato_api.integrations.oss_client import OssStoredObject
    from narrato_api.products.ai_video_tasks import PollClaim
    from narrato_api.products.model_generation import ModelTaskCharge, ModelTaskOutput, utc_now

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    with sessions.begin() as session:
        session.add(User(id="video_user", email="video@example.test", password_hash="hash"))
        session.add(CreditAccount(user_id="video_user", balance=0))
        session.add(Model(id="video_model", display_name="Video", model_type="video"))
        session.add(ModelPlayMode(id="video_mode", model_id="video_model", code="reference", display_name="Reference", active_provider_id="video_provider", default_credits=5))
        session.add(ModelPlayModeProvider(id="video_provider", play_mode_id="video_mode", provider_code="volcengine", provider_model_id="endpoint", submit_url="https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks", status_query_url="https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks/{task_id}", api_key="key"))
        task = ModelTask(id="video_task", user_id="video_user", model_id="video_model", play_mode_id="video_mode", provider_id="video_provider", task_type="video", status="finalizing", idempotency_key="video-key", default_credits_charged=5, poll_lease_token="lease", poll_lease_until=utc_now() + timedelta(seconds=60))
        session.add(task)
        session.add(ModelTaskCharge(id="video_price", task_id="video_task", billing_unit="second", per_second_credits=70, quantity=0, credits=0))
        session.add(ModelTaskOutput(id="video_output", task_id="video_task", output_type="video", provider_url="https://result.example/output.mp4", sort_order=0))

    class Oss:
        def copy_from_url(self, **kwargs: object) -> OssStoredObject:
            assert kwargs["source_url"] == "https://result.example/output.mp4"
            return OssStoredObject(bucket="bucket", object_key="narrato/model-results/video_task/0.mp4", cdn_url="https://cdn.example/output.mp4", size_bytes=7, content_type="video/mp4")

    class Core:
        def probe_media(self, **kwargs: object) -> MediaProbeResult:
            assert kwargs["source_url"] == "https://cdn.example/output.mp4"
            return MediaProbeResult(valid=True, duration_seconds=4.3)

        def get_probe_result(self, core_task_id: str) -> MediaProbeResult:
            raise AssertionError("synchronous fake should not be polled")

    settings = Settings(database_url="sqlite://", oss_bucket="bucket", ai_video_poll_interval_seconds=2, ai_video_poll_lease_seconds=35, ai_video_poll_max_backoff_seconds=8, ai_video_poll_max_errors=2, ai_video_submission_recovery_delay_seconds=5)
    worker = AiVideoPollingWorker(sessions, _Registry(), settings, oss_client=Oss(), core_client=Core())  # type: ignore[arg-type]
    assert worker.process_claim(PollClaim("video_task", "lease"))
    with sessions() as session:
        task = session.get(ModelTask, "video_task")
        output = session.get(ModelTaskOutput, "video_output")
        assert task is not None and output is not None
        assert task.status == "succeeded"
        assert task.error_code is None
        assert task.error_message is None
        assert task.actual_output_duration_seconds == 4.3
        assert task.final_credits == 301
        assert output.cdn_url == "https://cdn.example/output.mp4"


def test_worker_completes_playable_video_when_core_probe_has_no_state() -> None:
    from datetime import timedelta
    from narrato_api.integrations.core_client import MediaProbeResult
    from narrato_api.products.ai_video_tasks import PollClaim
    from narrato_api.products.model_generation import ModelTaskCharge, ModelTaskOutput, utc_now

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    with sessions.begin() as session:
        session.add(User(id="video_user", email="video@example.test", password_hash="hash"))
        session.add(CreditAccount(user_id="video_user", balance=0))
        session.add(Model(id="video_model", display_name="Video", model_type="video"))
        session.add(ModelPlayMode(id="video_mode", model_id="video_model", code="text_to_video", display_name="Text to Video", active_provider_id="video_provider", default_credits=5))
        session.add(ModelPlayModeProvider(id="video_provider", play_mode_id="video_mode", provider_code="volcengine", provider_model_id="endpoint", submit_url="https://provider.example/submit", api_key="key"))
        session.add(ModelTask(id="video_task", user_id="video_user", model_id="video_model", play_mode_id="video_mode", provider_id="video_provider", task_type="video", status="finalizing", idempotency_key="video-key", requested_duration_seconds=4, default_credits_charged=5, poll_lease_token="lease", poll_lease_until=utc_now() + timedelta(seconds=60)))
        session.add(ModelTaskCharge(id="video_price", task_id="video_task", billing_unit="second", per_second_credits=70, quantity=0, credits=0))
        session.add(ModelTaskOutput(id="video_output", task_id="video_task", output_type="video", cdn_url="https://cdn.example/output.mp4", sort_order=0))

    class Core:
        def probe_media(self, **_kwargs: object) -> MediaProbeResult:
            raise AssertionError("fixed-duration playable video must not wait for Core")

        def get_probe_result(self, _core_task_id: str) -> MediaProbeResult:
            raise AssertionError("no probe task ID was supplied")

    settings = Settings(database_url="sqlite://", oss_bucket="bucket", ai_video_poll_interval_seconds=2, ai_video_poll_lease_seconds=35, ai_video_poll_max_backoff_seconds=8, ai_video_poll_max_errors=2, ai_video_submission_recovery_delay_seconds=5)
    worker = AiVideoPollingWorker(sessions, _Registry(), settings, oss_client=object(), core_client=Core())  # type: ignore[arg-type]
    assert worker.process_claim(PollClaim("video_task", "lease"))
    with sessions() as session:
        task = session.get(ModelTask, "video_task")
        output = session.get(ModelTaskOutput, "video_output")
        assert task is not None and output is not None
        assert task.status == "succeeded"
        assert output.duration_seconds == 4.0
        assert task.actual_output_duration_seconds == 4.0


def test_worker_does_not_treat_wan_model_selected_duration_as_fixed() -> None:
    """Wan 3.0 uses duration=-1 for provider-selected output duration."""

    from datetime import timedelta
    from narrato_api.products.ai_video_tasks import PollClaim
    from narrato_api.products.model_generation import ModelTaskOutput, utc_now

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    with sessions.begin() as session:
        session.add(User(id="wan_user", email="wan@example.test", password_hash="hash"))
        session.add(Model(id="wan", display_name="Wan 3.0", model_type="video"))
        session.add(ModelPlayMode(id="wan_mode", model_id="wan", code="reference", display_name="Reference", active_provider_id="wan_provider"))
        session.add(ModelPlayModeProvider(id="wan_provider", play_mode_id="wan_mode", provider_code="apimart", request_profile="wan_30", provider_model_id="wan3.0-video", submit_url="https://provider.example/submit", api_key="key"))
        session.add(ModelTask(id="wan_task", user_id="wan_user", model_id="wan", play_mode_id="wan_mode", provider_id="wan_provider", task_type="video", status="finalizing", idempotency_key="wan-key", requested_duration_seconds=-1, poll_lease_token="lease", poll_lease_until=utc_now() + timedelta(seconds=60)))
        session.add(ModelTaskOutput(id="wan_output", task_id="wan_task", output_type="video", cdn_url="https://cdn.example/output.mp4", sort_order=0))

    settings = Settings(database_url="sqlite://", ai_video_poll_interval_seconds=2, ai_video_poll_lease_seconds=35, ai_video_poll_max_backoff_seconds=8, ai_video_poll_max_errors=2, ai_video_submission_recovery_delay_seconds=5)
    worker = AiVideoPollingWorker(sessions, _Registry(), settings, oss_client=object(), core_client=object())  # type: ignore[arg-type]
    assert worker._complete_fixed_duration_video(PollClaim("wan_task", "lease")) is False
    with sessions() as session:
        output = session.get(ModelTaskOutput, "wan_output")
        assert output is not None and output.duration_seconds is None
