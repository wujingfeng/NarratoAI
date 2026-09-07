from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from typing import Any, cast
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class CoreClientError(RuntimeError):
    """Core 媒体探测请求未能安全完成。"""


class CoreClientRejectedError(CoreClientError):
    """Core 已收到请求，但拒绝了媒体声明或媒体校验。"""

    def __init__(
        self,
        message: str,
        *,
        code: str = "CORE_REQUEST_REJECTED",
        http_status: int = 422,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.http_status = http_status


def _core_rejected_error(error: HTTPError) -> CoreClientRejectedError:
    """从 Core 安全错误信封保留真实错误码，避免被统一文案吞掉。"""

    code = "CORE_REQUEST_REJECTED"
    message = "Core task request was rejected"
    try:
        payload = json.loads(error.read(65_536) or b"{}")
    except (OSError, ValueError, TypeError):
        payload = {}
    raw_code = payload.get("code") if isinstance(payload, dict) else None
    raw_message = payload.get("message") if isinstance(payload, dict) else None
    if isinstance(raw_code, str) and 1 <= len(raw_code) <= 128:
        code = raw_code
    if isinstance(raw_message, str) and raw_message.strip():
        message = raw_message.strip()[:500]
    return CoreClientRejectedError(
        message,
        code=code,
        http_status=error.code,
    )


def _duration_seconds(payload: object) -> float | None:
    """仅接受 Core 已验证媒体探测返回的正有限时长。"""

    if not isinstance(payload, dict):
        return None
    duration = payload.get("duration_seconds")
    if (
        isinstance(duration, bool)
        or not isinstance(duration, (int, float))
        or not math.isfinite(duration)
        or duration <= 0
    ):
        return None
    return float(duration)


@dataclass(frozen=True, slots=True)
class MediaProbeResult:
    """Core 返回的媒体校验结论；None 表示异步结果尚未返回。"""

    valid: bool | None
    core_task_id: str | None = None
    duration_seconds: float | None = None


@dataclass(frozen=True, slots=True)
class CoreTaskResult:
    """Core 原子任务的最小状态投影，供 Business 工作流轮询。"""

    core_task_id: str
    status: str
    state_version: int
    progress: int = 0
    result: object | None = None
    artifacts: tuple[dict[str, object], ...] = ()
    error: dict[str, object] | None = None


@dataclass(frozen=True, slots=True)
class CoreVoiceCapability:
    """Core 能力目录中可直接用于创建渲染任务的稳定音色。"""

    voice_id: str
    name: str
    provider_code: str
    languages: tuple[str, ...]
    gender: str | None
    styles: tuple[str, ...]
    sample_url: str | None


@dataclass(frozen=True, slots=True)
class CoreJianyingResource:
    """发送给 Core 的已登记剪映资源。"""

    kind: str
    zip_path: str
    url: str
    size: int
    checksum: str
    content_type: str
    width: int | None = None
    height: int | None = None
    duration: float | None = None


@dataclass(frozen=True, slots=True)
class CoreJianyingManifestFile:
    """Core 返回的一项内联或 CDN Manifest 文件。"""

    zip_path: str
    content: str | None
    content_base64: str | None
    url: str | None
    size: int | None
    checksum: str | None
    content_type: str | None

    @classmethod
    def from_payload(cls, payload: object) -> CoreJianyingManifestFile:
        if not isinstance(payload, dict):
            raise CoreClientError("Core Jianying manifest response is invalid")
        values = {key: payload.get(key) for key in cls.__dataclass_fields__}
        if not isinstance(values["zip_path"], str) or not values["zip_path"]:
            raise CoreClientError("Core Jianying manifest response is invalid")
        if any(
            value is not None and not isinstance(value, expected)
            for value, expected in (
                (values["content"], str),
                (values["content_base64"], str),
                (values["url"], str),
                (values["size"], int),
                (values["checksum"], str),
                (values["content_type"], str),
            )
        ):
            raise CoreClientError("Core Jianying manifest response is invalid")
        return cls(
            content=cast(str | None, values["content"]),
            content_base64=cast(str | None, values["content_base64"]),
            zip_path=values["zip_path"],
            url=cast(str | None, values["url"]),
            size=cast(int | None, values["size"]),
            checksum=cast(str | None, values["checksum"]),
            content_type=cast(str | None, values["content_type"]),
        )


@dataclass(frozen=True, slots=True)
class CoreJianyingManifest:
    """Core 无状态生成的剪映基础文件和资源映射。"""

    template_version: str
    package_name: str
    files: tuple[CoreJianyingManifestFile, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "template_version": self.template_version,
            "package_name": self.package_name,
            "files": [asdict(item) for item in self.files],
        }


class HttpCoreClient:
    """只调用 Core 的媒体探测原子接口。"""

    def __init__(self, *, base_url: str, request_token: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.request_token = request_token

    def probe_media(
        self,
        *,
        source_url: str,
        media_type: str,
        declared_extension: str,
        caller_task_id: str,
    ) -> MediaProbeResult:
        """提交媒体探测，并兼容同步 Fake 与 Core 的 202 异步响应。"""

        if not self.request_token:
            raise CoreClientError("Core request token is not configured")
        body = json.dumps(
            {
                "source_url": source_url,
                "media_type": media_type,
                "declared_extension": declared_extension,
                "caller_task_id": caller_task_id,
            }
        ).encode()
        request = Request(
            f"{self.base_url}/api/v1/media-probe/tasks",
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.request_token}",
                "Content-Type": "application/json",
                "X-Idempotency-Key": caller_task_id,
            },
        )
        try:
            with urlopen(request, timeout=10) as response:
                payload = json.loads(response.read() or b"{}")
                status = response.status
        except HTTPError as error:
            # 422 是 Core 对请求声明的明确拒绝，不应伪装成服务不可用；认证、路由
            # 和服务端错误仍按不可用处理，避免将部署问题错误归因于用户文件。
            if error.code == 422:
                raise _core_rejected_error(error) from error
            raise CoreClientError("Core media probe request failed") from error
        except (URLError, TimeoutError, json.JSONDecodeError) as error:
            raise CoreClientError("Core media probe request failed") from error
        if status == 202:
            data = payload.get("data", payload)
            task_id = data.get("core_task_id") if isinstance(data, dict) else None
            if not isinstance(task_id, str) or not task_id:
                raise CoreClientError("Core media probe response is invalid")
            return MediaProbeResult(valid=None, core_task_id=task_id)
        data = payload.get("data", payload)
        valid = data.get("valid") if isinstance(data, dict) else None
        if not isinstance(valid, bool):
            raise CoreClientError("Core media probe response is invalid")
        return MediaProbeResult(valid=valid, duration_seconds=_duration_seconds(data))

    def get_probe_result(self, core_task_id: str) -> MediaProbeResult:
        """查询已提交 Core 原子任务的终态，不创建工作流。"""
        request = Request(
            f"{self.base_url}/api/v1/tasks/{core_task_id}",
            headers={"Authorization": f"Bearer {self.request_token}"},
        )
        try:
            with urlopen(request, timeout=10) as response:
                payload = json.loads(response.read() or b"{}")
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as error:
            raise CoreClientError("Core media probe query failed") from error
        data = payload.get("data", payload)
        state = data.get("status") if isinstance(data, dict) else None
        if state == "succeeded":
            result = data.get("result") if isinstance(data, dict) else None
            return MediaProbeResult(
                valid=True,
                core_task_id=core_task_id,
                duration_seconds=_duration_seconds(result),
            )
        if state == "failed":
            return MediaProbeResult(valid=False, core_task_id=core_task_id)
        return MediaProbeResult(valid=None, core_task_id=core_task_id)

    def submit_asr_batch(
        self, *, sources: list[dict[str, object]], caller_task_id: str
    ) -> str:
        """按素材顺序提交一次最多五条来源的 ASR 任务。"""

        return self._submit_task(
            "/api/v1/asr/tasks",
            {"sources": sources, "caller_task_id": caller_task_id},
            caller_task_id,
        )

    def submit_audio_understanding(
        self,
        *,
        model_id: str,
        sources: list[dict[str, object]],
        caller_task_id: str,
    ) -> str:
        """短剧专用：直接把公网视频 URL 交给方舟理解内嵌音频。"""

        return self._submit_task(
            "/api/v1/audio-understanding/tasks",
            {
                "model_id": model_id,
                "sources": sources,
                "language": "zh-CN",
                "fps": 1,
                "min_frame_tokens": 64,
                "min_frame_tokens_mode": "provider_default",
                "caller_task_id": caller_task_id,
            },
            caller_task_id,
        )

    def submit_video_analysis(
        self,
        *,
        model_id: str,
        sources: list[dict[str, object]],
        caller_task_id: str,
        config_snapshot: dict[str, object],
    ) -> str:
        return self._submit_task(
            "/api/v1/video-analysis/tasks",
            {
                "model_id": model_id,
                "sources": sources,
                "language": "zh-CN",
                "config_snapshot": config_snapshot,
                "caller_task_id": caller_task_id,
            },
            caller_task_id,
        )

    def submit_video_translation(
        self,
        *,
        model_id: str,
        subtitle_input: dict[str, object],
        target_language: str,
        caller_task_id: str,
    ) -> str:
        """提交一条 SRT 时间轴翻译任务，绝不回退为视频剧情分析。"""

        return self._submit_task(
            "/api/v1/video-translation/tasks",
            {
                "model_id": model_id,
                "source": subtitle_input,
                "target_language": target_language,
                "caller_task_id": caller_task_id,
            },
            caller_task_id,
        )

    def submit_translation_rewrite(
        self,
        *,
        model_id: str,
        target_language: str,
        segments: list[dict[str, object]],
        caller_task_id: str,
    ) -> str:
        """只压缩 TTS 超限译文，不重新执行 ASR 或整批字幕翻译。"""

        return self._submit_task(
            "/api/v1/video-translation/rewrite-tasks",
            {
                "model_id": model_id,
                "target_language": target_language,
                "segments": segments,
                "caller_task_id": caller_task_id,
            },
            caller_task_id,
        )

    def submit_script_generation(
        self,
        *,
        model_id: str,
        analysis_artifact: dict[str, object],
        sources: list[dict[str, object]],
        caller_task_id: str,
        config_snapshot: dict[str, object],
    ) -> str:
        return self._submit_task(
            "/api/v1/script-generation/tasks",
            {
                "model_id": model_id,
                "analysis_artifact": analysis_artifact,
                "sources": sources,
                "language": "zh-CN",
                "config_snapshot": config_snapshot,
                "caller_task_id": caller_task_id,
            },
            caller_task_id,
        )

    def submit_video_render(
        self,
        *,
        snapshot_id: str,
        voice_id: str,
        sources: list[dict[str, object]],
        timeline: list[dict[str, object]],
        render_config: dict[str, object],
        caller_task_id: str,
    ) -> str:
        return self._submit_task(
            "/api/v1/video-render/tasks",
            {
                "snapshot_id": snapshot_id,
                "voice_id": voice_id,
                "sources": sources,
                "timeline": timeline,
                "render_config": render_config,
                "caller_task_id": caller_task_id,
            },
            caller_task_id,
        )

    def submit_tts_preview(
        self,
        *,
        voice_id: str,
        language: str,
        text: str,
        speed: float,
        volume: int,
        caller_task_id: str,
    ) -> str:
        """创建单段翻译试听任务。

        speed/volume 是 Core TTS 的明确字段，Core 会将其冻结为供应商请求参数。
        不得发送未声明的 ``translation_preview`` 包装字段。
        """
        return self._submit_task(
            "/api/v1/tts/tasks",
            {
                "voice_id": voice_id,
                "language": language,
                "output_format": "wav",
                "sample_rate": 16000,
                "speed": speed,
                "volume": volume,
                "segments": [{"text": text, "start": 0, "end": 60}],
                "caller_task_id": caller_task_id,
            },
            caller_task_id,
        )

    def submit_translation_tts(
        self,
        *,
        voice_id: str,
        language: str,
        segments: list[dict[str, object]],
        caller_task_id: str,
    ) -> str:
        """提交确认台词后的整段配音任务，不能误走视频分析接口。"""

        return self._submit_task(
            "/api/v1/tts/tasks",
            {
                "voice_id": voice_id,
                "language": language,
                "output_format": "wav",
                "sample_rate": 16000,
                "segments": segments,
                "caller_task_id": caller_task_id,
            },
            caller_task_id,
        )

    def get_task_result(self, core_task_id: str) -> CoreTaskResult:
        request = Request(
            f"{self.base_url}/api/v1/tasks/{core_task_id}",
            headers={"Authorization": f"Bearer {self.request_token}"},
        )
        try:
            with urlopen(request, timeout=10) as response:
                payload = json.loads(response.read() or b"{}")
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as error:
            raise CoreClientError("Core task query failed") from error
        data = payload.get("data", payload)
        if (
            not isinstance(data, dict)
            or not isinstance(data.get("core_task_id"), str)
            or not isinstance(data.get("status"), str)
        ):
            raise CoreClientError("Core task response is invalid")
        state_version = data.get("state_version")
        progress = data.get("progress", 0)
        if (
            isinstance(state_version, bool)
            or not isinstance(state_version, int)
            or state_version < 0
        ):
            raise CoreClientError("Core task response is invalid")
        if (
            isinstance(progress, bool)
            or not isinstance(progress, int)
            or not 0 <= progress <= 100
        ):
            raise CoreClientError("Core task response is invalid")
        artifacts = data.get("artifacts", [])
        raw_error = data.get("error")
        error: dict[str, object] | None = None
        if isinstance(raw_error, dict) and isinstance(raw_error.get("code"), str):
            error = {"code": raw_error["code"]}
            if isinstance(raw_error.get("retryable"), bool):
                error["retryable"] = raw_error["retryable"]
            if isinstance(raw_error.get("reason"), str):
                error["reason"] = raw_error["reason"]
            for key in ("details", "diagnostics"):
                if isinstance(raw_error.get(key), dict):
                    error[key] = raw_error[key]
        return CoreTaskResult(
            data["core_task_id"],
            data["status"],
            state_version,
            progress,
            data.get("result"),
            tuple(item for item in artifacts if isinstance(item, dict)),
            error,
        )

    def get_voice_capabilities(self) -> tuple[CoreVoiceCapability, ...]:
        """读取 Core 已启用、已配置密钥且真实可调用的音色目录。"""

        if not self.request_token:
            raise CoreClientError("Core request token is not configured")
        request = Request(
            f"{self.base_url}/api/v1/capabilities",
            headers={"Authorization": f"Bearer {self.request_token}"},
        )
        try:
            with urlopen(request, timeout=10) as response:
                payload = json.loads(response.read() or b"{}")
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as error:
            raise CoreClientError("Core capability catalog request failed") from error
        data = payload.get("data", payload) if isinstance(payload, dict) else None
        voices = data.get("voices") if isinstance(data, dict) else None
        if (
            not isinstance(data, dict)
            or not isinstance(data.get("version"), str)
            or not isinstance(voices, list)
        ):
            raise CoreClientError("Core capability catalog response is invalid")
        result: list[CoreVoiceCapability] = []
        seen: set[str] = set()
        for item in voices:
            if not isinstance(item, dict):
                raise CoreClientError("Core capability catalog response is invalid")
            voice_id, name = item.get("voice_id"), item.get("name")
            provider_code = item.get("provider_code")
            languages = item.get("languages")
            gender = item.get("gender")
            styles = item.get("styles")
            sample_url = item.get("sample_url")
            if (
                not isinstance(voice_id, str)
                or not voice_id
                or voice_id in seen
                or not isinstance(name, str)
                or not name
                or not isinstance(provider_code, str)
                or not provider_code
                or not isinstance(languages, list)
                or any(not isinstance(value, str) or not value for value in languages)
                or (gender is not None and (not isinstance(gender, str) or not gender))
                or not isinstance(styles, list)
                or any(not isinstance(value, str) or not value for value in styles)
                or (sample_url is not None and not isinstance(sample_url, str))
            ):
                raise CoreClientError("Core capability catalog response is invalid")
            seen.add(voice_id)
            result.append(
                CoreVoiceCapability(
                    voice_id=voice_id,
                    name=name,
                    provider_code=provider_code,
                    languages=tuple(languages),
                    gender=gender,
                    styles=tuple(styles),
                    sample_url=sample_url or None,
                )
            )
        return tuple(result)

    def _submit_task(
        self, path: str, body_data: dict[str, object], idempotency_key: str
    ) -> str:
        if not self.request_token:
            raise CoreClientError("Core request token is not configured")
        request = Request(
            f"{self.base_url}{path}",
            data=json.dumps(body_data).encode(),
            method="POST",
            headers={
                "Authorization": f"Bearer {self.request_token}",
                "Content-Type": "application/json",
                "X-Idempotency-Key": idempotency_key,
            },
        )
        try:
            with urlopen(request, timeout=15) as response:
                payload = json.loads(response.read() or b"{}")
        except HTTPError as error:
            # 422 代表 Core 已经可用，但拒绝了当前任务契约或参数；调用方不能把它
            # 伪装成 503 服务不可用，否则前端会引导用户错误地排查服务状态。
            if error.code in {409, 422}:
                raise _core_rejected_error(error) from error
            raise CoreClientError("Core task submission failed") from error
        except (URLError, TimeoutError, json.JSONDecodeError) as error:
            raise CoreClientError("Core task submission failed") from error
        data = payload.get("data", payload)
        task_id = data.get("core_task_id") if isinstance(data, dict) else None
        if not isinstance(task_id, str) or not task_id:
            raise CoreClientError("Core task submission response is invalid")
        return task_id

    def build_jianying_manifest(
        self,
        *,
        snapshot_id: str,
        timeline: list[dict[str, Any]],
        resources: list[CoreJianyingResource],
    ) -> CoreJianyingManifest:
        """调用 Core 同步构建无状态剪映 Manifest，不创建 ZIP 或文件。"""

        if not self.request_token:
            raise CoreClientError("Core request token is not configured")
        body = json.dumps(
            {
                "snapshot_id": snapshot_id,
                "timeline": timeline,
                "resources": [asdict(resource) for resource in resources],
            }
        ).encode()
        request = Request(
            f"{self.base_url}/api/v1/jianying/manifests/build",
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.request_token}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urlopen(request, timeout=10) as response:
                payload = json.loads(response.read() or b"{}")
                status = response.status
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as error:
            raise CoreClientError("Core Jianying manifest request failed") from error
        data = payload.get("data", payload) if isinstance(payload, dict) else None
        if status != 200 or not isinstance(data, dict):
            raise CoreClientError("Core Jianying manifest response is invalid")
        template_version, package_name, files = (
            data.get("template_version"),
            data.get("package_name"),
            data.get("files"),
        )
        if (
            not isinstance(template_version, str)
            or not template_version
            or not isinstance(package_name, str)
            or not package_name
            or not isinstance(files, list)
        ):
            raise CoreClientError("Core Jianying manifest response is invalid")
        return CoreJianyingManifest(
            template_version=template_version,
            package_name=package_name,
            files=tuple(CoreJianyingManifestFile.from_payload(item) for item in files),
        )
