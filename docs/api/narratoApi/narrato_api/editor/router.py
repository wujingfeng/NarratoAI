from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request, status
from sqlalchemy.orm import sessionmaker

from narrato_api.api.dependencies import get_request_id
from narrato_api.api.errors import ApiError
from narrato_api.api.responses import ApiResponse
from narrato_api.auth.router import bearer_token, get_auth_service
from narrato_api.auth.service import AuthService
from narrato_api.editor.schemas import (
    EditorDraftData,
    EditorSaveData,
    EditorSaveRequest,
    RenderSubmitData,
)
from narrato_api.editor.service import (
    EditorDraftNotFoundError,
    EditorLockedError,
    EditorProjectNotFoundError,
    EditorRenderSnapshotError,
    EditorService,
    EditorWorkflowNotFoundError,
)

router = APIRouter()


def get_editor_service(request: Request) -> EditorService:
    """使用当前应用业务库创建编辑器事务服务。"""

    return EditorService(
        sessionmaker(bind=request.app.state.database_engine, expire_on_commit=False)
    )


def _editor_error(error: Exception) -> ApiError:
    if isinstance(error, (EditorProjectNotFoundError, EditorDraftNotFoundError)):
        return ApiError("EDITOR_NOT_FOUND", "Editor draft not found", 404)
    if isinstance(error, (EditorLockedError, EditorWorkflowNotFoundError)):
        return ApiError("EDITOR_LOCKED", "Editor is locked", 409)
    if isinstance(error, EditorRenderSnapshotError):
        return ApiError("EDITOR_RENDER_INVALID", str(error), 422)
    raise error


@router.get(
    "/projects/{project_id}/editor", response_model=ApiResponse[EditorDraftData]
)
def get_editor(
    project_id: str,
    token: Annotated[str, Depends(bearer_token)],
    auth: Annotated[AuthService, Depends(get_auth_service)],
    service: Annotated[EditorService, Depends(get_editor_service)],
    request_id: Annotated[str, Depends(get_request_id)],
) -> ApiResponse[EditorDraftData]:
    """读取当前用户项目草稿；锁定后仅提供只读内容。"""

    user = auth.resolve_user(token)
    try:
        draft, locked = service.get_draft(user_id=user.id, project_id=project_id)
    except (EditorProjectNotFoundError, EditorDraftNotFoundError) as error:
        raise _editor_error(error) from error
    return ApiResponse(
        code="EDITOR_DRAFT",
        message="Editor draft",
        data=EditorDraftData(draft_id=draft.id, content=draft.content, locked=locked),
        request_id=request_id,
    )


@router.post(
    "/projects/{project_id}/editor/save", response_model=ApiResponse[EditorSaveData]
)
def save_editor(
    project_id: str,
    body: EditorSaveRequest,
    token: Annotated[str, Depends(bearer_token)],
    auth: Annotated[AuthService, Depends(get_auth_service)],
    service: Annotated[EditorService, Depends(get_editor_service)],
    request_id: Annotated[str, Depends(get_request_id)],
) -> ApiResponse[EditorSaveData]:
    """保存 waiting_for_edit 项目草稿，采用 Last Write Wins。"""

    user = auth.resolve_user(token)
    try:
        draft_id = service.save_draft(
            user_id=user.id, project_id=project_id, content=body.content
        )
    except (EditorLockedError, EditorProjectNotFoundError) as error:
        raise _editor_error(error) from error
    return ApiResponse(
        code="EDITOR_SAVED",
        message="Editor draft saved",
        data=EditorSaveData(draft_id=draft_id),
        request_id=request_id,
    )


@router.post(
    "/projects/{project_id}/render/submit",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=ApiResponse[RenderSubmitData],
)
def submit_render(
    project_id: str,
    token: Annotated[str, Depends(bearer_token)],
    auth: Annotated[AuthService, Depends(get_auth_service)],
    service: Annotated[EditorService, Depends(get_editor_service)],
    request_id: Annotated[str, Depends(get_request_id)],
    idempotency_key: Annotated[str, Header(alias="X-Idempotency-Key")],
) -> ApiResponse[RenderSubmitData]:
    """创建不可变 revision、锁定编辑器并写入最终渲染 Outbox。"""

    user = auth.resolve_user(token)
    try:
        service.submit_render(
            user_id=user.id, project_id=project_id, idempotency_key=idempotency_key
        )
    except (
        EditorLockedError,
        EditorProjectNotFoundError,
        EditorWorkflowNotFoundError,
        EditorDraftNotFoundError,
        EditorRenderSnapshotError,
    ) as error:
        raise _editor_error(error) from error
    return ApiResponse(
        code="RENDER_SUBMITTED",
        message="Render submitted",
        data=RenderSubmitData(accepted=True),
        request_id=request_id,
    )
