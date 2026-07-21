from __future__ import annotations

from core_api.type_coercion import as_float, as_int

import math
import struct
import wave
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import httpx

from core_api.adapters.narrato.media_probe import AdapterError
from core_api.runtime.artifact_store import ArtifactStore
from core_api.runtime.workspace import CoreTaskWorkspace


class TtsInputError(AdapterError):
    """TTS 输入或冻结音色快照无效。"""

    code = "TTS_INPUT_INVALID"


class TtsTemporaryError(AdapterError):
    """TTS 供应商发生可自动重试的临时错误。"""

    code = "TTS_TEMPORARY_FAILURE"
    retryable = True


def validate_wav(path: Path) -> None:
    """确认 WAV 可解析、非空且使用受支持的 PCM 基本参数。"""
    try:
        if path.stat().st_size > 100 * 1024 * 1024:
            raise TtsInputError("TTS_OUTPUT_INVALID")
        with wave.open(str(path), "rb") as audio:
            if (
                audio.getnchannels() not in {1, 2}
                or audio.getsampwidth() not in {1, 2, 3, 4}
                or not 8_000 <= audio.getframerate() <= 48_000
                or audio.getnframes() <= 0
                or audio.getcomptype() != "NONE"
            ):
                raise TtsInputError("TTS_OUTPUT_INVALID")
    except (OSError, EOFError, wave.Error) as exc:
        raise TtsInputError("TTS_OUTPUT_INVALID") from exc


class TtsProvider(Protocol):
    """请求级 TTS Provider 最小协议。"""

    def synthesize(
        self, text: str, target: Path, *, voice_snapshot: Mapping[str, object]
    ) -> None:
        """将一段文本写入调用方指定的 attempt 文件。"""
        ...


class FakeTtsProvider:
    """生成确定性 WAV 的无网络测试 Provider。"""

    def synthesize(
        self, text: str, target: Path, *, voice_snapshot: Mapping[str, object]
    ) -> None:
        """用短正弦波表达非空文本，不读取全局配置。"""

        if not text.strip():
            raise TtsInputError("TTS_TEXT_EMPTY")
        sample_rate = 16_000
        frames = max(1_600, min(16_000, len(text) * 1_600))
        target.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(target), "wb") as output:
            output.setparams((1, 2, sample_rate, frames, "NONE", "not compressed"))
            output.writeframes(
                b"".join(
                    struct.pack(
                        "<h",
                        as_int(800 * math.sin(2 * math.pi * 220 * i / sample_rate)),
                    )
                    for i in range(frames)
                )
            )


@dataclass(slots=True)
class HttpTtsProvider:
    """使用 attempt 冻结 endpoint/secret 的请求级 HTTP TTS Provider。"""

    endpoint: str
    api_key: str
    timeout_seconds: float = 120.0
    transport: httpx.BaseTransport | None = None

    def synthesize(
        self, text: str, target: Path, *, voice_snapshot: Mapping[str, object]
    ) -> None:
        """以稳定供应商音色 code 请求 WAV，不缓存 client 或读取全局配置。"""
        if not self.endpoint.startswith("https://") or not self.api_key:
            raise TtsInputError("TTS_PROVIDER_UNAVAILABLE")
        try:
            with httpx.Client(
                timeout=self.timeout_seconds, transport=self.transport
            ) as client:
                response = client.post(
                    self.endpoint,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json={
                        "text": text,
                        "voice": voice_snapshot.get("provider_voice_code"),
                        "format": voice_snapshot.get("output_format", "wav"),
                        "sample_rate": voice_snapshot.get("sample_rate", 16_000),
                    },
                )
                if response.status_code in {408, 429} or response.status_code >= 500:
                    raise TtsTemporaryError("TTS_TEMPORARY_FAILURE")
                if response.status_code >= 400:
                    raise TtsInputError("TTS_PROVIDER_REJECTED")
                content = response.content
        except TtsInputError:
            raise
        except TtsTemporaryError:
            raise
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise TtsTemporaryError("TTS_TEMPORARY_FAILURE") from exc
        if len(content) <= 44 or len(content) > 100 * 1024 * 1024:
            raise TtsInputError("TTS_OUTPUT_INVALID")
        target.write_bytes(content)


def create_tts_provider(
    provider_code: str, *, voice_snapshot: Mapping[str, object], api_key: str
) -> TtsProvider:
    """只按冻结供应商配置创建 Provider，生产配置缺失时不回退 Fake。"""
    if provider_code == "fake":
        return FakeTtsProvider()
    settings = voice_snapshot.get("provider_settings", {})
    endpoint = settings.get("tts_endpoint") if isinstance(settings, Mapping) else None
    return HttpTtsProvider(endpoint=str(endpoint or ""), api_key=api_key)


@dataclass(slots=True)
class TtsAdapter:
    """校验稳定音色快照并在 attempt workspace 合成配音。"""

    provider: TtsProvider
    artifact_store: ArtifactStore

    def run(
        self,
        *,
        workspace: CoreTaskWorkspace,
        core_task_id: str,
        attempt_no: int,
        voice_id: str,
        voice_snapshot: Mapping[str, object],
        segments: Sequence[Mapping[str, object]],
        lease_guard: Callable[[], None] | None = None,
    ) -> dict[str, object]:
        """按显式 segment 顺序合成一个 WAV 并登记 voice Artifact。"""

        if voice_snapshot.get("voice_id") != voice_id or not segments:
            raise TtsInputError("TTS_INPUT_INVALID")
        texts: list[str] = []
        previous_end = 0.0
        for segment in segments:
            text = segment.get("text")
            start, end = segment.get("start"), segment.get("end")
            if (
                not isinstance(text, str)
                or not text.strip()
                or type(start) not in (int, float)
                or type(end) not in (int, float)
                or not math.isfinite(as_float(start))
                or not math.isfinite(as_float(end))
                or as_float(start) < previous_end
                or as_float(end) <= as_float(start)
            ):
                raise TtsInputError("TTS_SEGMENT_INVALID")
            previous_end = as_float(end)
            texts.append(text.strip())
        if len("\n".join(texts).encode("utf-8")) > 5 * 1024 * 1024:
            raise TtsInputError("TTS_TEXT_TOO_LARGE")
        target = workspace.controlled_path("output", "voice", "wav")
        try:
            self.provider.synthesize(
                "\n".join(texts), target, voice_snapshot=voice_snapshot
            )
        except AdapterError:
            raise
        except Exception as exc:
            raise TtsTemporaryError("TTS_TEMPORARY_FAILURE") from exc
        validate_wav(target)
        try:
            with wave.open(str(target), "rb") as audio:
                if audio.getframerate() != voice_snapshot.get("sample_rate", 16_000):
                    raise TtsInputError("TTS_OUTPUT_INVALID")
        except wave.Error as exc:
            raise TtsInputError("TTS_OUTPUT_INVALID") from exc
        if lease_guard:
            lease_guard()
        artifact = self.artifact_store.upload(
            workspace=workspace,
            local_path=target,
            core_task_id=core_task_id,
            attempt_no=attempt_no,
            kind="voice",
            content_type="audio/wav",
        )
        return {"metadata": {"segments": len(texts)}, "artifacts": [artifact.to_dict()]}
