from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from core_api.api.dependencies import (
    get_database_session,
    get_request_id,
    get_settings,
    require_service_token,
)
from core_api.api.responses import ApiResponse
from core_api.capabilities.schemas import CapabilityCatalogDTO
from core_api.capabilities.service import CapabilityService
from core_api.config import Settings

router = APIRouter()


@router.get("", response_model=ApiResponse[CapabilityCatalogDTO])
def get_capabilities(
    request_id: Annotated[str, Depends(get_request_id)],
    settings: Annotated[Settings, Depends(get_settings)],
    session: Annotated[Session, Depends(get_database_session)],
    _authorized: Annotated[None, Depends(require_service_token)],
) -> ApiResponse[CapabilityCatalogDTO]:
    """返回当前已启用且密钥可解析的统一能力目录。"""

    catalog = CapabilityService(session, settings.provider_secrets).catalog()
    return ApiResponse(
        code="OK",
        message="能力目录读取成功",
        data=catalog,
        request_id=request_id,
    )
