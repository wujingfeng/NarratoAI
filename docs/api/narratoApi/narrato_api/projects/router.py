from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session

from narrato_api.api.dependencies import get_request_id, get_settings
from narrato_api.api.errors import ApiError
from narrato_api.api.responses import ApiResponse, StrictModel
from narrato_api.auth.router import bearer_token, get_auth_service
from narrato_api.auth.service import AuthService
from narrato_api.config import Settings
from narrato_api.exports.service import (
    JianyingManifestSnapshotNotFoundError,
    build_owned_completed_project_jianying_manifest,
)
from narrato_api.integrations.core_client import CoreClientError, HttpCoreClient
from narrato_api.projects.service import (
    ProjectNotFoundError,
    ProjectLifecycleConflict,
    ProjectResultLookupError,
    create_project,
    estimate_project_cost,
    lookup_completed_project_result,
    request_project_deletion,
    start_project,
    ProjectStateConflict,
)

router = APIRouter()


def get_jianying_core_client(
    settings: Annotated[Settings, Depends(get_settings)],
) -> HttpCoreClient:
    """创建仅用于剪映 Manifest 的 Core 客户端。"""

    return HttpCoreClient(
        base_url=str(settings.core_base_url), request_token=settings.core_request_token
    )


class ProjectResultArtifactData(StrictModel):
    """项目结果中可公开的已登记产物。"""

    id: str
    kind: str
    cdn_url: str


class ProjectCreateRequest(StrictModel):
    product: str


class ProjectData(StrictModel):
    id: str
    status: str


class ProjectCostData(StrictModel):
    credits: int
    total_seconds: int
    credits_per_minute: int


class ProjectStartData(StrictModel):
    workflow_id: str


def _lifecycle_error(error: Exception) -> ApiError:
    if isinstance(error, ProjectNotFoundError):
        return ApiError("PROJECT_NOT_FOUND", "Project not found", 404)
    if isinstance(error, ProjectLifecycleConflict):
        return ApiError(error.code, str(error), 409)
    raise error


@router.post("/projects", status_code=status.HTTP_201_CREATED, response_model=ApiResponse[ProjectData])
def create_owned_project(body: ProjectCreateRequest, request: Request, token: Annotated[str, Depends(bearer_token)], auth: Annotated[AuthService, Depends(get_auth_service)], request_id: Annotated[str, Depends(get_request_id)]) -> ApiResponse[ProjectData]:
    user = auth.resolve_user(token)
    with Session(request.app.state.database_engine) as session:
        with session.begin():
            try:
                project = create_project(session, user_id=user.id, product=body.product)
                data = ProjectData(id=project.id, status=project.status)
            except ProjectLifecycleConflict as error:
                raise _lifecycle_error(error) from error
    return ApiResponse(code="PROJECT_CREATED", message="Project created", data=data, request_id=request_id)


@router.post("/projects/{project_id}/cost-estimate", response_model=ApiResponse[ProjectCostData])
def estimate_owned_project(project_id: str, request: Request, token: Annotated[str, Depends(bearer_token)], auth: Annotated[AuthService, Depends(get_auth_service)], request_id: Annotated[str, Depends(get_request_id)]) -> ApiResponse[ProjectCostData]:
    user = auth.resolve_user(token)
    with Session(request.app.state.database_engine) as session:
        try:
            credits, total_seconds, credits_per_minute = estimate_project_cost(session, user_id=user.id, project_id=project_id)
        except (ProjectNotFoundError, ProjectLifecycleConflict) as error:
            raise _lifecycle_error(error) from error
    return ApiResponse(code="PROJECT_COST_ESTIMATED", message="Project cost estimated", data=ProjectCostData(credits=credits, total_seconds=total_seconds, credits_per_minute=credits_per_minute), request_id=request_id)


@router.post("/projects/{project_id}/start", status_code=status.HTTP_202_ACCEPTED, response_model=ApiResponse[ProjectStartData])
def start_owned_project(project_id: str, request: Request, token: Annotated[str, Depends(bearer_token)], auth: Annotated[AuthService, Depends(get_auth_service)], request_id: Annotated[str, Depends(get_request_id)]) -> ApiResponse[ProjectStartData]:
    user = auth.resolve_user(token)
    with Session(request.app.state.database_engine) as session:
        try:
            with session.begin():
                workflow_id = start_project(session, user_id=user.id, project_id=project_id)
        except (ProjectNotFoundError, ProjectLifecycleConflict) as error:
            raise _lifecycle_error(error) from error
    return ApiResponse(code="PROJECT_STARTED", message="Project started", data=ProjectStartData(workflow_id=workflow_id), request_id=request_id)


class ProjectResultData(StrictModel):
    """已完成项目的最小可读结果。"""

    project_id: str
    artifacts: list[ProjectResultArtifactData]


