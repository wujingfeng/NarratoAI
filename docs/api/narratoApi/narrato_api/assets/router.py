from __future__ import annotations

from typing import Annotated, Literal, cast

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import sessionmaker

from narrato_api.api.dependencies import get_request_id, get_settings
from narrato_api.api.responses import ApiResponse
from narrato_api.assets.schemas import (
    AssetData,
    AssetOrderData,
    AssetOrderRequest,
    AssetRemovalData,
    UploadCompleteRequest,
    UploadPolicyData,
    UploadPolicyRequest,
)
from narrato_api.assets.service import UploadService
from narrato_api.auth.router import bearer_token, get_auth_service
from narrato_api.auth.service import AuthService
from narrato_api.config import Settings
from narrato_api.integrations.core_client import HttpCoreClient
from narrato_api.integrations.oss_client import HttpOssClient, OssPostPolicyService
from narrato_api.assets.constraints import AssetDeclarationError
from narrato_api.api.errors import ApiError

router = APIRouter()


def get_oss_client(
    request: Request, settings: Annotated[Settings, Depends(get_settings)]
) -> HttpOssClient:
    """创建供当前请求校验、URL 构造和鉴权删除使用的 OSS 客户端。"""

    return HttpOssClient(
        endpoint=settings.oss_endpoint,
        access_key_id=settings.oss_access_key_id,
        access_key_secret=settings.oss_access_key_secret,
    )


def get_core_client(
    settings: Annotated[Settings, Depends(get_settings)],
) -> HttpCoreClient:
    """创建只暴露媒体探测的 Core 调用客户端。"""

    return HttpCoreClient(
        base_url=str(settings.core_base_url), request_token=settings.core_request_token
    )


