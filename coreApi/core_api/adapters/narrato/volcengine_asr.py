from __future__ import annotations

import time
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol
from urllib.parse import urljoin, urlsplit

import requests

from core_api.adapters.narrato.asr import AsrTemporaryError
from core_api.adapters.narrato.media_probe import AdapterError
from core_api.tasks.asr_jobs import AsrProviderJobStore


_SUBMIT_URL = "https://openspeech.bytedance.com/api/v1/auc/submit"
_QUERY_URL = "https://openspeech.bytedance.com/api/v1/auc/query"
_SUCCESS_CODE = 1000
_PENDING_CODES = frozenset({2000, 2001})
_INPUT_CODES = frozenset({1010, 1011, 1012, 1013, 1014})
_TEMPORARY_CODES = frozenset({1003, 1005, 1006, 1015, 1020, 1021, 1022, 1099})

logger = logging.getLogger(__name__)


class VolcengineAsrAuthError(AdapterError):
    """火山录音文件识别鉴权或资源权限不可用。"""

    code = "ASR_PROVIDER_AUTH_FAILED"


class VolcengineAsrRequestError(AdapterError):
    """火山录音文件识别拒绝了请求参数。"""

    code = "ASR_PROVIDER_REQUEST_INVALID"


class VolcengineAsrQuotaError(AdapterError):
    """火山录音文件识别调用额度已经耗尽。"""

    code = "ASR_PROVIDER_QUOTA_EXCEEDED"


class VolcengineAsrTemporaryError(AsrTemporaryError):
    """火山录音文件识别暂时不可用，可由 Core 自动重试。"""

    code = "ASR_PROVIDER_TEMPORARY_FAILURE"


class VolcengineAsrInputError(AdapterError):
    """火山录音文件识别拒绝了已冻结的媒体输入。"""

    code = "ASR_PROVIDER_INPUT_REJECTED"


class VolcengineAsrResultError(AdapterError):
    """火山返回了无法消费的结果。"""

    code = "ASR_PROVIDER_RESULT_INVALID"


class _HttpSession(Protocol):
    def post(
        self,
        url: str,
        *,
        json: dict[str, object],
        headers: dict[str, str],
        timeout: int,
    ) -> Any: ...


