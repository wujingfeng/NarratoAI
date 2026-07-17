from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from narrato_api.api.dependencies import get_request_id
from narrato_api.api.errors import ApiError
from narrato_api.api.responses import ApiResponse, StrictModel
from narrato_api.auth.router import bearer_token, get_auth_service
from narrato_api.auth.service import AuthService
from narrato_api.projects.service import (
    ProjectResultLookupError,
    lookup_completed_project_result,
)

router = APIRouter()


class ProjectResultArtifactData(StrictModel):
    """项目结果中可公开的已登记产物。"""

    id: str
    kind: str
    cdn_url: str


class ProjectResultData(StrictModel):
    """已完成项目的最小可读结果。"""

    project_id: str
    artifacts: list[ProjectResultArtifactData]


@router.get("/projects/{project_id}/result", response_model=ApiResponse[ProjectResultData])
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