class JianyingManifestFileData(StrictModel):
    """Core 已生成的一项内联或 CDN 剪映文件。"""

    zip_path: str
    content: str | None = None
    content_base64: str | None = None
    url: str | None = None
    size: int | None = None
    checksum: str | None = None
    content_type: str | None = None


class JianyingManifestData(StrictModel):
    """Core 生成的无 ZIP 剪映基础文件和资源映射。"""

    template_version: str
    package_name: str
    files: list[JianyingManifestFileData]


class ProjectDeletionRequestData(StrictModel):
    """已登记、尚未执行实际删除的项目删除请求。"""

    job_id: str
    project_id: str
    status: str


@router.post(
    "/projects/{project_id}/deletion-requests",
    status_code=202,
    response_model=ApiResponse[ProjectDeletionRequestData],
)
def request_deletion(
    project_id: str,
    request: Request,
    token: Annotated[str, Depends(bearer_token)],
    auth: Annotated[AuthService, Depends(get_auth_service)],
    request_id: Annotated[str, Depends(get_request_id)],
) -> ApiResponse[ProjectDeletionRequestData]:
    """为当前用户的终态项目登记幂等删除审计请求。"""

    user = auth.resolve_user(token)
    with Session(request.app.state.database_engine) as session:
        try:
            with session.begin():
                deletion = request_project_deletion(
                    session, user_id=user.id, project_id=project_id
                )
        except ProjectNotFoundError as error:
            raise ApiError("PROJECT_NOT_FOUND", "Project not found", 404) from error
        except ProjectStateConflict as error:
            raise ApiError(
                "PROJECT_NOT_TERMINAL", "Project is not terminal", 409
            ) from error

    return ApiResponse(
        code="PROJECT_DELETION_REQUESTED",
        message="Project deletion requested",
        data=ProjectDeletionRequestData(
            job_id=deletion.job_id,
            project_id=deletion.project_id,
            status=deletion.status,
        ),
        request_id=request_id,
    )


@router.get(
    "/projects/{project_id}/result", response_model=ApiResponse[ProjectResultData]
)
def get_project_result(
    project_id: str,
    request: Request,
    token: Annotated[str, Depends(bearer_token)],
    auth: Annotated[AuthService, Depends(get_auth_service)],
    request_id: Annotated[str, Depends(get_request_id)],
) -> ApiResponse[ProjectResultData]:
    """只返回当前用户已完成项目的已登记产物。"""

    user = auth.resolve_user(token)
    with Session(request.app.state.database_engine) as session:
        try:
            result = lookup_completed_project_result(
                session, user_id=user.id, project_id=project_id
            )
        except ProjectResultLookupError as error:
            raise ApiError(
                "PROJECT_RESULT_NOT_FOUND", "Project result not found", 404
            ) from error

    return ApiResponse(
        code="PROJECT_RESULT",
        message="Project result",
        data=ProjectResultData(
            project_id=result.project_id,
            artifacts=[
                ProjectResultArtifactData(
                    id=artifact.id,
                    kind=artifact.kind,
                    cdn_url=artifact.cdn_url,
                )
                for artifact in result.artifacts
            ],
        ),
        request_id=request_id,
    )


@router.post(
    "/projects/{project_id}/exports/jianying-manifest",
    response_model=ApiResponse[JianyingManifestData],
)
def build_project_jianying_manifest(
    project_id: str,
    request: Request,
    token: Annotated[str, Depends(bearer_token)],
    auth: Annotated[AuthService, Depends(get_auth_service)],
    core_client: Annotated[HttpCoreClient, Depends(get_jianying_core_client)],
    request_id: Annotated[str, Depends(get_request_id)],
) -> ApiResponse[JianyingManifestData]:
    """只为当前用户已完成项目返回 Core 生成的剪映 Manifest。"""

    user = auth.resolve_user(token)
    with Session(request.app.state.database_engine) as session:
        try:
            manifest = build_owned_completed_project_jianying_manifest(
                session,
                user_id=user.id,
                project_id=project_id,
                core_client=core_client,
            )
        except ProjectResultLookupError as error:
            raise ApiError(
                "PROJECT_RESULT_NOT_FOUND", "Project result not found", 404
            ) from error
        except JianyingManifestSnapshotNotFoundError as error:
            raise ApiError(
                error.code, "Project editor snapshot not found", 409
            ) from error
        except CoreClientError as error:
            raise ApiError(
                "CORE_UNAVAILABLE", "Core manifest service is unavailable", 503
            ) from error

    return ApiResponse(
        code="JIANYING_MANIFEST",
        message="Jianying manifest",
        data=JianyingManifestData(
            template_version=manifest.template_version,
            package_name=manifest.package_name,
            files=[
                JianyingManifestFileData(**file) for file in manifest.to_dict()["files"]
            ],
        ),
        request_id=request_id,
    )
