from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from core_api.adapters.narrato.media_probe import (
    AdapterError,
    SRT_MAX_BYTES,
    VIDEO_MAX_BYTES,
    VIDEO_EXTENSIONS,
    SrtConstraintError,
    parse_srt,
)
from core_api.infrastructure.oss_client import Downloader
from core_api.runtime.artifact_store import ArtifactStore
from core_api.runtime.process_runner import ProcessRunner
from core_api.runtime.workspace import CoreTaskWorkspace
from core_api.tasks.asr_jobs import AsrProviderJobStore


class AsrInvalidSrtError(AdapterError):
    """ASR 返回空或损坏的字幕结果。"""

    code = "ASR_INVALID_SRT"


class AsrTemporaryError(AdapterError):
    """ASR 服务暂时失败，可由 attempt 自动重试。"""

    code = "ASR_TEMPORARY_FAILURE"
    retryable = True


AsrTranscriber = Callable[[str, str], str | None]
AsrSourceTranscriber = Callable[..., str | None]
AUDIO_EXTENSIONS = frozenset({"mp3", "wav", "ogg", "m4a", "aac", "flac"})
VOLCENGINE_DIRECT_AUDIO_EXTENSIONS = frozenset({"mp3", "wav", "ogg"})
ASR_PREVIEW_CHARS = 24_000


def _srt_preview(content: bytes) -> tuple[str, bool]:
    """Return a bounded UTF text preview of an already validated SRT."""

    for encoding in ("utf-8-sig", "utf-16", "gb18030"):
        try:
            text = content.decode(encoding)
        except UnicodeError:
            continue
        if "\x00" not in text:
            normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
            return normalized[:ASR_PREVIEW_CHARS], len(normalized) > ASR_PREVIEW_CHARS
    raise AsrInvalidSrtError("ASR_INVALID_SRT")


def default_fun_asr_transcriber(local_file: str, subtitle_file: str) -> str | None:
    """调用 NarratoAI 现有本地 FunASR 稳定入口。"""

    from app.services.fun_asr_subtitle import create_with_local_fun_asr

    return create_with_local_fun_asr(local_file, subtitle_file=subtitle_file)


