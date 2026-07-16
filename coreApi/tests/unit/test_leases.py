from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from core_api.tasks.models import CoreTaskStatus, utc_now
from core_api.tasks.service import LeaseStillActiveError, StaleLeaseError


def test_heartbeat_requires_current_token_and_version(task_service, task):
    """心跳同时校验 current attempt、token 和租约版本。"""

    attempt = task_service.acquire_lease(task.id, lease_seconds=30)
    before = attempt.lease_expires_at

    with pytest.raises(StaleLeaseError):
        task_service.heartbeat(
            attempt.id,
            "wrong-token",
            attempt.lease_version,
            lease_seconds=60,
        )
    with pytest.raises(StaleLeaseError):
        task_service.heartbeat(
            attempt.id,
            attempt.lease_token,
            attempt.lease_version + 1,
            lease_seconds=60,
        )

    renewed = task_service.heartbeat(
        attempt.id,
        attempt.lease_token,
        attempt.lease_version,
        lease_seconds=60,
    )
    assert renewed.heartbeat_at is not None
    assert renewed.lease_expires_at > before


def test_replaced_attempt_cannot_heartbeat(task_service, task):
    """已被新 attempt 替代的租约不能续期。"""

    first = task_service.start_attempt(task.id)
    first.lease_expires_at = utc_now() - timedelta(seconds=1)
    task_service.session.commit()
    task_service.expire_and_restart(first.id)
    with pytest.raises(StaleLeaseError):
        task_service.heartbeat(
            first.id,
            first.lease_token,
            first.lease_version,
        )


def test_heartbeat_rejects_expired_lease(task_service, task, session):
    """已过期租约即使 token 正确也不能复活。"""

    attempt = task_service.start_attempt(task.id)
    attempt.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    session.commit()
    with pytest.raises(StaleLeaseError):
        task_service.heartbeat(
            attempt.id,
            attempt.lease_token,
            attempt.lease_version,
        )


def test_restart_rejects_non_positive_lease_duration(task_service, task):
    """重启 attempt 不接受已失效的新租约时长。"""

    attempt = task_service.start_attempt(task.id)
    with pytest.raises(ValueError, match="lease_seconds"):
        task_service.expire_and_restart(attempt.id, lease_seconds=0)


def test_active_lease_cannot_be_restarted(task_service, task, session):
    """一小时有效租约不能被扫描器提前替换。"""

    attempt = task_service.start_attempt(task.id, lease_seconds=3600)
    before_version = task.state_version
    with pytest.raises(LeaseStillActiveError, match="LEASE_STILL_ACTIVE"):
        task_service.expire_and_restart(attempt.id)
    session.refresh(task)
    session.refresh(attempt)
    assert task.status == CoreTaskStatus.RUNNING
    assert task.state_version == before_version
    assert task.current_attempt_no == 1
    assert attempt.status.value == "running"


def test_stale_heartbeat_at_threshold_allows_restart(task_service, task, session):
    """心跳到达超时阈值时，即使租约较长也允许恢复。"""

    observed_at = utc_now()
    attempt = task_service.start_attempt(task.id, lease_seconds=3600)
    attempt.heartbeat_at = observed_at - timedelta(seconds=60)
    session.commit()
    replacement = task_service.expire_and_restart(
        attempt.id,
        heartbeat_timeout_seconds=60,
        now=observed_at,
    )
    assert replacement is not None
    assert replacement.attempt_no == 2