def _milliseconds_to_srt(milliseconds: int) -> str:
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, millis = divmod(remainder, 1_000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


def volcengine_result_to_srt(payload: dict[str, object]) -> str:
    """把火山 AUC 成功结果中的 utterances 规范化成 SRT。"""

    response = payload.get("resp")
    if not isinstance(response, dict):
        response = payload.get("result")
    if not isinstance(response, dict):
        raise VolcengineAsrInputError("ASR_PROVIDER_RESULT_INVALID")
    utterances = response.get("utterances")
    if not isinstance(utterances, list) or not utterances:
        raise VolcengineAsrInputError("ASR_PROVIDER_RESULT_INVALID")

    lines: list[str] = []
    previous_end = -1
    for index, utterance in enumerate(utterances, start=1):
        if not isinstance(utterance, dict):
            raise VolcengineAsrInputError("ASR_PROVIDER_RESULT_INVALID")
        text = utterance.get("text")
        start = utterance.get("start_time")
        end = utterance.get("end_time")
        if (
            not isinstance(text, str)
            or not text.strip()
            or isinstance(start, bool)
            or isinstance(end, bool)
            or not isinstance(start, (int, float))
            or not isinstance(end, (int, float))
        ):
            raise VolcengineAsrInputError("ASR_PROVIDER_RESULT_INVALID")
        start_ms, end_ms = int(start), int(end)
        if start_ms < 0 or end_ms <= start_ms or start_ms < previous_end:
            raise VolcengineAsrInputError("ASR_PROVIDER_RESULT_INVALID")
        previous_end = end_ms
        lines.extend(
            [
                str(index),
                f"{_milliseconds_to_srt(start_ms)} --> {_milliseconds_to_srt(end_ms)}",
                text.strip(),
                "",
            ]
        )
    return "\n".join(lines)


@dataclass(slots=True)
class VolcengineAsrTranscriber:
    """通过火山录音文件识别标准版将受控 CDN URL 转为 SRT。"""

    appid: str
    token: str
    cluster: str
    poll_interval_seconds: float = 2.0
    total_timeout_seconds: float = 600.0
    language: str = "zh-CN"
    use_itn: bool = True
    use_punc: bool = True
    with_speaker_info: bool = False
    session: _HttpSession | None = None
    callback_base_url: str = ""
    job_store: AsrProviderJobStore | None = None
    _client: _HttpSession = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.appid = self.appid.strip()
        self.token = self.token.strip()
        self.cluster = self.cluster.strip()
        if not self.appid or not self.token or not self.cluster:
            raise VolcengineAsrAuthError("ASR_PROVIDER_NOT_CONFIGURED")
        if self.poll_interval_seconds <= 0 or self.total_timeout_seconds <= 0:
            raise VolcengineAsrInputError("ASR_PROVIDER_CONFIG_INVALID")
        parsed_callback = urlsplit(self.callback_base_url)
        if (
            parsed_callback.scheme not in {"http", "https"}
            or not parsed_callback.hostname
            or parsed_callback.username
            or parsed_callback.password
            or parsed_callback.query
            or parsed_callback.fragment
        ):
            raise VolcengineAsrInputError("ASR_PROVIDER_CALLBACK_CONFIG_INVALID")
        if self.job_store is None:
            raise VolcengineAsrInputError("ASR_PROVIDER_JOB_STORE_REQUIRED")
        self.callback_base_url = self.callback_base_url.rstrip("/") + "/"
        self._client = self.session or requests.Session()

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer; {self.token}",
            "Content-Type": "application/json",
        }

    def _app(self) -> dict[str, str]:
        return {"appid": self.appid, "token": self.token, "cluster": self.cluster}

    @staticmethod
    def _source_path(source_url: str | None) -> str:
        """仅记录 URL path，避免把签名参数或完整媒体地址写入日志。"""

        if not source_url:
            return "-"
        return urlsplit(source_url).path or "/"

    @staticmethod
    def _endpoint_path(url: str) -> str:
        return urlsplit(url).path or "/"

    @classmethod
    def _response(
        cls,
        response: Any,
        *,
        phase: str,
        endpoint_url: str,
        source_url: str | None = None,
    ) -> dict[str, object]:
        endpoint_path = cls._endpoint_path(endpoint_url)
        source_path = cls._source_path(source_url)
        payload: object | None = None
        json_error: Exception | None = None
        try:
            payload = response.json()
        except (TypeError, ValueError) as exc:
            json_error = exc

        http_status = getattr(response, "status_code", None)
        try:
            response.raise_for_status()
        except requests.RequestException as exc:
            upstream = getattr(exc, "response", None)
            provider_code = (
                cls._response_code(payload) if isinstance(payload, dict) else None
            )
            logger.warning(
                "volcengine_asr_request_failed phase=%s endpoint_path=%s source_path=%s http_status=%s provider_code=%s error_type=%s tt_logid=%s",
                phase,
                endpoint_path,
                source_path,
                http_status or getattr(upstream, "status_code", None),
                provider_code,
                type(exc).__name__,
                getattr(upstream, "headers", {}).get("X-Tt-Logid"),
            )
            if isinstance(payload, dict) and provider_code is not None:
                cls._raise_for_terminal_code(payload)
            if http_status in {401, 403}:
                raise VolcengineAsrAuthError("ASR_PROVIDER_AUTH_FAILED") from exc
            if http_status == 429 or (isinstance(http_status, int) and http_status >= 500):
                raise VolcengineAsrTemporaryError(
                    "ASR_PROVIDER_TEMPORARY_FAILURE"
                ) from exc
            if isinstance(http_status, int) and 400 <= http_status < 500:
                raise VolcengineAsrRequestError(
                    "ASR_PROVIDER_REQUEST_INVALID"
                ) from exc
            raise VolcengineAsrTemporaryError("ASR_PROVIDER_TEMPORARY_FAILURE") from exc

        if json_error is not None:
            logger.warning(
                "volcengine_asr_response_invalid phase=%s endpoint_path=%s source_path=%s error_type=%s",
                phase,
                endpoint_path,
                source_path,
                type(json_error).__name__,
            )
            raise VolcengineAsrTemporaryError(
                "ASR_PROVIDER_TEMPORARY_FAILURE"
            ) from json_error
        if not isinstance(payload, dict):
            logger.warning(
                "volcengine_asr_response_invalid phase=%s endpoint_path=%s source_path=%s error_type=unexpected_payload",
                phase,
                endpoint_path,
                source_path,
            )
            raise VolcengineAsrTemporaryError("ASR_PROVIDER_TEMPORARY_FAILURE")
        logger.info(
            "volcengine_asr_response phase=%s endpoint_path=%s source_path=%s http_status=%s provider_code=%s tt_logid=%s",
            phase,
            endpoint_path,
            source_path,
            getattr(response, "status_code", None),
            cls._response_code(payload),
            getattr(response, "headers", {}).get("X-Tt-Logid"),
        )
        return payload

    @staticmethod
    def _response_code(payload: dict[str, object]) -> int | None:
        response = payload.get("resp")
        if not isinstance(response, dict):
            return None
        code = response.get("code")
        if isinstance(code, int) and not isinstance(code, bool):
            return code
        # 火山标准版文档中的 code 示例是字符串 "1000"。此前仅接受 int，
        # 导致成功提交也会被误判为 temporary failure 并耗尽重试。
        if isinstance(code, str) and code.isdecimal():
            return int(code)
        return None

    @classmethod
    def _raise_for_terminal_code(cls, payload: dict[str, object]) -> None:
        code = cls._response_code(payload)
        if code == 1001:
            raise VolcengineAsrRequestError("ASR_PROVIDER_REQUEST_INVALID")
        if code == 1002:
            raise VolcengineAsrAuthError("ASR_PROVIDER_AUTH_FAILED")
        if code == 1004:
            raise VolcengineAsrQuotaError("ASR_PROVIDER_QUOTA_EXCEEDED")
        if code in _INPUT_CODES:
            raise VolcengineAsrInputError("ASR_PROVIDER_INPUT_REJECTED")
        if code in _TEMPORARY_CODES:
            raise VolcengineAsrTemporaryError("ASR_PROVIDER_TEMPORARY_FAILURE")
        raise VolcengineAsrTemporaryError("ASR_PROVIDER_TEMPORARY_FAILURE")

    def __call__(
        self,
        source_url: str,
        declared_format: str,
        subtitle_file: str,
        *,
        core_task_id: str,
        source_index: int,
        source_asset_id: str,
        lease_guard: Callable[[], None] | None = None,
    ) -> str:
        assert self.job_store is not None
        job = self.job_store.get_or_create(
            core_task_id=core_task_id,
            source_index=source_index,
            source_asset_id=source_asset_id,
        )
        callback_url = urljoin(
            self.callback_base_url,
            f"api/v1/asr/callbacks/{job.callback_key}",
        )
        submit = {
            "app": self._app(),
            "user": {"uid": "narrato-core"},
            "audio": {"url": source_url, "format": declared_format},
            "request": {"callback": callback_url},
            "additions": {
                "language": self.language,
                "use_itn": "True" if self.use_itn else "False",
                "use_punc": "True" if self.use_punc else "False",
                "with_speaker_info": ("True" if self.with_speaker_info else "False"),
                "enable_query": "True",
            },
        }
        task_id = job.provider_task_id
        if not task_id:
            if lease_guard is not None:
                lease_guard()
            logger.info(
                "volcengine_asr_request phase=submit endpoint_path=%s source_path=%s source_host=%s source_format=%s",
                self._endpoint_path(_SUBMIT_URL),
                self._source_path(source_url),
                urlsplit(source_url).hostname,
                declared_format,
            )
            payload = self._response(
                self._client.post(
                    _SUBMIT_URL, json=submit, headers=self._headers(), timeout=30
                ),
                phase="submit",
                endpoint_url=_SUBMIT_URL,
                source_url=source_url,
            )
            if self._response_code(payload) != _SUCCESS_CODE:
                self._raise_for_terminal_code(payload)
            response = payload.get("resp")
            task_id = response.get("id") if isinstance(response, dict) else None
            if not isinstance(task_id, str) or not task_id:
                raise VolcengineAsrResultError("ASR_PROVIDER_TASK_ID_MISSING")
            job = self.job_store.mark_submitted(job.id, task_id)

        deadline = time.monotonic() + self.total_timeout_seconds
        while time.monotonic() < deadline:
            if lease_guard is not None:
                lease_guard()
            job = self.job_store.get(job.id)
            if job.status == "succeeded" and job.response_payload is not None:
                srt = volcengine_result_to_srt(job.response_payload)
                Path(subtitle_file).write_text(srt, encoding="utf-8")
                return subtitle_file
            if job.status == "failed" and job.response_payload is not None:
                self._raise_for_terminal_code(job.response_payload)
            time.sleep(self.poll_interval_seconds)
            if lease_guard is not None:
                lease_guard()
            query = {
                "appid": self.appid,
                "token": self.token,
                "cluster": self.cluster,
                "id": task_id,
            }
            logger.info(
                "volcengine_asr_request phase=query endpoint_path=%s source_path=%s",
                self._endpoint_path(_QUERY_URL),
                self._source_path(source_url),
            )
            payload = self._response(
                self._client.post(
                    _QUERY_URL, json=query, headers=self._headers(), timeout=30
                ),
                phase="query",
                endpoint_url=_QUERY_URL,
                source_url=source_url,
            )
            code = self._response_code(payload)
            if code in _PENDING_CODES:
                self.job_store.record_provider_response(
                    job.id, payload=payload, status="submitted"
                )
                continue
            if code != _SUCCESS_CODE:
                self.job_store.record_provider_response(
                    job.id,
                    payload=payload,
                    status="failed",
                    error={
                        "code": "ASR_PROVIDER_REJECTED",
                        "provider_code": code,
                    },
                )
                self._raise_for_terminal_code(payload)
            self.job_store.record_provider_response(
                job.id, payload=payload, status="succeeded"
            )
            srt = volcengine_result_to_srt(payload)
            Path(subtitle_file).write_text(srt, encoding="utf-8")
            return subtitle_file
        raise VolcengineAsrTemporaryError("ASR_PROVIDER_POLL_TIMEOUT")
