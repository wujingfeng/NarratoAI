from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from core_api.adapters.narrato.media_probe import (
    AdapterError,
    SRT_MAX_BYTES,
    VIDEO_MAX_BYTES,
    SrtConstraintError,
    _extension,
    parse_srt,
)
from core_api.infrastructure.oss_client import Downloader
from core_api.runtime.artifact_store import ArtifactStore
from core_api.runtime.workspace import CoreTaskWorkspace


class AsrInvalidSrtError(AdapterError):
    """ASR 返回空或损坏的字幕结果。"""

    code = "ASR_INVALID_SRT"


class AsrTemporaryError(AdapterError):
    """ASR 服务暂时失败，可由 attempt 自动重试。"""

    code = "ASR_TEMPORARY_FAILURE"
    retryable = True


AsrTranscriber = Callable[[str, str], str | None]


def default_fun_asr_transcriber(local_file: str, subtitle_file: str) -> str | None:
    """调用 NarratoAI 现有本地 FunASR 稳定入口。"""

    from app.services.fun_asr_subtitle import create_with_local_fun_asr

    return create_with_local_fun_asr(local_file, subtitle_file=subtitle_file)


@dataclass(slots=True)
class AsrAdapter:
    """在独立 workspace 调用 ASR 并上传统一 SRT Artifact。"""

    downloader: Downloader
    transcriber: AsrTranscriber
    artifact_store: ArtifactStore

    def run(
        self,
        *,
        source_url: str,
        declared_extension: str,
        core_task_id: str,
        attempt_no: int,
        workspace: CoreTaskWorkspace,
        lease_guard: Callable[[], None] | None = None,
    ) -> dict[str, object]:
        """执行显式输入 ASR，不读取共享目录或供应商全局状态。"""

        extension = _extension(declared_extension, video_only=True)
        source = workspace.controlled_path("input", "media", extension)
        self.downloader.download(source_url, source, max_bytes=VIDEO_MAX_BYTES)
        target = workspace.controlled_path("output", "subtitle", "srt")
        try:
            returned = self.transcriber(str(source), str(target))
        except AdapterError:
            raise
        except Exception as exc:
            # 不把第三方响应或本地路径写入任务错误。
            raise AsrTemporaryError("ASR_TEMPORARY_FAILURE") from exc
        result_path = Path(returned) if returned else target
        try:
            if result_path.resolve(strict=True) != target.resolve(strict=True):
                raise AsrInvalidSrtError("ASR_INVALID_SRT")
            if target.stat().st_size > SRT_MAX_BYTES:
                raise AsrInvalidSrtError("ASR_INVALID_SRT")
            metadata = parse_srt(target.read_bytes())
        except (OSError, SrtConstraintError) as exc:
            raise AsrInvalidSrtError("ASR_INVALID_SRT") from exc
        if lease_guard is not None:
            # OSS 是不可逆外部副作用，上传前必须同步确认 current lease fencing。
            lease_guard()
        artifact = self.artifact_store.upload(
            workspace=workspace,
            local_path=target,
            core_task_id=core_task_id,
            attempt_no=attempt_no,
            kind="subtitle",
            content_type="application/x-subrip; charset=utf-8",
        )
        return {"metadata": metadata, "artifacts": [artifact.to_dict()]}
