from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import select

from core_api.adapters.narrato.short_drama import (
    FakeShortDramaProvider,
    ProviderTemporaryError,
    ScriptValidationError,
    ShortDramaAdapter,
)
from core_api.infrastructure.oss_client import DownloadReceipt, OssUploadResult
from core_api.runtime.artifact_store import ArtifactStore
from core_api.tasks.handlers import AtomicTaskHandler
from core_api.tasks.models import CoreArtifact, CoreTaskStatus
from core_api.tasks.service import TaskService


SRTS = {
    "https://cdn.example.test/narrato/api/b.srt": b"1\n00:00:00,000 --> 00:00:01,000\nB episode\n",
    "https://cdn.example.test/narrato/api/a.srt": b"1\n00:00:00,000 --> 00:00:01,000\nA episode\n",
}


class MemoryDownloader:
    """从内存 CDN 下载 SRT 和前序分析 Artifact。"""

    def __init__(self) -> None:
        self.objects = dict(SRTS)

    def download(
        self, url: str, destination: Path, *, max_bytes: int
    ) -> DownloadReceipt:
        content = self.objects[url]
        assert len(content) <= max_bytes
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
        return DownloadReceipt(
            url,
            len(content),
            "application/json" if url.endswith(".json") else "application/x-subrip",
        )


class MemoryOss:
    """记录确定性 JSON 产物内容。"""

    public_base_url = "https://cdn.example.test"

    def __init__(self, downloader: MemoryDownloader) -> None:
        self.downloader = downloader
        self.uploads: dict[str, bytes] = {}

    def upload_stream(
        self, stream, object_key: str, *, content_type: str, size: int
    ) -> OssUploadResult:
        content = stream.read()
        assert len(content) == size
        self.uploads[object_key] = content
        url = f"https://cdn.example.test/{object_key}"
        self.downloader.objects[url] = content
        return OssUploadResult("fake-core", object_key, url)


class CapturingFakeProvider(FakeShortDramaProvider):
    """确认 script 阶段实际收到 analysis 冻结字幕，而非剧情摘要。"""

    received_subtitles: list[str]

    def generate_script(self, analysis, *, sources, language, config):
        self.received_subtitles = [str(source.subtitle_text) for source in sources]
        return super().generate_script(
            analysis, sources=sources, language=language, config=config
        )


class DuplicateEventIdProvider(FakeShortDramaProvider):
    """模拟每次独立视频调用都从 event_001 开始编号。"""

    def analyze_video(self, source, *, subtitle_text, language, config):
        result = dict(super().analyze_video(
            source,
            subtitle_text=subtitle_text,
            language=language,
            config=config,
        ))
        result["events"] = [{**item, "event_id": "event_001"} for item in result["events"]]
        return result


class FailingRepairProvider(CapturingFakeProvider):
    """模型已返回可编辑脚本后，模拟自动修复供应商失败。"""

    original_script: list[dict[str, object]]

    def match_script(self, script, *, sources):
        self.original_script = [
            {
                "source_asset_id": "unknown_asset",
                "start": 0.0,
                "end": 10.0,
                "narration": "结构错误",
                "original_sound": False,
            },
            {
                "source_asset_id": sources[1].source_asset_id,
                "start": 0.0,
                "end": 1.0,
                "narration": "模型正常返回的第二个片段",
                "original_sound": False,
            },
        ]
        return self.original_script

    def repair_script(self, invalid_script, *, validation_errors, sources):
        self.repair_calls += 1
        raise ProviderTemporaryError("PROVIDER_TEMPORARY_FAILURE")


def source_snapshots(with_subtitles: bool = True) -> list[dict[str, object]]:
    """返回按 B、A 排序的显式来源快照。"""

    result = []
    for asset_id in ("asset_b", "asset_a"):
        item: dict[str, object] = {
            "source_asset_id": asset_id,
            "video_url": f"https://cdn.example.test/narrato/api/{asset_id[-1]}.mp4",
            "duration_seconds": 10.0,
        }
        if with_subtitles:
            item["subtitle_url"] = (
                f"https://cdn.example.test/narrato/api/{asset_id[-1]}.srt"
            )
        result.append(item)
    return result