def get_upload_service(
    request: Request,
    oss_client: Annotated[object, Depends(get_oss_client)],
    core_client: Annotated[object, Depends(get_core_client)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> UploadService:
    """将应用数据库与外部上传依赖组合为请求服务。"""

    return UploadService(
        session_factory=sessionmaker(
            bind=request.app.state.database_engine, expire_on_commit=False
        ),
        oss_client=oss_client,
        core_client=core_client,
        oss_bucket=settings.oss_bucket,
    )


@router.post(
    "/projects/{project_id}/uploads/policy",
    response_model=ApiResponse[UploadPolicyData],
)
def create_upload_policy(
    project_id: str,
    body: UploadPolicyRequest,
    token: Annotated[str, Depends(bearer_token)],
    auth: Annotated[AuthService, Depends(get_auth_service)],
    service: Annotated[UploadService, Depends(get_upload_service)],
    settings: Annotated[Settings, Depends(get_settings)],
    request_id: Annotated[str, Depends(get_request_id)],
) -> ApiResponse[UploadPolicyData]:
    """仅向已登录项目所有者签发受限 OSS 直传表单。"""

    user = auth.resolve_user(token)
    policy_service = OssPostPolicyService(
        upload_url=settings.oss_url,
        bucket=settings.oss_bucket,
        access_key_id=settings.oss_access_key_id,
        access_key_secret=settings.oss_access_key_secret,
    )
    try:
        policy = policy_service.create_policy(
            asset_type=body.asset_type,
            filename=body.filename,
            size_bytes=body.size_bytes,
            content_type=body.content_type,
            existing_video_count=0,
        )
    except AssetDeclarationError as error:
        raise ApiError(
            "UPLOAD_DECLARATION_REJECTED", "Upload declaration is invalid", 422
        ) from error
    service.reserve(
        user_id=user.id,
        project_id=project_id,
        asset_type=body.asset_type,
        filename=body.filename,
        size_bytes=body.size_bytes,
        object_key=policy.key,
        cdn_url=f"{settings.cdn_public_base_url}/{policy.key}",
    )
    return ApiResponse(
        code="UPLOAD_POLICY_CREATED",
        message="Upload policy created",
        request_id=request_id,
        data=UploadPolicyData(
            url=policy.url,
            key=policy.key,
            fields=policy.fields,
            max_size_bytes=policy.max_size_bytes,
        ),
    )


@router.post(
    "/projects/{project_id}/uploads/complete",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=ApiResponse[AssetData],
)
def complete_upload(
    project_id: str,
    body: UploadCompleteRequest,
    token: Annotated[str, Depends(bearer_token)],
    auth: Annotated[AuthService, Depends(get_auth_service)],
    service: Annotated[UploadService, Depends(get_upload_service)],
    request_id: Annotated[str, Depends(get_request_id)],
) -> ApiResponse[AssetData]:
    """复核已上传对象并启动媒体探测。"""

    user = auth.resolve_user(token)
    asset = service.complete(
        user_id=user.id,
        project_id=project_id,
        asset_type=body.asset_type,
        filename=body.filename,
        size_bytes=body.size_bytes,
        content_type=body.content_type,
        object_key=body.object_key,
    )
    return ApiResponse(
        code="UPLOAD_VALIDATION_STARTED",
        message="Upload validation started",
        request_id=request_id,
        data=AssetData(
            id=asset.id,
            status=cast(Literal["validating", "ready", "invalid"], asset.status),
            cdn_url=asset.cdn_url,
        ),
    )


@router.get("/assets/{asset_id}", response_model=ApiResponse[AssetData])
def get_asset(
    asset_id: str,
    token: Annotated[str, Depends(bearer_token)],
    auth: Annotated[AuthService, Depends(get_auth_service)],
    service: Annotated[UploadService, Depends(get_upload_service)],
    request_id: Annotated[str, Depends(get_request_id)],
) -> ApiResponse[AssetData]:
    """认证读取单个资产，并按需轮询 Core 以收敛其异步探测状态。"""

    user = auth.resolve_user(token)
    asset = service.get_owned_asset(user_id=user.id, asset_id=asset_id)
    return ApiResponse(
        code="ASSET_RETRIEVED",
        message="Asset retrieved",
        request_id=request_id,
        data=AssetData(
            id=asset.id,
            status=cast(Literal["validating", "ready", "invalid"], asset.status),
            cdn_url=asset.cdn_url,
        ),
    )


@router.post(
    "/projects/{project_id}/assets/{asset_id}/remove",
    response_model=ApiResponse[AssetRemovalData],
)
def remove_asset(
    project_id: str,
    asset_id: str,
    token: Annotated[str, Depends(bearer_token)],
    auth: Annotated[AuthService, Depends(get_auth_service)],
    service: Annotated[UploadService, Depends(get_upload_service)],
    request_id: Annotated[str, Depends(get_request_id)],
) -> ApiResponse[AssetRemovalData]:
    """删除当前用户尚未开始项目的单个上传素材。"""

    user = auth.resolve_user(token)
    service.remove_owned_asset(
        user_id=user.id, project_id=project_id, asset_id=asset_id
    )
    return ApiResponse(
        code="ASSET_REMOVED",
        message="Asset removed",
        request_id=request_id,
        data=AssetRemovalData(removed=True),
    )


@router.post(
    "/projects/{project_id}/assets/order",
    response_model=ApiResponse[AssetOrderData],
)
def reorder_video_assets(
    project_id: str,
    body: AssetOrderRequest,
    token: Annotated[str, Depends(bearer_token)],
    auth: Annotated[AuthService, Depends(get_auth_service)],
    service: Annotated[UploadService, Depends(get_upload_service)],
    request_id: Annotated[str, Depends(get_request_id)],
) -> ApiResponse[AssetOrderData]:
    """保存当前项目完整的视频源顺序，供分析、编辑和渲染统一消费。"""

    user = auth.resolve_user(token)
    asset_ids = service.reorder_owned_video_assets(
        user_id=user.id,
        project_id=project_id,
        asset_ids=body.asset_ids,
    )
    return ApiResponse(
        code="PROJECT_ASSET_ORDER_UPDATED",
        message="Project video asset order updated",
        request_id=request_id,
        data=AssetOrderData(asset_ids=asset_ids),
    )
