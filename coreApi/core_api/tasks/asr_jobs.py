from __future__ import annotations

import secrets
from dataclasses import dataclass
from typing import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from core_api.ids import new_time_ordered_id
from core_api.tasks.models import AsrProviderJob, CoreArtifact


@dataclass(frozen=True, slots=True)
class AsrJobSnapshot:
    id: str
    callback_key: str
    provider_task_id: str | None
    prepared_audio_url: str | None
    status: str
    response_payload: dict[str, object] | None
    error: dict[str, object] | None


class AsrProviderJobStore:
    """用短事务持久化第三方 ASR 状态，供 Worker 与 Callback 并发使用。"""

    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self.session_factory = session_factory

    @staticmethod
    def _snapshot(row: AsrProviderJob) -> AsrJobSnapshot:
        return AsrJobSnapshot(
            id=row.id,
            callback_key=row.callback_key,
            provider_task_id=row.provider_task_id,
            prepared_audio_url=row.prepared_audio_url,
            status=row.status,
            response_payload=row.response_payload,
            error=row.error,
        )

    def get_or_create(
        self, *, core_task_id: str, source_index: int, source_asset_id: str
    ) -> AsrJobSnapshot:
        with self.session_factory() as session:
            row = session.scalar(
                select(AsrProviderJob).where(
                    AsrProviderJob.core_task_id == core_task_id,
                    AsrProviderJob.source_index == source_index,
                )
            )
            if row is None:
                row = AsrProviderJob(
                    id=new_time_ordered_id("asrj_"),
                    core_task_id=core_task_id,
                    source_index=source_index,
                    source_asset_id=source_asset_id,
                    provider="volcengine",
                    callback_key=secrets.token_urlsafe(32),
                    status="preparing",
                )
                session.add(row)
                session.commit()
                session.refresh(row)
            return self._snapshot(row)

    def set_prepared_audio(
        self,
        job_id: str,
        *,
        artifact: dict[str, object],
        attempt_no: int,
    ) -> AsrJobSnapshot:
        with self.session_factory() as session:
            row = session.get(AsrProviderJob, job_id, with_for_update=True)
            if row is None:
                raise RuntimeError("ASR_PROVIDER_JOB_NOT_FOUND")
            if not row.prepared_audio_url:
                row.prepared_audio_url = str(artifact["url"])
                session.add(
                    CoreArtifact(
                        id=str(artifact["artifact_id"]),
                        core_task_id=row.core_task_id,
                        attempt_no=attempt_no,
                        kind=str(artifact["kind"]),
                        bucket=str(artifact["bucket"]),
                        object_key=str(artifact["object_key"]),
                        url=str(artifact["url"]),
                        content_type=str(artifact["content_type"]),
                        size=int(artifact["size"]),
                        checksum=str(artifact["checksum"])
                        if artifact.get("checksum")
                        else None,
                    )
                )
                session.commit()
                session.refresh(row)
            return self._snapshot(row)

    def mark_submitted(self, job_id: str, provider_task_id: str) -> AsrJobSnapshot:
        with self.session_factory() as session:
            row = session.get(AsrProviderJob, job_id, with_for_update=True)
            if row is None:
                raise RuntimeError("ASR_PROVIDER_JOB_NOT_FOUND")
            if row.provider_task_id and row.provider_task_id != provider_task_id:
                raise RuntimeError("ASR_PROVIDER_TASK_ID_CONFLICT")
            row.provider_task_id = provider_task_id
            if row.status == "preparing":
                row.status = "submitted"
            session.commit()
            session.refresh(row)
            return self._snapshot(row)

    def get(self, job_id: str) -> AsrJobSnapshot:
        with self.session_factory() as session:
            row = session.get(AsrProviderJob, job_id)
            if row is None:
                raise RuntimeError("ASR_PROVIDER_JOB_NOT_FOUND")
            return self._snapshot(row)

    def record_provider_response(
        self,
        job_id: str,
        *,
        payload: dict[str, object],
        status: str,
        error: dict[str, object] | None = None,
    ) -> AsrJobSnapshot:
        with self.session_factory() as session:
            row = session.get(AsrProviderJob, job_id, with_for_update=True)
            if row is None:
                raise RuntimeError("ASR_PROVIDER_JOB_NOT_FOUND")
            # 成功是单调终态；迟到的 pending/failed 不允许覆盖成功回调。
            if row.status != "succeeded":
                row.status = status
                row.response_payload = payload
                row.error = error
                session.commit()
                session.refresh(row)
            return self._snapshot(row)

    def record_callback(
        self, callback_key: str, *, payload: dict[str, object], provider_task_id: str
    ) -> AsrJobSnapshot | None:
        with self.session_factory() as session:
            row = session.scalar(
                select(AsrProviderJob)
                .where(AsrProviderJob.callback_key == callback_key)
                .with_for_update()
            )
            if row is None or row.provider_task_id != provider_task_id:
                return None
            response = payload.get("resp")
            raw_code = response.get("code") if isinstance(response, dict) else None
            try:
                code = int(raw_code)
            except (TypeError, ValueError):
                code = None
            if code == 1000:
                row.status, row.error = "succeeded", None
            elif code in {2000, 2001}:
                row.status = "submitted"
            else:
                row.status = "failed"
                row.error = {
                    "code": "ASR_PROVIDER_CALLBACK_FAILED",
                    "provider_code": code,
                }
            row.response_payload = payload
            session.commit()
            session.refresh(row)
            return self._snapshot(row)