def test_audio_understanding_keeps_business_subtitle_contract_and_json_artifact(
    session, tmp_path
):
    service = TaskService(session)
    downloader = MemoryDownloader()
    oss = MemoryOss(downloader)
    handler = AtomicTaskHandler(
        task_service=service,
        work_root=tmp_path / "audio-understanding-work",
        short_drama_adapter=ShortDramaAdapter(
            provider=FakeShortDramaProvider(),
            artifact_store=ArtifactStore(oss),
        ),
    )
    task = service.create_core_task(
        caller="narrato-api",
        route="/api/v1/audio-understanding/tasks",
        task_type="audio_understanding",
        idempotency_key="fake-audio-understanding",
        input_snapshot={
            "model_id": "model_fake",
            "model_snapshot": {
                "model_id": "model_fake",
                "catalog_version": "catalog_test",
            },
            "language": "zh-CN",
            "config_snapshot": {
                "fps": 1,
                "min_frame_tokens": 64,
                "min_frame_tokens_mode": "provider_default",
            },
            "source_order": ["asset_b", "asset_a"],
            "sources": source_snapshots(with_subtitles=False),
        },
    )

    handler.run(task.id)
    completed = service.get_task(task.id)
    assert completed.status == CoreTaskStatus.SUCCEEDED
    assert [item["source_asset_id"] for item in completed.result["subtitles"]] == [
        "asset_b",
        "asset_a",
    ]
    assert all(
        item["artifact"]["kind"] == "subtitle"
        for item in completed.result["subtitles"]
    )
    aggregate = next(
        item for item in completed.result["artifacts"]
        if item["kind"] == "audio_understanding"
    )
    payload = json.loads(oss.uploads[aggregate["object_key"]])
    assert payload["schema_version"] == "short-drama-audio-understanding.v1"
    assert payload["config_snapshot"]["min_frame_tokens_mode"] == "provider_default"


def test_analysis_namespaces_provider_event_ids_per_source(session, tmp_path):
    service = TaskService(session)
    downloader = MemoryDownloader()
    oss = MemoryOss(downloader)
    handler = AtomicTaskHandler(
        task_service=service,
        work_root=tmp_path / "namespaced-events-work",
        short_drama_adapter=ShortDramaAdapter(
            provider=DuplicateEventIdProvider(),
            downloader=downloader,
            artifact_store=ArtifactStore(oss),
        ),
    )
    task = service.create_core_task(
        caller="narrato-api",
        route="/api/v1/video-analysis/tasks",
        task_type="video_analysis",
        idempotency_key="namespaced-events",
        input_snapshot={
            "model_id": "model_fake",
            "model_snapshot": {"model_id": "model_fake"},
            "language": "zh-CN",
            "config_snapshot": {},
            "source_order": ["asset_b", "asset_a"],
            "sources": source_snapshots(),
        },
    )
    handler.run(task.id)
    events = service.get_task(task.id).result["analysis"]["events"]
    assert [event["event_id"] for event in events] == [
        "asset_b:event_001",
        "asset_a:event_001",
    ]


