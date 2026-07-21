from __future__ import annotations

import pytest
from pydantic import ValidationError

from core_api.api.errors import (
    CapabilityUnavailableError,
    ServiceUnavailableError,
    UnauthorizedError,
)
from core_api.api.responses import ApiResponse, envelope


def test_shared_response_envelope_has_only_protocol_fields() -> None:
    payload = {"capability_id": "short-drama.analysis"}

    actual = envelope(
        request_id="req_contract_core",
        code="CAPABILITY_AVAILABLE",
        message="Capability is available",
        data=payload,
    )

    assert actual == {
        "code": "CAPABILITY_AVAILABLE",
        "message": "Capability is available",
        "data": payload,
        "request_id": "req_contract_core",
    }
    with pytest.raises(ValidationError):
        ApiResponse(**actual, unexpected="not part of the public protocol")


@pytest.mark.parametrize(
    ("error", "code", "status_code"),
    [
        (ServiceUnavailableError(), "SERVICE_UNAVAILABLE", 503),
        (UnauthorizedError(), "UNAUTHORIZED", 401),
        (CapabilityUnavailableError(), "CAPABILITY_UNAVAILABLE", 409),
    ],
)
def test_stable_public_error_codes(
    error: Exception, code: str, status_code: int
) -> None:
    assert getattr(error, "code") == code
    assert getattr(error, "status_code") == status_code
