from __future__ import annotations

from core_api.type_coercion import as_float, as_int

import base64
import binascii
import json
import logging
import math
import struct
import uuid
import wave
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import httpx

from core_api.adapters.narrato.media_probe import AdapterError
from core_api.runtime.artifact_store import ArtifactStore
from core_api.runtime.workspace import CoreTaskWorkspace


logger = logging.getLogger(__name__)


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
    ) -> TtsSynthesisResult | None:
        """将一段文本写入调用方指定的 attempt 文件。"""
        ...


@dataclass(frozen=True, slots=True)
class TtsWordTimestamp:
    word: str
    start_time: float
    end_time: float


@dataclass(frozen=True, slots=True)
class TtsSynthesisResult:
    """供应商原生时间信息；音频文件仍由 target 承载。"""

    duration_ms: int | None = None
    words: tuple[TtsWordTimestamp, ...] = ()


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


@dataclass(slots=True)
class VolcengineTtsProvider:
    """火山引擎语音合成 HTTP v1 适配器。"""

    endpoint: str
    appid: str
    token: str
    cluster: str = "volcano_tts"
    timeout_seconds: float = 120.0
    transport: httpx.BaseTransport | None = None

    def synthesize(
        self, text: str, target: Path, *, voice_snapshot: Mapping[str, object]
    ) -> TtsSynthesisResult:
        """按火山 TTS 合同提交同步 query，并解码响应中的 Base64 音频。"""

        endpoint = self.endpoint.strip()
        appid = self.appid.strip()
        token = self.token.strip()
        cluster = self.cluster.strip() or "volcano_tts"
        voice_type = str(voice_snapshot.get("provider_voice_code") or "").strip()
        if (
            not endpoint.startswith("https://")
            or not appid
            or not token
            or not voice_type
            or not text.strip()
        ):
            raise TtsInputError("TTS_PROVIDER_UNAVAILABLE")

        payload = {
            "app": {"appid": appid, "token": token, "cluster": cluster},
            "user": {"uid": "narrato-core"},
            "audio": {
                "voice_type": voice_type,
                "encoding": str(voice_snapshot.get("output_format") or "wav"),
                "speed_ratio": as_float(voice_snapshot.get("speed_ratio", 1.0)),
                "volume_ratio": as_float(voice_snapshot.get("volume_ratio", 1.0)),
                "pitch_ratio": as_float(voice_snapshot.get("pitch_ratio", 1.0)),
            },
            "request": {
                "reqid": str(uuid.uuid4()),
                "text": text,
                "text_type": "plain",
                "operation": "query",
                "with_timestamp": 1,
            },
        }
        try:
            with httpx.Client(
                timeout=self.timeout_seconds, transport=self.transport
            ) as client:
                response = client.post(
                    endpoint,
                    headers={"Authorization": f"Bearer;{token}"},
                    json=payload,
                )
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise TtsTemporaryError("TTS_TEMPORARY_FAILURE") from exc

        if response.status_code in {408, 429} or response.status_code >= 500:
            logger.warning(
                "volcengine_tts_http_failure http_status=%s voice_type=%s",
                response.status_code,
                voice_type,
            )
            raise TtsTemporaryError("TTS_TEMPORARY_FAILURE")
        try:
            body = response.json()
        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning(
                "volcengine_tts_invalid_response http_status=%s voice_type=%s",
                response.status_code,
                voice_type,
            )
            raise TtsInputError("TTS_PROVIDER_RESPONSE_INVALID") from exc
        if not isinstance(body, Mapping):
            raise TtsInputError("TTS_PROVIDER_RESPONSE_INVALID")

        provider_code = body.get("code")
        provider_message = str(body.get("message") or "")[:500]
        if response.status_code >= 400 or provider_code != 3000:
            logger.warning(
                "volcengine_tts_rejected http_status=%s provider_code=%s provider_message=%s voice_type=%s",
                response.status_code,
                provider_code,
                provider_message,
                voice_type,
            )
            if response.status_code in {408, 429} or (
                isinstance(provider_code, int) and provider_code >= 5000
            ):
                raise TtsTemporaryError("TTS_TEMPORARY_FAILURE")
            raise TtsInputError("TTS_PROVIDER_REJECTED")

        encoded_audio = body.get("data")
        if not isinstance(encoded_audio, str) or not encoded_audio:
            raise TtsInputError("TTS_OUTPUT_INVALID")
        try:
            content = base64.b64decode(encoded_audio, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise TtsInputError("TTS_OUTPUT_INVALID") from exc
        if len(content) <= 44 or len(content) > 100 * 1024 * 1024:
            raise TtsInputError("TTS_OUTPUT_INVALID")
        target.write_bytes(content)
        return _volcengine_tts_timestamps(body)


def _volcengine_tts_timestamps(body: Mapping[str, object]) -> TtsSynthesisResult:
    addition = body.get("addition")
    if not isinstance(addition, Mapping):
        return TtsSynthesisResult()
    raw_duration = addition.get("duration")
    try:
        duration_ms = as_int(raw_duration) if raw_duration is not None else None
    except (TypeError, ValueError):
        duration_ms = None
    frontend: object = addition.get("frontend")
    if isinstance(frontend, str):
        try:
            frontend = json.loads(frontend)
        except json.JSONDecodeError:
            frontend = None
    if not isinstance(frontend, Mapping) or not isinstance(frontend.get("words"), list):
        return TtsSynthesisResult(duration_ms=duration_ms)
    words: list[TtsWordTimestamp] = []
    previous = 0.0
    for raw in frontend["words"]:
        if not isinstance(raw, Mapping):
            continue
        word, start, end = raw.get("word"), raw.get("start_time"), raw.get("end_time")
        if (
            not isinstance(word, str)
            or type(start) not in (int, float)
            or type(end) not in (int, float)
        ):
            continue
        start_f, end_f = as_float(start), as_float(end)
        if (
            not math.isfinite(start_f)
            or not math.isfinite(end_f)
            or start_f < previous
            or end_f < start_f
        ):
            continue
        words.append(TtsWordTimestamp(word, start_f, end_f))
        previous = end_f
    return TtsSynthesisResult(duration_ms=duration_ms, words=tuple(words))


def create_tts_provider(
    provider_code: str, *, voice_snapshot: Mapping[str, object], api_key: str
) -> TtsProvider:
    """只按冻结供应商配置创建 Provider，生产配置缺失时不回退 Fake。"""
    if provider_code == "fake":
        return FakeTtsProvider()
    settings = voice_snapshot.get("provider_settings", {})
    endpoint = settings.get("tts_endpoint") if isinstance(settings, Mapping) else None
    if provider_code == "volcengine":
        try:
            credentials = json.loads(api_key)
        except (json.JSONDecodeError, TypeError):
            credentials = {}
        if not isinstance(credentials, Mapping):
            credentials = {}
        cluster = settings.get("cluster") if isinstance(settings, Mapping) else None
        return VolcengineTtsProvider(
            endpoint=str(endpoint or ""),
            appid=str(credentials.get("appid") or ""),
            token=str(credentials.get("token") or ""),
            cluster=str(cluster or "volcano_tts"),
        )
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
        normalized_segments: list[dict[str, object]] = []
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
            normalized_segments.append(dict(segment))
        if len("\n".join(texts).encode("utf-8")) > 5 * 1024 * 1024:
            raise TtsInputError("TTS_TEXT_TOO_LARGE")
        target = workspace.controlled_path("output", "voice", "wav")
        segment_paths: list[Path] = []
        synthesis_results: list[TtsSynthesisResult | None] = []
        segment_timings: list[dict[str, object]] = []
        for index, (text, segment) in enumerate(
            zip(texts, normalized_segments, strict=True)
        ):
            segment_target = workspace.controlled_path(
                "output", f"voice_segment_{index:04}", "wav"
            )
            segment_voice = dict(voice_snapshot)
            requested_speed = as_float(segment.get("speed", 1.0))
            segment_voice["speed_ratio"] = requested_speed
            segment_voice["volume_ratio"] = as_float(segment.get("volume", 100)) / 100
            try:
                synthesis = self.provider.synthesize(
                    text, segment_target, voice_snapshot=segment_voice
                )
            except AdapterError:
                raise
            except Exception as exc:
                raise TtsTemporaryError("TTS_TEMPORARY_FAILURE") from exc
            validate_wav(segment_target)
            with wave.open(str(segment_target), "rb") as audio:
                frame_rate = audio.getframerate()
                duration_ms = round(audio.getnframes() / frame_rate * 1000)
            allowed = segment.get("allowed_duration_ms")
            tolerance = as_int(segment.get("timing_tolerance_ms", 0))
            adapted_speed = requested_speed
            fit_status = "fit"
            overflow_ms = 0
            if type(allowed) is int and allowed > 0 and duration_ms > allowed + tolerance:
                adapted_speed = min(2.0, requested_speed * duration_ms / allowed)
                _compress_wav_duration(segment_target, allowed / 1000)
                with wave.open(str(segment_target), "rb") as audio:
                    duration_ms = round(audio.getnframes() / audio.getframerate() * 1000)
                overflow_ms = max(0, duration_ms - allowed)
                fit_status = "speed_adjusted" if overflow_ms == 0 else "overflow"
            segment_paths.append(segment_target)
            synthesis_results.append(synthesis)
            if type(allowed) is int:
                segment_timings.append({
                    "segment_id": segment.get("segment_id"),
                    "segment_index": segment.get("segment_index", index),
                    "start_ms": round(as_float(segment["start"]) * 1000),
                    "end_ms": round(as_float(segment["end"]) * 1000),
                    "tts_duration_ms": duration_ms,
                    "allowed_duration_ms": allowed,
                    "adapted_speed": adapted_speed,
                    "timing_fit_status": fit_status,
                    "timing_overflow_ms": overflow_ms,
                })
        _concat_wav_segments(segment_paths, target)
        validate_wav(target)
        synthesis = next(
            (item for item in synthesis_results if isinstance(item, TtsSynthesisResult)),
            None,
        )
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
        metadata: dict[str, object] = {"segments": len(texts)}
        word_timestamps: list[dict[str, object]] = []
        for index, item in enumerate(synthesis_results):
            if not isinstance(item, TtsSynthesisResult):
                continue
            for word in item.words:
                word_timestamps.append({
                    "segment_index": index,
                    "word": word.word,
                    "start_time": word.start_time,
                    "end_time": word.end_time,
                })
        if isinstance(synthesis, TtsSynthesisResult):
            metadata["word_timestamps"] = word_timestamps
        if segment_timings:
            metadata["segment_timings"] = segment_timings
        return {"metadata": metadata, "artifacts": [artifact.to_dict()]}


def _compress_wav_duration(path: Path, target_seconds: float) -> None:
    """确定性压缩 PCM 帧数；用于翻译 TTS 超时长后的渲染前适配。"""

    with wave.open(str(path), "rb") as source:
        params = source.getparams()
        frames = source.readframes(source.getnframes())
    frame_width = params.nchannels * params.sampwidth
    source_count = len(frames) // frame_width
    target_count = max(1, min(source_count, round(target_seconds * params.framerate)))
    if target_count >= source_count:
        return
    output = bytearray(target_count * frame_width)
    for index in range(target_count):
        source_index = min(source_count - 1, int(index * source_count / target_count))
        output[index * frame_width : (index + 1) * frame_width] = frames[
            source_index * frame_width : (source_index + 1) * frame_width
        ]
    with wave.open(str(path), "wb") as target:
        target.setparams(params)
        target.writeframes(bytes(output))


def _concat_wav_segments(paths: Sequence[Path], target: Path) -> None:
    if not paths:
        raise TtsInputError("TTS_OUTPUT_INVALID")
    params = None
    payloads: list[bytes] = []
    for path in paths:
        with wave.open(str(path), "rb") as audio:
            current = audio.getparams()
            signature = (
                current.nchannels,
                current.sampwidth,
                current.framerate,
                current.comptype,
            )
            if params is None:
                params = current
                expected = signature
            elif signature != expected:
                raise TtsInputError("TTS_OUTPUT_INVALID")
            payloads.append(audio.readframes(audio.getnframes()))
    assert params is not None
    with wave.open(str(target), "wb") as output:
        output.setparams(params)
        for payload in payloads:
            output.writeframes(payload)