def test_fake_provider_analysis_then_script_artifacts_are_safe_and_registered(
    session, tmp_path
):
    service = TaskService(session)
    downloader = MemoryDownloader()
    oss = MemoryOss(downloader)
    provider = CapturingFakeProvider(invalid_first=True)
    adapter = ShortDramaAdapter(
        provider=provider,
        downloader=downloader,
        artifact_store=ArtifactStore(oss),
    )
    handler = AtomicTaskHandler(
        task_service=service,
        work_root=tmp_path / "work",
        short_drama_adapter=adapter,
    )
    common = {
        "model_id": "model_fake",
        "model_snapshot": {"model_id": "model_fake", "catalog_version": "catalog_test"},
        "language": "zh-CN",
        "config_snapshot": {"drama_genre": "复仇", "original_sound_ratio": 30},
        "source_order": ["asset_b", "asset_a"],
    }
    analysis_task = service.create_core_task(
        caller="narrato-api",
        route="/api/v1/video-analysis/tasks",
        task_type="video_analysis",
        idempotency_key="fake-analysis",
        input_snapshot={**common, "sources": source_snapshots()},
    )
    handler.run(analysis_task.id)
    analysis_task = service.get_task(analysis_task.id)
    assert analysis_task.status == CoreTaskStatus.SUCCEEDED
    assert analysis_task.phase == "analysis"
    analysis_artifact = analysis_task.result["artifacts"][0]
    analysis_json = json.loads(oss.uploads[analysis_artifact["object_key"]])
    assert analysis_task.result["analysis"] == analysis_json["analysis"]
    assert analysis_artifact["kind"] == "analysis"
    assert analysis_json["source_order"] == ["asset_b", "asset_a"]
    assert analysis_json["model_snapshot"] == {
        "model_id": "model_fake",
        "catalog_version": "catalog_test",
    }
    assert analysis_json["language"] == "zh-CN"
    assert analysis_json["config_snapshot"]["drama_genre"] == "复仇"
    assert analysis_json["prompt_metadata"] == {
        "prompt_category": "short_drama_narration",
        "prompt_name": "plot_analysis",
        "prompt_version": "v1.1",
    }
    assert analysis_json["sources"] == [
        {
            "source_asset_id": "asset_b",
            "order": 0,
            "video_url": "https://cdn.example.test/narrato/api/b.mp4",
            "subtitle_url": "https://cdn.example.test/narrato/api/b.srt",
            "duration_seconds": 10.0,
        },
        {
            "source_asset_id": "asset_a",
            "order": 1,
            "video_url": "https://cdn.example.test/narrato/api/a.mp4",
            "subtitle_url": "https://cdn.example.test/narrato/api/a.srt",
            "duration_seconds": 10.0,
        },
    ]

    script_task = service.create_core_task(
        caller="narrato-api",
        route="/api/v1/script-generation/tasks",
        task_type="script_generation",
        idempotency_key="fake-script",
        input_snapshot={
            **common,
            "sources": source_snapshots(with_subtitles=False),
            "analysis_artifact": {
                "artifact_id": analysis_artifact["artifact_id"],
                "url": analysis_artifact["url"],
            },
        },
    )
    handler.run(script_task.id)
    script_task = service.get_task(script_task.id)

    assert script_task.status == CoreTaskStatus.SUCCEEDED
    assert script_task.phase == "script_generation"
    assert provider.repair_calls == 1
    assert provider.received_subtitles == [
        "1\n00:00:00,000 --> 00:00:01,000\nB episode",
        "1\n00:00:00,000 --> 00:00:01,000\nA episode",
    ]
    assert {item["kind"] for item in script_task.result["artifacts"]} == {
        "timeline",
        "editor_draft",
    }
    rows = session.scalars(
        select(CoreArtifact).where(CoreArtifact.core_task_id == script_task.id)
    ).all()
    assert {row.kind for row in rows} == {"timeline", "editor_draft"}
    payloads = [
        json.loads(oss.uploads[item["object_key"]])
        for item in script_task.result["artifacts"]
    ]
    text = json.dumps(payloads, ensure_ascii=False)
    assert (
        "/private/" not in text
        and "provider_raw" not in text
        and "fake-only" not in text
    )
    timeline = next(
        item for item in payloads if item["schema_version"] == "short-drama-timeline.v1"
    )
    assert [item["source_asset_id"] for item in timeline["items"][:2]] == [
        "asset_b",
        "asset_a",
    ]
    assert timeline["language"] == "zh-CN"
    assert timeline["config_snapshot"]["original_sound_ratio"] == 30
    assert len(timeline["sources"]) == 2
    assert [item["subtitle_url"] for item in timeline["sources"]] == [
        "https://cdn.example.test/narrato/api/b.srt",
        "https://cdn.example.test/narrato/api/a.srt",
    ]