@dataclass(slots=True)
class AsrAdapter:
    """在独立 workspace 调用 ASR 并上传统一 SRT Artifact。"""

    downloader: Downloader
    transcriber: AsrTranscriber | None
    artifact_store: ArtifactStore
    source_transcriber: AsrSourceTranscriber | None = None
    source_url_validator: Callable[[str], str] | None = None
    process_runner: ProcessRunner | None = None
    provider_job_store: AsrProviderJobStore | None = None

    def run(
        self,
        *,
        sources: list[dict[str, object]],
        core_task_id: str,
        attempt_no: int,
        workspace: CoreTaskWorkspace,
        lease_guard: Callable[[], None] | None = None,
    ) -> dict[str, object]:
        """按输入顺序识别 1..5 个音视频来源并返回一一对应的字幕。"""

        if not isinstance(sources, list) or not 1 <= len(sources) <= 5:
            raise AsrInvalidSrtError("ASR_SOURCES_INVALID")
        subtitles: list[dict[str, object]] = []
        artifacts: list[dict[str, object]] = []
        for index, item in enumerate(sources):
            if not isinstance(item, dict):
                raise AsrInvalidSrtError("ASR_SOURCE_INVALID")
            source_asset_id = item.get("source_asset_id")
            source_url = item.get("source_url")
            raw_extension = str(item.get("declared_extension") or "").lower().lstrip(".")
            if (
                not isinstance(source_asset_id, str)
                or not source_asset_id
                or not isinstance(source_url, str)
                or raw_extension not in VIDEO_EXTENSIONS | AUDIO_EXTENSIONS
            ):
                raise AsrInvalidSrtError("ASR_SOURCE_INVALID")
            target = workspace.controlled_path("output", f"subtitle_{index}", "srt")
            try:
                if self.source_transcriber is not None:
                    provider_url, provider_format = self._prepare_remote_source(
                        source_url=source_url,
                        extension=raw_extension,
                        source_index=index,
                        source_asset_id=source_asset_id,
                        core_task_id=core_task_id,
                        attempt_no=attempt_no,
                        workspace=workspace,
                        lease_guard=lease_guard,
                    )
                    returned = self.source_transcriber(
                        provider_url,
                        provider_format,
                        str(target),
                        core_task_id=core_task_id,
                        source_index=index,
                        source_asset_id=source_asset_id,
                        lease_guard=lease_guard,
                    )
                else:
                    if self.transcriber is None:
                        raise AsrTemporaryError("ASR_TEMPORARY_FAILURE")
                    source = workspace.controlled_path(
                        "input", f"media_{index}", raw_extension
                    )
                    self.downloader.download(
                        source_url, source, max_bytes=VIDEO_MAX_BYTES
                    )
                    returned = self.transcriber(str(source), str(target))
            except AdapterError:
                raise
            except Exception as exc:
                raise AsrTemporaryError("ASR_TEMPORARY_FAILURE") from exc
            result_path = Path(returned) if returned else target
            try:
                if result_path.resolve(strict=True) != target.resolve(strict=True):
                    raise AsrInvalidSrtError("ASR_INVALID_SRT")
                if target.stat().st_size > SRT_MAX_BYTES:
                    raise AsrInvalidSrtError("ASR_INVALID_SRT")
                subtitle_content = target.read_bytes()
                metadata = parse_srt(subtitle_content)
                preview_text, preview_truncated = _srt_preview(subtitle_content)
            except (OSError, SrtConstraintError) as exc:
                raise AsrInvalidSrtError("ASR_INVALID_SRT") from exc
            if lease_guard is not None:
                lease_guard()
            artifact = self.artifact_store.upload(
                workspace=workspace,
                local_path=target,
                core_task_id=core_task_id,
                attempt_no=attempt_no,
                kind="subtitle",
                content_type="application/x-subrip; charset=utf-8",
            ).to_dict()
            artifacts.append(artifact)
            subtitles.append(
                {
                    "source_asset_id": source_asset_id,
                    "metadata": metadata,
                    "artifact": artifact,
                    "preview_text": preview_text,
                    "preview_truncated": preview_truncated,
                }
            )
        return {"subtitles": subtitles, "artifacts": artifacts}

    def _prepare_remote_source(
        self,
        *,
        source_url: str,
        extension: str,
        source_index: int,
        source_asset_id: str,
        core_task_id: str,
        attempt_no: int,
        workspace: CoreTaskWorkspace,
        lease_guard: Callable[[], None] | None,
    ) -> tuple[str, str]:
        validated_url = (
            self.source_url_validator(source_url)
            if self.source_url_validator is not None
            else source_url
        )
        if extension in VOLCENGINE_DIRECT_AUDIO_EXTENSIONS:
            return validated_url, extension
        if self.process_runner is None or self.provider_job_store is None:
            raise AsrTemporaryError("ASR_MEDIA_PREPROCESSOR_UNAVAILABLE")
        job = self.provider_job_store.get_or_create(
            core_task_id=core_task_id,
            source_index=source_index,
            source_asset_id=source_asset_id,
        )
        if job.prepared_audio_url:
            return job.prepared_audio_url, "mp3"
        source = workspace.controlled_path("input", f"media_{source_index}", extension)
        target = workspace.controlled_path(
            "output", f"asr_audio_{source_index}", "mp3"
        )
        self.downloader.download(validated_url, source, max_bytes=VIDEO_MAX_BYTES)
        result = self.process_runner.run(
            [
                "ffmpeg",
                "-nostdin",
                "-y",
                "-i",
                str(source),
                "-vn",
                "-codec:a",
                "libmp3lame",
                "-q:a",
                "2",
                str(target),
            ],
            timeout_seconds=600,
            heartbeat=lease_guard,
        )
        if result.timed_out or result.exit_code != 0 or not target.is_file():
            raise AsrInvalidSrtError("ASR_AUDIO_EXTRACTION_FAILED")
        if lease_guard is not None:
            lease_guard()
        artifact = self.artifact_store.upload(
            workspace=workspace,
            local_path=target,
            core_task_id=core_task_id,
            attempt_no=attempt_no,
            kind="asr_audio",
            content_type="audio/mpeg",
        ).to_dict()
        job = self.provider_job_store.set_prepared_audio(
            job.id, artifact=artifact, attempt_no=attempt_no
        )
        assert job.prepared_audio_url is not None
        return job.prepared_audio_url, "mp3"
