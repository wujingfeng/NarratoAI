from __future__ import annotations

import pytest
from pydantic import ValidationError

from narrato_api.api.errors import ServiceUnavailableError
from narrato_api.api.responses import ApiResponse, envelope


def test_shared_response_envelope_has_only_protocol_fields() -> None:
    payload = {"project_id": "prj_contract_business"}

    actual = envelope(
        request_id="req_contract_business",
        code="PROJECT_CREATED",
        message="Project created",
        data=payload,
    )

    assert actual == {
        "code": "PROJECT_CREATED",
        "message": "Project created",
        "data": payload,
        "request_id": "req_contract_business",
    }
    with pytest.raises(ValidationError):
        ApiResponse(**actual, unexpected="not part of the public protocol")


def test_stable_service_unavailable_error_code() -> None:
    error = ServiceUnavailableError()

    assert error.code == "SERVICE_UNAVAILABLE"
    assert error.status_code == 503