def test_fake_provider_retryable_error_enters_retry_wait(session, tmp_path):
    service = TaskService(session)
    adapter = ShortDramaAdapter(provider=FakeShortDramaProvider(retryable_failures=1))
    task = service.create_core_task(
        caller="narrato-api",
        route="/api/v1/video-analysis/tasks",
        task_type="video_analysis",
        idempotency_key="fake-retryable",
        input_snapshot={
            "model_id": "model_fake",
            "model_snapshot": {
                "model_id": "model_fake",
                "catalog_version": "catalog_test",
            },
            "language": "zh-CN",
            "config_snapshot": {},
            "source_order": ["asset_a"],
            "sources": [
                {
                    "source_asset_id": "asset_a",
                    "video_url": "https://cdn.example.test/narrato/api/a.mp4",
                    "subtitle_text": "explicit fixture",
                    "duration_seconds": 10,
                }
            ],
        },
    )
    handler = AtomicTaskHandler(
        task_service=service,
        work_root=tmp_path / "retry-work",
        short_drama_adapter=adapter,
    )
    handler.run(task.id)
    assert service.get_task(task.id).status == CoreTaskStatus.RETRY_WAIT
    assert service.get_task(task.id).error["code"] == "PROVIDER_TEMPORARY_FAILURE"


def test_script_task_retries_when_automatic_repair_temporarily_fails(
    session, tmp_path
):
    service = TaskService(session)
    downloader = MemoryDownloader()
    oss = MemoryOss(downloader)
    provider = FailingRepairProvider()
    handler = AtomicTaskHandler(
        task_service=service,
        work_root=tmp_path / "nonblocking-repair-work",
        short_drama_adapter=ShortDramaAdapter(
            provider=provider,
            downloader=downloader,
            artifact_store=ArtifactStore(oss),
        ),
    )
    common = {
        "model_id": "model_fake",
        "model_snapshot": {
            "model_id": "model_fake",
            "catalog_version": "catalog_test",
        },
        "language": "zh-CN",
        "config_snapshot": {"original_sound_ratio": 30},
        "source_order": ["asset_b", "asset_a"],
    }
    analysis_task = service.create_core_task(
        caller="narrato-api",
        route="/api/v1/video-analysis/tasks",
        task_type="video_analysis",
        idempotency_key="nonblocking-repair-analysis",
        input_snapshot={**common, "sources": source_snapshots()},
    )
    handler.run(analysis_task.id)
    analysis_artifact = service.get_task(analysis_task.id).result["artifacts"][0]
    script_task = service.create_core_task(
        caller="narrato-api",
        route="/api/v1/script-generation/tasks",
        task_type="script_generation",
        idempotency_key="nonblocking-repair-script",
        input_snapshot={
            **common,
            "sources": source_snapshots(with_subtitles=False),
            "analysis_artifact": {
                "artifact_id": analysis_artifact["artifact_id"],
                "url": analysis_artifact["url"],
            },
        },
    )

    handler.run(script_task.id)
    completed = service.get_task(script_task.id)

    assert completed.status == CoreTaskStatus.RETRY_WAIT
    assert completed.result is None
    assert provider.repair_calls == 1


def test_script_task_persists_exact_validation_diagnostics(session, tmp_path):
    class DiagnosticAdapter:
        def run_script_generation(self, **_kwargs):
            raise ScriptValidationError(
                "SCRIPT_SOURCE_UNKNOWN",
                details={"item_index": 2, "source_asset_id": "unknown"},
                diagnostics={"stage": "repair_after_timeline_validation"},
            )

    service = TaskService(session)
    task = service.create_core_task(
        caller="narrato-api",
        route="/api/v1/script-generation/tasks",
        task_type="script_generation",
        idempotency_key="diagnostic-script",
        input_snapshot={},
    )
    AtomicTaskHandler(
        task_service=service,
        work_root=tmp_path / "diagnostic-work",
        short_drama_adapter=DiagnosticAdapter(),  # type: ignore[arg-type]
    ).run(task.id)

    failed = service.get_task(task.id)
    assert failed.status == CoreTaskStatus.FAILED
    assert failed.error == {
        "code": "SCRIPT_VALIDATION_FAILED",
        "reason": "SCRIPT_SOURCE_UNKNOWN",
        "details": {"item_index": 2, "source_asset_id": "unknown"},
        "diagnostics": {"stage": "repair_after_timeline_validation"},
        "retryable": False,
    }


def test_duplicate_wake_does_not_duplicate_analysis_artifact(session, tmp_path):
    service = TaskService(session)
    downloader = MemoryDownloader()
    oss = MemoryOss(downloader)
    handler = AtomicTaskHandler(
        task_service=service,
        work_root=tmp_path / "duplicate-work",
        short_drama_adapter=ShortDramaAdapter(
            provider=FakeShortDramaProvider(),
            downloader=downloader,
            artifact_store=ArtifactStore(oss),
        ),
    )
    task = service.create_core_task(
        caller="narrato-api",
        route="/api/v1/video-analysis/tasks",
        task_type="video_analysis",
        idempotency_key="duplicate-analysis",
        input_snapshot={
            "model_id": "model_fake",
            "model_snapshot": {
                "model_id": "model_fake",
                "catalog_version": "catalog_test",
            },
            "language": "zh-CN",
            "config_snapshot": {},
            "source_order": ["asset_b", "asset_a"],
            "sources": source_snapshots(),
        },
    )
    handler.run(task.id)
    handler.run(task.id)
    assert len(oss.uploads) == 1
    assert (
        len(
            session.scalars(
                select(CoreArtifact).where(CoreArtifact.core_task_id == task.id)
            ).all()
        )
        == 1
    )


def test_retryable_analysis_recovers_on_new_attempt(session, tmp_path):
    service = TaskService(session)
    downloader = MemoryDownloader()
    oss = MemoryOss(downloader)
    provider = FakeShortDramaProvider(retryable_failures=1)
    handler = AtomicTaskHandler(
        task_service=service,
        work_root=tmp_path / "recovery-work",
        short_drama_adapter=ShortDramaAdapter(
            provider=provider,
            downloader=downloader,
            artifact_store=ArtifactStore(oss),
        ),
    )
    task = service.create_core_task(
        caller="narrato-api",
        route="/api/v1/video-analysis/tasks",
        task_type="video_analysis",
        idempotency_key="analysis-recovery",
        input_snapshot={
            "model_id": "model_fake",
            "model_snapshot": {
                "model_id": "model_fake",
                "catalog_version": "catalog_test",
            },
            "language": "zh-CN",
            "config_snapshot": {},
            "source_order": ["asset_b", "asset_a"],
            "sources": source_snapshots(),
        },
    )
    handler.run(task.id)
    retrying = service.get_task(task.id)
    assert retrying.status == CoreTaskStatus.RETRY_WAIT
    handler.run(
        task.id,
        expected_state_version=retrying.state_version,
        not_before=retrying.updated_at,
    )
    assert service.get_task(task.id).status == CoreTaskStatus.SUCCEEDED
    assert service.get_task(task.id).current_attempt_no == 2
    assert (
        len(
            session.scalars(
                select(CoreArtifact).where(CoreArtifact.core_task_id == task.id)
            ).all()
        )
        == 1
    )


def test_script_rejects_analysis_artifact_with_different_source_order(
    session, tmp_path
):
    service = TaskService(session)
    downloader = MemoryDownloader()
    analysis_url = "https://cdn.example.test/narrato/coreApi/bad-analysis.json"
    downloader.objects[analysis_url] = json.dumps(
        {
            "schema_version": "short-drama-analysis.v1",
            "source_order": ["asset_a", "asset_b"],
            "analysis": {"summary": "wrong map", "scenes": []},
        }
    ).encode()
    handler = AtomicTaskHandler(
        task_service=service,
        work_root=tmp_path / "bad-analysis-work",
        short_drama_adapter=ShortDramaAdapter(
            provider=FakeShortDramaProvider(),
            downloader=downloader,
            artifact_store=ArtifactStore(MemoryOss(downloader)),
        ),
    )
    task = service.create_core_task(
        caller="narrato-api",
        route="/api/v1/script-generation/tasks",
        task_type="script_generation",
        idempotency_key="bad-analysis-order",
        input_snapshot={
            "model_id": "model_fake",
            "model_snapshot": {
                "model_id": "model_fake",
                "catalog_version": "catalog_test",
            },
            "language": "zh-CN",
            "config_snapshot": {},
            "source_order": ["asset_b", "asset_a"],
            "sources": source_snapshots(with_subtitles=False),
            "analysis_artifact": {"artifact_id": "art_bad", "url": analysis_url},
        },
    )
    handler.run(task.id)
    assert service.get_task(task.id).status == CoreTaskStatus.FAILED
    assert service.get_task(task.id).error["code"] == "SHORT_DRAMA_INPUT_INVALID"
