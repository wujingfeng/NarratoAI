from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Query, Request, status
from pydantic import Field
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from narrato_api.admin.models import (
    AdminMenu,
    AdminOperationLog,
    AdminPermission,
    AdminRole,
    AdminRolePermission,
    AdminUser,
    AdminUserRole,
    SystemConfig,
)
from narrato_api.admin.service import (
    AdminTokenService,
    new_id,
    normalize_username,
    password_hasher,
    permissions_for,
    require_permission,
    roles_for,
)
from narrato_api.api.dependencies import get_request_id, get_settings
from narrato_api.api.errors import ApiError
from narrato_api.api.responses import ApiResponse, StrictModel
from narrato_api.artifacts.models import RegisteredArtifact
from narrato_api.assets.models import Asset
from narrato_api.auth.models import User
from narrato_api.auth.service import validate_password
from narrato_api.billing.models import CreditAccount, CreditLedger
from narrato_api.config import Settings
from narrato_api.projects.models import Project, ProjectNarrationSettings, ProjectStageHistory
from narrato_api.products.model_generation import (
    Model,
    ModelPlayMode,
    ModelPlayModeProvider,
    ModelTask,
    ModelTaskAsset,
    ModelTaskOutput,
)
from narrato_api.products.video_translation import VideoTranslationSettings
from narrato_api.workflows.models import Workflow, WorkflowNode, WorkflowNodeAttempt

router = APIRouter(prefix="/admin")


class LoginRequest(StrictModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class AdminCreateRequest(StrictModel):
    username: str = Field(min_length=1, max_length=64)
    display_name: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=8, max_length=128)
    role_ids: list[str] = Field(default_factory=list, max_length=50)
    is_superuser: bool = False


class AdminUpdateRequest(StrictModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=128)
    status: str | None = None
    role_ids: list[str] | None = Field(default=None, max_length=50)
    password: str | None = Field(default=None, min_length=8, max_length=128)


class RoleRequest(StrictModel):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=512)
    permission_ids: list[str] = Field(default_factory=list, max_length=200)


class PermissionRequest(StrictModel):
    code: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=512)


class MenuRequest(StrictModel):
    parent_id: str | None = Field(default=None, max_length=64)
    name: str = Field(min_length=1, max_length=128)
    code: str = Field(min_length=1, max_length=128)
    path: str | None = Field(default=None, max_length=256)
    icon: str | None = Field(default=None, max_length=64)
    menu_type: str = "menu"
    permission_code: str | None = Field(default=None, max_length=128)
    is_visible: bool = True
    sort_order: int = Field(default=0, ge=0, le=100_000)


class StatusRequest(StrictModel):
    status: str


class BatchStatusRequest(StatusRequest):
    user_ids: list[str] = Field(min_length=1, max_length=1000)


class ConfigRequest(StrictModel):
    value: str | None = Field(default=None, max_length=100_000)
    description: str | None = Field(default=None, max_length=512)
    is_secret: bool = False


class ModelUpdateRequest(StrictModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=512)
    category: str | None = Field(default=None, min_length=1, max_length=64)
    sort_order: int | None = Field(default=None, ge=0, le=100_000)
    is_enabled: bool | None = None
    is_default: bool | None = None


class PlayModeUpdateRequest(StrictModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=512)
    default_credits: int | None = Field(default=None, ge=0)
    is_enabled: bool | None = None
    is_default: bool | None = None
    sort_order: int | None = Field(default=None, ge=0, le=100_000)


class ProviderUpdateRequest(StrictModel):
    provider_model_id: str | None = Field(default=None, min_length=1, max_length=128)
    submit_url: str | None = Field(default=None, min_length=1, max_length=2048)
    status_query_url: str | None = Field(default=None, max_length=2048)
    status_query_method: str | None = None
    api_key: str | None = Field(default=None, min_length=1, max_length=8192)
    is_enabled: bool | None = None


class Context:
    def __init__(
        self,
        request: Request,
        session: Session,
        admin: AdminUser,
        permissions: set[str],
    ) -> None:
        self.request, self.session, self.admin, self.permissions = (
            request,
            session,
            admin,
            permissions,
        )


def _db(request: Request) -> Iterator[Session]:
    session = Session(request.app.state.database_engine, expire_on_commit=False)
    try:
        yield session
    finally:
        session.close()


def _token_service(settings: Settings) -> AdminTokenService:
    # 旧部署尚未配置独立密钥时允许复用认证 HMAC；令牌仍有独立前缀与 payload 类型。
    secret = (
        settings.admin_session_hmac_secret or settings.verification_code_hmac_secret
    )
    try:
        return AdminTokenService(
            secret=secret, ttl_seconds=settings.admin_session_ttl_seconds
        )
    except ValueError as error:
        raise ApiError(
            "ADMIN_AUTH_UNAVAILABLE", "Admin authentication unavailable", 503
        ) from error


def _bearer(authorization: Annotated[str | None, Header()] = None) -> str:
    if not authorization:
        raise ApiError("ADMIN_AUTH_REQUIRED", "Admin authentication required", 401)
    scheme, sep, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or sep != " " or not token or " " in token:
        raise ApiError("ADMIN_AUTH_REQUIRED", "Admin authentication required", 401)
    return token


def _context(
    request: Request,
    token: Annotated[str, Depends(_bearer)],
    settings: Annotated[Settings, Depends(get_settings)],
    session: Annotated[Session, Depends(_db)],
) -> Context:
    identity = _token_service(settings).resolve(token)
    if identity is None:
        raise ApiError("ADMIN_AUTH_REQUIRED", "Admin authentication required", 401)
    admin = session.get(AdminUser, identity.id)
    if (
        admin is None
        or admin.status != "active"
        or admin.password_version != identity.password_version
    ):
        raise ApiError("ADMIN_AUTH_REQUIRED", "Admin authentication required", 401)
    return Context(request, session, admin, permissions_for(session, admin))


def allowed(permission: str) -> Callable[[Context], Context]:
    def dependency(context: Annotated[Context, Depends(_context)]) -> Context:
        if not require_permission(context.permissions, permission):
            raise ApiError("ADMIN_PERMISSION_DENIED", "Admin permission denied", 403)
        return context

    return dependency


def _ok(
    request_id: str, code: str, data: dict[str, Any]
) -> ApiResponse[dict[str, Any]]:
    return ApiResponse(code=code, message="OK", data=data, request_id=request_id)


def _page(page: int, page_size: int) -> tuple[int, int]:
    return max(1, page), min(max(1, page_size), 1000)


def _data(
    model: object, fields: tuple[str, ...], *, secret_fields: set[str] | None = None
) -> dict[str, Any]:
    result = {field: getattr(model, field) for field in fields}
    for field in secret_fields or set():
        if field in result:
            result[field] = "********" if result[field] else None
    return result


_SECRET_FIELD_PARTS = ("api_key", "authorization", "password", "secret", "token")


def _redact(value: Any, *, key: str = "") -> Any:
    """保留用户可见任务配置，避免管理详情意外返回密钥。"""

    if any(part in key.lower() for part in _SECRET_FIELD_PARTS):
        return "********"
    if isinstance(value, dict):
        return {
            str(item_key): _redact(item_value, key=str(item_key))
            for item_key, item_value in value.items()
        }
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value


def _asset_media(asset: Asset) -> dict[str, Any]:
    return {
        "id": asset.id,
        "kind": asset.asset_type,
        "url": asset.cdn_url,
        "filename": asset.filename,
        "content_type": None,
        "size_bytes": asset.size_bytes,
        "duration_seconds": asset.duration_seconds,
        "status": asset.status,
    }


def _user_name(context: Context, user_id: str) -> str | None:
    user = context.session.get(User, user_id)
    return user.email if user is not None else None


def _artifact_media(artifact: RegisteredArtifact) -> dict[str, Any]:
    return {
        "id": artifact.id,
        "kind": artifact.kind,
        "url": artifact.cdn_url,
        "filename": None,
        "content_type": artifact.content_type,
        "size_bytes": artifact.size,
        "duration_seconds": artifact.duration,
        "width": artifact.width,
        "height": artifact.height,
    }


def _project_input(context: Context, project: Project | None) -> dict[str, Any]:
    if project is None:
        return {"project": None, "settings": {}, "source_assets": []}
    assets = list(
        context.session.scalars(
            select(Asset)
            .where(Asset.project_id == project.id)
            .order_by(Asset.sort_order, Asset.created_at, Asset.id)
        )
    )
    narration = context.session.get(ProjectNarrationSettings, project.id)
    translation = context.session.get(VideoTranslationSettings, project.id)
    latest_snapshot = context.session.scalar(
        select(ProjectStageHistory)
        .where(ProjectStageHistory.project_id == project.id)
        .where(ProjectStageHistory.settings_snapshot.is_not(None))
        .order_by(ProjectStageHistory.created_at.desc())
    )
    settings = (
        dict(translation.settings)
        if translation is not None
        else dict(narration.settings)
        if narration is not None
        else dict(latest_snapshot.settings_snapshot or {})
        if latest_snapshot is not None
        else {}
    )
    return {
        "project": _data(
            project,
            ("id", "product", "status", "current_stage", "created_at", "updated_at"),
        ),
        "settings": _redact(settings),
        "source_assets": [_asset_media(asset) for asset in assets],
    }


def _workflow_execution(context: Context, workflow_id: str) -> list[dict[str, Any]]:
    nodes = list(
        context.session.scalars(
            select(WorkflowNode)
            .where(WorkflowNode.workflow_id == workflow_id)
            .order_by(WorkflowNode.created_at, WorkflowNode.id)
        )
    )
    result: list[dict[str, Any]] = []
    for node in nodes:
        latest_attempt = context.session.scalar(
            select(WorkflowNodeAttempt)
            .where(WorkflowNodeAttempt.workflow_node_id == node.id)
            .order_by(
                WorkflowNodeAttempt.attempt_number.desc(),
                WorkflowNodeAttempt.created_at.desc(),
            )
        )
        result.append(
            _data(
                node,
                (
                    "id",
                    "name",
                    "state",
                    "retryable",
                    "manual_gate",
                    "created_at",
                    "updated_at",
                ),
            )
            | {
                "latest_attempt": _data(
                    latest_attempt,
                    (
                        "attempt_number",
                        "state",
                        "core_task_id",
                        "created_at",
                        "completed_at",
                    ),
                )
                if latest_attempt is not None
                else None
            }
        )
    return result


def _audit(
    context: Context,
    *,
    action: str,
    resource_type: str,
    resource_id: str | None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
) -> None:
    request = context.request
    forwarded = request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
    ip = forwarded or (request.client.host if request.client else None)
    context.session.add(
        AdminOperationLog(
            admin_id=context.admin.id,
            username=context.admin.username,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            request_id=getattr(request.state, "request_id", None),
            ip_address=ip,
            method=request.method,
            path=request.url.path,
            before_data=before,
            after_data=after,
        )
    )


def _menus(session: Session, permissions: set[str]) -> list[dict[str, Any]]:
    menus = list(
        session.scalars(
            select(AdminMenu)
            .where(AdminMenu.is_visible.is_(True))
            .order_by(AdminMenu.sort_order, AdminMenu.id)
        )
    )
    permitted = [
        menu
        for menu in menus
        if not menu.permission_code
        or require_permission(permissions, menu.permission_code)
    ]
    records = {
        menu.id: _data(
            menu,
            (
                "id",
                "parent_id",
                "name",
                "code",
                "path",
                "icon",
                "menu_type",
                "permission_code",
                "sort_order",
            ),
        )
        | {"children": []}
        for menu in permitted
    }
    roots: list[dict[str, Any]] = []
    for item in records.values():
        parent = records.get(item["parent_id"])
        if parent is not None:
            parent["children"].append(item)
        else:
            roots.append(item)
    return roots


def _admin_data(
    session: Session, admin: AdminUser, permissions: set[str] | None = None
) -> dict[str, Any]:
    available = (
        permissions if permissions is not None else permissions_for(session, admin)
    )
    return _data(
        admin,
        (
            "id",
            "username",
            "display_name",
            "status",
            "is_superuser",
            "created_at",
            "updated_at",
        ),
    ) | {
        "roles": roles_for(session, admin.id),
        "permissions": sorted(available),
        "menus": _menus(session, available),
    }


@router.post("/auth/login", response_model=ApiResponse[dict[str, Any]])
def login(
    body: LoginRequest,
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    session: Annotated[Session, Depends(_db)],
    request_id: Annotated[str, Depends(get_request_id)],
) -> ApiResponse[dict[str, Any]]:
    try:
        username = normalize_username(body.username)
    except ValueError:
        username = ""
    admin = (
        session.scalar(select(AdminUser).where(AdminUser.username == username))
        if username
        else None
    )
    matched = password_hasher(settings).verify(
        admin.password_hash if admin else None, body.password
    )
    if admin is None or admin.status != "active" or not matched:
        session.add(
            AdminOperationLog(
                username=username or None,
                action="admin.auth.login",
                resource_type="admin_auth",
                request_id=request_id,
                ip_address=(request.client.host if request.client else None),
                method="POST",
                path=request.url.path,
                result="failed",
            )
        )
        session.commit()
        raise ApiError("ADMIN_LOGIN_FAILED", "Invalid username or password", 401)
    permissions = permissions_for(session, admin)
    _audit(
        Context(request, session, admin, permissions),
        action="admin.auth.login",
        resource_type="admin_auth",
        resource_id=admin.id,
    )
    session.commit()
    return _ok(
        request_id,
        "ADMIN_LOGIN_SUCCEEDED",
        {
            "token": _token_service(settings).issue(admin),
            "token_type": "Bearer",
            "expires_in": settings.admin_session_ttl_seconds,
            "admin": _admin_data(session, admin, permissions),
        },
    )


@router.get("/auth/me", response_model=ApiResponse[dict[str, Any]])
def me(
    context: Annotated[Context, Depends(_context)],
    request_id: Annotated[str, Depends(get_request_id)],
) -> ApiResponse[dict[str, Any]]:
    return _ok(
        request_id,
        "ADMIN_CURRENT_USER",
        {"admin": _admin_data(context.session, context.admin, context.permissions)},
    )


@router.post("/auth/logout", response_model=ApiResponse[dict[str, Any]])
def logout(
    context: Annotated[Context, Depends(_context)],
    request_id: Annotated[str, Depends(get_request_id)],
) -> ApiResponse[dict[str, Any]]:
    _audit(
        context,
        action="admin.auth.logout",
        resource_type="admin_auth",
        resource_id=context.admin.id,
    )
    context.session.commit()
    return _ok(request_id, "ADMIN_LOGOUT_SUCCEEDED", {})


@router.get("/overview", response_model=ApiResponse[dict[str, Any]])
def overview(
    context: Annotated[Context, Depends(allowed("admin:overview:read"))],
    request_id: Annotated[str, Depends(get_request_id)],
) -> ApiResponse[dict[str, Any]]:
    session = context.session
    since = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    users_total = session.scalar(select(func.count()).select_from(User)) or 0
    users_active = (
        session.scalar(
            select(func.count()).select_from(User).where(User.status == "active")
        )
        or 0
    )
    model_total = session.scalar(select(func.count()).select_from(ModelTask)) or 0
    workflow_total = session.scalar(select(func.count()).select_from(Workflow)) or 0
    model_status = [
        {"type": row[0], "status": row[1], "count": row[2]}
        for row in session.execute(
            select(ModelTask.task_type, ModelTask.status, func.count()).group_by(
                ModelTask.task_type, ModelTask.status
            )
        )
    ]
    workflow_status = [
        {"type": "workflow", "status": row[0], "count": row[1]}
        for row in session.execute(
            select(Workflow.state, func.count()).group_by(Workflow.state)
        )
    ]
    trend = [
        {"type": row[0], "count": row[1]}
        for row in session.execute(
            select(ModelTask.task_type, func.count())
            .where(ModelTask.created_at >= since)
            .group_by(ModelTask.task_type)
        )
    ]
    credit_rows = session.execute(
        select(CreditLedger.entry_type, func.coalesce(func.sum(CreditLedger.amount), 0))
        .where(CreditLedger.created_at >= since)
        .group_by(CreditLedger.entry_type)
    )
    recent = [
        _data(
            task,
            (
                "id",
                "user_id",
                "task_type",
                "status",
                "model_id",
                "created_at",
                "updated_at",
            ),
        )
        for task in session.scalars(
            select(ModelTask).order_by(ModelTask.created_at.desc()).limit(10)
        )
    ]
    return _ok(
        request_id,
        "ADMIN_OVERVIEW",
        {
            "users": {"total": users_total, "active": users_active},
            "tasks": {
                "total": model_total + workflow_total,
                "model_tasks": model_total,
                "workflows": workflow_total,
                "by_status": model_status + workflow_status,
                "today_trend": trend,
            },
            "credits_today": {row[0]: row[1] for row in credit_rows},
            "recent_tasks": recent,
        },
    )


@router.get("/menus/tree", response_model=ApiResponse[dict[str, Any]])
def menu_tree(
    context: Annotated[Context, Depends(allowed("admin:rbac:read"))],
    request_id: Annotated[str, Depends(get_request_id)],
) -> ApiResponse[dict[str, Any]]:
    return _ok(
        request_id,
        "ADMIN_MENU_TREE",
        {"items": _menus(context.session, context.permissions)},
    )


@router.get("/users", response_model=ApiResponse[dict[str, Any]])
def users(
    context: Annotated[Context, Depends(allowed("admin:users:read"))],
    request_id: Annotated[str, Depends(get_request_id)],
    page: int = Query(1, ge=1),
    page_size: int = Query(30, ge=1, le=1000),
    keyword: str | None = Query(None, max_length=254),
    status_value: str | None = Query(None, alias="status"),
    start_at: datetime | None = None,
    end_at: datetime | None = None,
) -> ApiResponse[dict[str, Any]]:
    page, page_size = _page(page, page_size)
    conditions: list[Any] = []
    if keyword:
        conditions.append(User.email.ilike(f"%{keyword.strip()}%"))
    if status_value in {"active", "disabled"}:
        conditions.append(User.status == status_value)
    if start_at:
        conditions.append(User.created_at >= start_at)
    if end_at:
        conditions.append(User.created_at <= end_at)
    statement = (
        select(User, CreditAccount.balance)
        .outerjoin(CreditAccount, CreditAccount.user_id == User.id)
        .where(*conditions)
    )
    total = (
        context.session.scalar(
            select(func.count()).select_from(User).where(*conditions)
        )
        or 0
    )
    rows = context.session.execute(
        statement.order_by(User.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = [
        _data(user, ("id", "email", "status", "created_at", "updated_at"))
        | {"credit_balance": balance or 0}
        for user, balance in rows
    ]
    return _ok(
        request_id,
        "ADMIN_USERS",
        {"items": items, "total": total, "page": page, "page_size": page_size},
    )


@router.get("/users/{user_id}", response_model=ApiResponse[dict[str, Any]])
def user_detail(
    user_id: str,
    context: Annotated[Context, Depends(allowed("admin:users:read"))],
    request_id: Annotated[str, Depends(get_request_id)],
) -> ApiResponse[dict[str, Any]]:
    user = context.session.get(User, user_id)
    if user is None:
        raise ApiError("ADMIN_RESOURCE_NOT_FOUND", "Resource not found", 404)
    account = context.session.get(CreditAccount, user_id)
    return _ok(
        request_id,
        "ADMIN_USER",
        {
            "user": _data(user, ("id", "email", "status", "created_at", "updated_at"))
            | {"credit_balance": account.balance if account else 0}
        },
    )


@router.patch("/users/{user_id}/status", response_model=ApiResponse[dict[str, Any]])
def update_user_status(
    user_id: str,
    body: StatusRequest,
    context: Annotated[Context, Depends(allowed("admin:users:manage"))],
    request_id: Annotated[str, Depends(get_request_id)],
) -> ApiResponse[dict[str, Any]]:
    if body.status not in {"active", "disabled"}:
        raise ApiError("VALIDATION_ERROR", "Invalid user status", 422)
    user = context.session.get(User, user_id)
    if user is None:
        raise ApiError("ADMIN_RESOURCE_NOT_FOUND", "Resource not found", 404)
    before = _data(user, ("status",))
    user.status = body.status
    _audit(
        context,
        action="admin.users.status.update",
        resource_type="user",
        resource_id=user.id,
        before=before,
        after={"status": user.status},
    )
    context.session.commit()
    return _ok(
        request_id,
        "ADMIN_USER_STATUS_UPDATED",
        {"user": _data(user, ("id", "email", "status", "updated_at"))},
    )


@router.patch("/users/batch-status", response_model=ApiResponse[dict[str, Any]])
def batch_update_user_status(
    body: BatchStatusRequest,
    context: Annotated[Context, Depends(allowed("admin:users:manage"))],
    request_id: Annotated[str, Depends(get_request_id)],
) -> ApiResponse[dict[str, Any]]:
    if body.status not in {"active", "disabled"} or len(set(body.user_ids)) != len(
        body.user_ids
    ):
        raise ApiError("VALIDATION_ERROR", "Invalid batch status request", 422)
    users = list(
        context.session.scalars(select(User).where(User.id.in_(body.user_ids)))
    )
    if len(users) != len(body.user_ids):
        raise ApiError("ADMIN_RESOURCE_NOT_FOUND", "Resource not found", 404)
    before = {user.id: user.status for user in users}
    for user in users:
        user.status = body.status
    _audit(
        context,
        action="admin.users.batch_status.update",
        resource_type="user_batch",
        resource_id=None,
        before={"statuses": before},
        after={"status": body.status, "count": len(users)},
    )
    context.session.commit()
    return _ok(request_id, "ADMIN_USERS_STATUS_UPDATED", {"updated": len(users)})


@router.get("/tasks", response_model=ApiResponse[dict[str, Any]])
def tasks(
    context: Annotated[Context, Depends(allowed("admin:tasks:read"))],
    request_id: Annotated[str, Depends(get_request_id)],
    page: int = Query(1, ge=1, le=1000),
    page_size: int = Query(30, ge=1, le=1000),
    keyword: str | None = Query(None, max_length=128),
    category: str | None = Query(
        None, pattern="^(short_drama|video_translation|ai_video)$"
    ),
    task_type: str | None = None,
    status_value: str | None = Query(None, alias="status"),
    user_id: str | None = None,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
) -> ApiResponse[dict[str, Any]]:
    """统一呈现短剧/翻译工作流及 AI 模型任务，按创建时间全局分页。"""
    page, page_size = _page(page, page_size)
    model_conditions: list[Any] = []
    workflow_conditions: list[Any] = []
    if keyword:
        value = f"%{keyword.strip()}%"
        model_conditions.append(
            or_(ModelTask.id.ilike(value), ModelTask.provider_task_id.ilike(value))
        )
        workflow_conditions.append(
            or_(Workflow.id.ilike(value), Project.id.ilike(value))
        )
    if task_type:
        model_conditions.append(ModelTask.task_type == task_type)
    if status_value:
        model_conditions.append(ModelTask.status == status_value)
        workflow_conditions.append(Workflow.state == status_value)
    if user_id:
        model_conditions.append(ModelTask.user_id == user_id)
        workflow_conditions.append(Workflow.user_id == user_id)
    if start_at:
        model_conditions.append(ModelTask.created_at >= start_at)
        workflow_conditions.append(Workflow.created_at >= start_at)
    if end_at:
        model_conditions.append(ModelTask.created_at <= end_at)
        workflow_conditions.append(Workflow.created_at <= end_at)

    include_models = category in (None, "ai_video")
    include_workflows = category != "ai_video" and task_type is None
    if category == "short_drama":
        workflow_conditions.append(Project.product == "short_drama_narration")
    elif category == "video_translation":
        workflow_conditions.append(Project.product == "video_translation")

    model_total = (
        (
            context.session.scalar(
                select(func.count()).select_from(ModelTask).where(*model_conditions)
            )
            or 0
        )
        if include_models
        else 0
    )
    workflow_statement = (
        select(Workflow, Project.product)
        .join(Project, Project.id == Workflow.project_id)
        .where(*workflow_conditions)
    )
    workflow_total = (
        (
            context.session.scalar(
                select(func.count())
                .select_from(Workflow)
                .join(Project, Project.id == Workflow.project_id)
                .where(*workflow_conditions)
            )
            or 0
        )
        if include_workflows
        else 0
    )

    # Fetching the top N rows of each ordered source is sufficient to merge page N globally.
    take = page * page_size
    merged: list[dict[str, Any]] = []
    if include_models:
        model_fields = (
            "id",
            "project_id",
            "user_id",
            "model_id",
            "play_mode_id",
            "task_type",
            "status",
            "provider_task_id",
            "resolution",
            "requested_duration_seconds",
            "default_credits_charged",
            "final_credits",
            "error_code",
            "created_at",
            "updated_at",
        )
        merged.extend(
            _data(row, model_fields)
            | {
                "user_name": user_name,
                "category": "ai_video",
                "source": "model_task",
            }
            for row, user_name in context.session.execute(
                select(ModelTask, User.email)
                .outerjoin(User, User.id == ModelTask.user_id)
                .where(*model_conditions)
                .order_by(ModelTask.created_at.desc())
                .limit(take)
            )
        )
    if include_workflows:
        workflow_fields = (
            "id",
            "project_id",
            "user_id",
            "state",
            "state_version",
            "created_at",
            "updated_at",
        )
        for workflow, product, user_name in context.session.execute(
            workflow_statement.add_columns(User.email)
            .outerjoin(User, User.id == Workflow.user_id)
            .order_by(Workflow.created_at.desc())
            .limit(take)
        ):
            merged.append(
                _data(workflow, workflow_fields)
                | {
                    "user_name": user_name,
                    "status": workflow.state,
                    "category": "video_translation"
                    if product == "video_translation"
                    else "short_drama",
                    "product": product,
                    "source": "workflow",
                }
            )
    merged.sort(key=lambda row: (row["created_at"], row["id"]), reverse=True)
    start_index = (page - 1) * page_size
    return _ok(
        request_id,
        "ADMIN_TASKS",
        {
            "items": merged[start_index : start_index + page_size],
            "total": model_total + workflow_total,
            "page": page,
            "page_size": page_size,
        },
    )


@router.get("/tasks/{task_id}", response_model=ApiResponse[dict[str, Any]])
def task_detail(
    task_id: str,
    context: Annotated[Context, Depends(allowed("admin:tasks:read"))],
    request_id: Annotated[str, Depends(get_request_id)],
) -> ApiResponse[dict[str, Any]]:
    task = context.session.get(ModelTask, task_id)
    if task is not None:
        fields = (
            "id",
            "project_id",
            "user_id",
            "model_id",
            "play_mode_id",
            "provider_id",
            "task_type",
            "status",
            "provider_task_id",
            "prompt",
            "resolution",
            "ratio",
            "requested_duration_seconds",
            "audio_enabled",
            "default_credits_charged",
            "final_credits",
            "input_token",
            "output_token",
            "actual_output_duration_seconds",
            "actual_output_image_count",
            "settlement_status",
            "attempt_count",
            "error_code",
            "error_message",
            "submitted_at",
            "next_poll_at",
            "created_at",
            "updated_at",
        )
        input_assets = list(
            context.session.execute(
                select(ModelTaskAsset, Asset)
                .join(Asset, Asset.id == ModelTaskAsset.asset_id)
                .where(ModelTaskAsset.task_id == task.id)
                .order_by(ModelTaskAsset.sort_order, ModelTaskAsset.id)
            )
        )
        outputs = list(
            context.session.scalars(
                select(ModelTaskOutput)
                .where(ModelTaskOutput.task_id == task.id)
                .order_by(ModelTaskOutput.sort_order, ModelTaskOutput.id)
            )
        )
        project = context.session.get(Project, task.project_id) if task.project_id else None
        return _ok(
            request_id,
            "ADMIN_TASK",
            {
                "task": _data(task, fields)
                | {
                    "user_name": _user_name(context, task.user_id),
                    "category": "ai_video",
                    "source": "model_task",
                },
                "input": {
                    "prompt": task.prompt,
                    "configuration": {
                        "model_id": task.model_id,
                        "play_mode_id": task.play_mode_id,
                        "provider_id": task.provider_id,
                        "task_type": task.task_type,
                        "resolution": task.resolution,
                        "ratio": task.ratio,
                        "requested_duration_seconds": task.requested_duration_seconds,
                        "audio_enabled": task.audio_enabled,
                    },
                    "source_assets": [
                        _asset_media(asset)
                        | {
                            "input_type": link.input_type,
                            "mentioned": link.is_mentioned,
                            "sort_order": link.sort_order,
                        }
                        for link, asset in input_assets
                    ],
                    "project": _project_input(context, project)["project"],
                },
                "result": {
                    "outputs": [
                        {
                            "id": output.id,
                            "kind": output.output_type,
                            "url": output.cdn_url,
                            "text": output.text_content,
                            "content_type": output.content_type,
                            "size_bytes": output.size_bytes,
                            "duration_seconds": output.duration_seconds,
                            "sort_order": output.sort_order,
                        }
                        for output in outputs
                    ],
                    "error": {
                        "code": task.error_code,
                        "message": task.error_message,
                    }
                    if task.error_code or task.error_message
                    else None,
                    "usage": {
                        "default_credits_charged": task.default_credits_charged,
                        "final_credits": task.final_credits,
                        "input_token": task.input_token,
                        "output_token": task.output_token,
                        "actual_output_duration_seconds": task.actual_output_duration_seconds,
                        "actual_output_image_count": task.actual_output_image_count,
                        "settlement_status": task.settlement_status,
                    },
                },
            },
        )
    workflow = context.session.get(Workflow, task_id)
    if workflow is None:
        raise ApiError("ADMIN_RESOURCE_NOT_FOUND", "Resource not found", 404)
    project = context.session.get(Project, workflow.project_id)
    artifacts = list(
        context.session.scalars(
            select(RegisteredArtifact)
            .where(RegisteredArtifact.project_id == workflow.project_id)
            .order_by(RegisteredArtifact.created_at, RegisteredArtifact.id)
        )
    )
    return _ok(
        request_id,
        "ADMIN_TASK",
        {
            "task": _data(
                workflow,
                (
                    "id",
                    "project_id",
                    "user_id",
                    "template_snapshot_id",
                    "state",
                    "state_version",
                    "created_at",
                    "updated_at",
                ),
            )
            | {
                "user_name": _user_name(context, workflow.user_id),
                "status": workflow.state,
                "product": project.product if project else None,
                "category": "video_translation"
                if project and project.product == "video_translation"
                else "short_drama",
                "source": "workflow",
            },
            "input": _project_input(context, project),
            "result": {
                "artifacts": [_artifact_media(artifact) for artifact in artifacts],
                "error": None,
            },
            "execution": {"nodes": _workflow_execution(context, workflow.id)},
        },
    )


@router.get("/models", response_model=ApiResponse[dict[str, Any]])
def models(
    context: Annotated[Context, Depends(allowed("admin:models:read"))],
    request_id: Annotated[str, Depends(get_request_id)],
    page: int = Query(1, ge=1),
    page_size: int = Query(30, ge=1, le=1000),
    model_type: str | None = None,
    keyword: str | None = Query(None, max_length=128),
) -> ApiResponse[dict[str, Any]]:
    page, page_size = _page(page, page_size)
    cond: list[Any] = []
    if model_type:
        cond.append(Model.model_type == model_type)
    if keyword:
        cond.append(Model.display_name.ilike(f"%{keyword.strip()}%"))
    total = (
        context.session.scalar(select(func.count()).select_from(Model).where(*cond))
        or 0
    )
    items = [
        _data(
            model,
            (
                "id",
                "display_name",
                "model_type",
                "description",
                "category",
                "sort_order",
                "is_enabled",
                "is_default",
                "created_at",
                "updated_at",
            ),
        )
        for model in context.session.scalars(
            select(Model)
            .where(*cond)
            .order_by(Model.sort_order, Model.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ]
    return _ok(
        request_id,
        "ADMIN_MODELS",
        {"items": items, "total": total, "page": page, "page_size": page_size},
    )


def _patch_instance(
    instance: object, body: StrictModel, allowed_fields: tuple[str, ...]
) -> tuple[dict[str, Any], dict[str, Any]]:
    before = {field: getattr(instance, field) for field in allowed_fields}
    for field in allowed_fields:
        value = getattr(body, field, None)
        if value is not None:
            setattr(instance, field, value)
    after = {field: getattr(instance, field) for field in allowed_fields}
    return before, after


@router.patch("/models/{model_id}", response_model=ApiResponse[dict[str, Any]])
def update_model(
    model_id: str,
    body: ModelUpdateRequest,
    context: Annotated[Context, Depends(allowed("admin:models:manage"))],
    request_id: Annotated[str, Depends(get_request_id)],
) -> ApiResponse[dict[str, Any]]:
    model = context.session.get(Model, model_id)
    if model is None:
        raise ApiError("ADMIN_RESOURCE_NOT_FOUND", "Resource not found", 404)
    before, after = _patch_instance(
        model,
        body,
        (
            "display_name",
            "description",
            "category",
            "sort_order",
            "is_enabled",
            "is_default",
        ),
    )
    _audit(
        context,
        action="admin.models.update",
        resource_type="model",
        resource_id=model.id,
        before=before,
        after=after,
    )
    context.session.commit()
    return _ok(
        request_id,
        "ADMIN_MODEL_UPDATED",
        {
            "model": _data(
                model,
                (
                    "id",
                    "display_name",
                    "model_type",
                    "description",
                    "category",
                    "sort_order",
                    "is_enabled",
                    "is_default",
                    "updated_at",
                ),
            )
        },
    )


@router.get("/play-modes", response_model=ApiResponse[dict[str, Any]])
def play_modes(
    context: Annotated[Context, Depends(allowed("admin:models:read"))],
    request_id: Annotated[str, Depends(get_request_id)],
    model_id: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(30, ge=1, le=1000),
) -> ApiResponse[dict[str, Any]]:
    page, page_size = _page(page, page_size)
    conditions: list[Any] = []
    if model_id:
        conditions.append(ModelPlayMode.model_id == model_id)
    statement = select(ModelPlayMode).where(*conditions)
    total = (
        context.session.scalar(
            select(func.count()).select_from(ModelPlayMode).where(*conditions)
        )
        or 0
    )
    rows = context.session.scalars(
        statement.order_by(ModelPlayMode.model_id, ModelPlayMode.sort_order)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    fields = (
        "id",
        "model_id",
        "code",
        "display_name",
        "description",
        "default_credits",
        "active_provider_id",
        "supports_generate_audio",
        "is_enabled",
        "is_default",
        "sort_order",
        "updated_at",
    )
    return _ok(
        request_id,
        "ADMIN_PLAY_MODES",
        {
            "items": [_data(row, fields) for row in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
        },
    )


@router.patch("/play-modes/{play_mode_id}", response_model=ApiResponse[dict[str, Any]])
def update_play_mode(
    play_mode_id: str,
    body: PlayModeUpdateRequest,
    context: Annotated[Context, Depends(allowed("admin:models:manage"))],
    request_id: Annotated[str, Depends(get_request_id)],
) -> ApiResponse[dict[str, Any]]:
    mode = context.session.get(ModelPlayMode, play_mode_id)
    if mode is None:
        raise ApiError("ADMIN_RESOURCE_NOT_FOUND", "Resource not found", 404)
    before, after = _patch_instance(
        mode,
        body,
        (
            "display_name",
            "description",
            "default_credits",
            "is_enabled",
            "is_default",
            "sort_order",
        ),
    )
    _audit(
        context,
        action="admin.play_modes.update",
        resource_type="play_mode",
        resource_id=mode.id,
        before=before,
        after=after,
    )
    context.session.commit()
    return _ok(
        request_id,
        "ADMIN_PLAY_MODE_UPDATED",
        {
            "play_mode": _data(
                mode,
                (
                    "id",
                    "model_id",
                    "code",
                    "display_name",
                    "description",
                    "default_credits",
                    "is_enabled",
                    "is_default",
                    "sort_order",
                    "updated_at",
                ),
            )
        },
    )


@router.get("/providers", response_model=ApiResponse[dict[str, Any]])
def providers(
    context: Annotated[Context, Depends(allowed("admin:models:read"))],
    request_id: Annotated[str, Depends(get_request_id)],
    play_mode_id: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(30, ge=1, le=1000),
) -> ApiResponse[dict[str, Any]]:
    page, page_size = _page(page, page_size)
    conditions: list[Any] = []
    if play_mode_id:
        conditions.append(ModelPlayModeProvider.play_mode_id == play_mode_id)
    statement = select(ModelPlayModeProvider).where(*conditions)
    total = (
        context.session.scalar(
            select(func.count()).select_from(ModelPlayModeProvider).where(*conditions)
        )
        or 0
    )
    rows = context.session.scalars(
        statement.order_by(ModelPlayModeProvider.play_mode_id, ModelPlayModeProvider.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    fields = (
        "id",
        "play_mode_id",
        "provider_code",
        "provider_model_id",
        "submit_url",
        "status_query_url",
        "status_query_method",
        "api_key",
        "is_enabled",
        "updated_at",
    )
    return _ok(
        request_id,
        "ADMIN_PROVIDERS",
        {
            "items": [_data(row, fields, secret_fields={"api_key"}) for row in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
        },
    )


@router.patch("/providers/{provider_id}", response_model=ApiResponse[dict[str, Any]])
def update_provider(
    provider_id: str,
    body: ProviderUpdateRequest,
    context: Annotated[Context, Depends(allowed("admin:models:manage"))],
    request_id: Annotated[str, Depends(get_request_id)],
) -> ApiResponse[dict[str, Any]]:
    provider = context.session.get(ModelPlayModeProvider, provider_id)
    if provider is None:
        raise ApiError("ADMIN_RESOURCE_NOT_FOUND", "Resource not found", 404)
    allowed_fields = (
        "provider_model_id",
        "submit_url",
        "status_query_url",
        "status_query_method",
        "api_key",
        "is_enabled",
    )
    before, after = _patch_instance(provider, body, allowed_fields)
    before["api_key"] = "********" if before["api_key"] else None
    after["api_key"] = "********" if after["api_key"] else None
    _audit(
        context,
        action="admin.providers.update",
        resource_type="provider",
        resource_id=provider.id,
        before=before,
        after=after,
    )
    context.session.commit()
    return _ok(
        request_id,
        "ADMIN_PROVIDER_UPDATED",
        {
            "provider": _data(
                provider,
                (
                    "id",
                    "play_mode_id",
                    "provider_code",
                    "provider_model_id",
                    "submit_url",
                    "status_query_url",
                    "status_query_method",
                    "api_key",
                    "is_enabled",
                    "updated_at",
                ),
                secret_fields={"api_key"},
            )
        },
    )


@router.get("/system-configs", response_model=ApiResponse[dict[str, Any]])
def system_configs(
    context: Annotated[Context, Depends(allowed("admin:configs:read"))],
    request_id: Annotated[str, Depends(get_request_id)],
    keyword: str | None = Query(None, max_length=128),
    page: int = Query(1, ge=1),
    page_size: int = Query(30, ge=1, le=1000),
) -> ApiResponse[dict[str, Any]]:
    page, page_size = _page(page, page_size)
    conditions: list[Any] = []
    if keyword:
        conditions.append(SystemConfig.config_key.ilike(f"%{keyword.strip()}%"))
    statement = select(SystemConfig).where(*conditions)
    total = (
        context.session.scalar(
            select(func.count()).select_from(SystemConfig).where(*conditions)
        )
        or 0
    )
    rows = context.session.scalars(
        statement.order_by(SystemConfig.config_key)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = []
    for row in rows:
        item = _data(
            row,
            (
                "id",
                "config_key",
                "value",
                "description",
                "is_secret",
                "updated_by",
                "created_at",
                "updated_at",
            ),
        )
        if row.is_secret:
            item["value"] = "********" if row.value else None
        items.append(item)
    return _ok(
        request_id,
        "ADMIN_SYSTEM_CONFIGS",
        {"items": items, "total": total, "page": page, "page_size": page_size},
    )


@router.patch(
    "/system-configs/{config_key}", response_model=ApiResponse[dict[str, Any]]
)
def put_system_config(
    config_key: str,
    body: ConfigRequest,
    context: Annotated[Context, Depends(allowed("admin:configs:manage"))],
    request_id: Annotated[str, Depends(get_request_id)],
) -> ApiResponse[dict[str, Any]]:
    key = config_key.strip()
    if not key or len(key) > 128 or any(not (c.isalnum() or c in "._-") for c in key):
        raise ApiError("VALIDATION_ERROR", "Invalid config key", 422)
    row = context.session.scalar(
        select(SystemConfig).where(SystemConfig.config_key == key)
    )
    if row is None:
        row = SystemConfig(
            id=new_id("cfg"),
            config_key=key,
            value=body.value,
            description=body.description,
            is_secret=body.is_secret,
            updated_by=context.admin.id,
        )
        context.session.add(row)
        before = None
    else:
        before = {
            "value": "********" if row.is_secret and row.value else row.value,
            "description": row.description,
            "is_secret": row.is_secret,
        }
        # secret fields may only be changed when a non-null replacement is supplied.
        if body.value is not None:
            row.value = body.value
        row.description, row.is_secret, row.updated_by = (
            body.description,
            row.is_secret or body.is_secret,
            context.admin.id,
        )
    after = {
        "value": "********" if row.is_secret and row.value else row.value,
        "description": row.description,
        "is_secret": row.is_secret,
    }
    _audit(
        context,
        action="admin.system_configs.put",
        resource_type="system_config",
        resource_id=key,
        before=before,
        after=after,
    )
    context.session.commit()
    return _ok(
        request_id,
        "ADMIN_SYSTEM_CONFIG_UPDATED",
        {
            "config": _data(
                row, ("id", "config_key", "description", "is_secret", "updated_at")
            )
            | {"value": "********" if row.is_secret and row.value else row.value}
        },
    )


@router.get("/credit-ledger", response_model=ApiResponse[dict[str, Any]])
def credit_ledger(
    context: Annotated[Context, Depends(allowed("admin:logs:read"))],
    request_id: Annotated[str, Depends(get_request_id)],
    page: int = Query(1, ge=1),
    page_size: int = Query(30, ge=1, le=1000),
    user_id: str | None = None,
    entry_type: str | None = None,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
) -> ApiResponse[dict[str, Any]]:
    page, page_size = _page(page, page_size)
    cond: list[Any] = []
    if user_id:
        cond.append(CreditLedger.user_id == user_id)
    if entry_type:
        cond.append(CreditLedger.entry_type == entry_type)
    if start_at:
        cond.append(CreditLedger.created_at >= start_at)
    if end_at:
        cond.append(CreditLedger.created_at <= end_at)
    total = (
        context.session.scalar(
            select(func.count()).select_from(CreditLedger).where(*cond)
        )
        or 0
    )
    entries = context.session.scalars(
        select(CreditLedger)
        .where(*cond)
        .order_by(CreditLedger.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return _ok(
        request_id,
        "ADMIN_CREDIT_LEDGER",
        {
            "items": [
                _data(
                    row,
                    (
                        "id",
                        "user_id",
                        "entry_type",
                        "amount",
                        "idempotency_key",
                        "reference_id",
                        "reason",
                        "created_at",
                    ),
                )
                for row in entries
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
        },
    )


@router.get("/operation-logs", response_model=ApiResponse[dict[str, Any]])
def operation_logs(
    context: Annotated[Context, Depends(allowed("admin:logs:read"))],
    request_id: Annotated[str, Depends(get_request_id)],
    page: int = Query(1, ge=1),
    page_size: int = Query(30, ge=1, le=1000),
    admin_id: str | None = None,
    action: str | None = Query(None, max_length=128),
    start_at: datetime | None = None,
    end_at: datetime | None = None,
) -> ApiResponse[dict[str, Any]]:
    page, page_size = _page(page, page_size)
    cond: list[Any] = []
    if admin_id:
        cond.append(AdminOperationLog.admin_id == admin_id)
    if action:
        cond.append(AdminOperationLog.action.ilike(f"%{action.strip()}%"))
    if start_at:
        cond.append(AdminOperationLog.created_at >= start_at)
    if end_at:
        cond.append(AdminOperationLog.created_at <= end_at)
    total = (
        context.session.scalar(
            select(func.count()).select_from(AdminOperationLog).where(*cond)
        )
        or 0
    )
    records = context.session.scalars(
        select(AdminOperationLog)
        .where(*cond)
        .order_by(AdminOperationLog.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    fields = (
        "id",
        "admin_id",
        "username",
        "action",
        "resource_type",
        "resource_id",
        "request_id",
        "ip_address",
        "method",
        "path",
        "before_data",
        "after_data",
        "result",
        "created_at",
    )
    return _ok(
        request_id,
        "ADMIN_OPERATION_LOGS",
        {
            "items": [_data(row, fields) for row in records],
            "total": total,
            "page": page,
            "page_size": page_size,
        },
    )


def _replace_roles(session: Session, admin_id: str, role_ids: list[str]) -> None:
    if len(set(role_ids)) != len(role_ids):
        raise ApiError("VALIDATION_ERROR", "Duplicate roles", 422)
    if role_ids:
        count = (
            session.scalar(
                select(func.count())
                .select_from(AdminRole)
                .where(AdminRole.id.in_(role_ids))
            )
            or 0
        )
        if count != len(role_ids):
            raise ApiError("VALIDATION_ERROR", "Unknown role", 422)
    session.query(AdminUserRole).filter(AdminUserRole.admin_id == admin_id).delete(
        synchronize_session=False
    )
    session.add_all(
        AdminUserRole(admin_id=admin_id, role_id=role_id) for role_id in role_ids
    )


@router.get("/admins", response_model=ApiResponse[dict[str, Any]])
def admins(
    context: Annotated[Context, Depends(allowed("admin:rbac:read"))],
    request_id: Annotated[str, Depends(get_request_id)],
    page: int = Query(1, ge=1),
    page_size: int = Query(30, ge=1, le=1000),
    keyword: str | None = Query(None, max_length=64),
    status_value: str | None = Query(None, alias="status"),
) -> ApiResponse[dict[str, Any]]:
    page, page_size = _page(page, page_size)
    conditions: list[Any] = []
    if keyword:
        conditions.append(
            or_(
                AdminUser.username.ilike(f"%{keyword.strip()}%"),
                AdminUser.display_name.ilike(f"%{keyword.strip()}%"),
            )
        )
    if status_value in {"active", "disabled"}:
        conditions.append(AdminUser.status == status_value)
    total = (
        context.session.scalar(
            select(func.count()).select_from(AdminUser).where(*conditions)
        )
        or 0
    )
    rows = context.session.scalars(
        select(AdminUser)
        .where(*conditions)
        .order_by(AdminUser.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return _ok(
        request_id,
        "ADMIN_ADMINS",
        {
            "items": [_admin_data(context.session, row) for row in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
        },
    )


@router.post(
    "/admins",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiResponse[dict[str, Any]],
)
def create_admin(
    body: AdminCreateRequest,
    context: Annotated[Context, Depends(allowed("admin:rbac:manage"))],
    request_id: Annotated[str, Depends(get_request_id)],
) -> ApiResponse[dict[str, Any]]:
    try:
        username = normalize_username(body.username)
        validate_password(body.password)
    except ValueError as error:
        raise ApiError(
            "VALIDATION_ERROR", "Invalid administrator input", 422
        ) from error
    if context.session.scalar(
        select(AdminUser.id).where(AdminUser.username == username)
    ):
        raise ApiError("ADMIN_CONFLICT", "Administrator already exists", 409)
    admin = AdminUser(
        id=new_id("adm"),
        username=username,
        display_name=body.display_name.strip(),
        password_hash=password_hasher(get_settings(context.request)).hash(
            body.password
        ),
        is_superuser=body.is_superuser,
    )
    context.session.add(admin)
    context.session.flush()
    _replace_roles(context.session, admin.id, body.role_ids)
    _audit(
        context,
        action="admin.admins.create",
        resource_type="admin",
        resource_id=admin.id,
        after={
            "username": username,
            "display_name": admin.display_name,
            "role_ids": body.role_ids,
            "is_superuser": admin.is_superuser,
        },
    )
    context.session.commit()
    return _ok(
        request_id, "ADMIN_CREATED", {"admin": _admin_data(context.session, admin)}
    )


@router.patch("/admins/{admin_id}", response_model=ApiResponse[dict[str, Any]])
def update_admin(
    admin_id: str,
    body: AdminUpdateRequest,
    context: Annotated[Context, Depends(allowed("admin:rbac:manage"))],
    request_id: Annotated[str, Depends(get_request_id)],
) -> ApiResponse[dict[str, Any]]:
    admin = context.session.get(AdminUser, admin_id)
    if admin is None:
        raise ApiError("ADMIN_RESOURCE_NOT_FOUND", "Resource not found", 404)
    if admin.is_superuser and body.status == "disabled":
        raise ApiError(
            "ADMIN_SUPERUSER_PROTECTED", "Super administrator cannot be disabled", 409
        )
    before = {
        "display_name": admin.display_name,
        "status": admin.status,
        "roles": roles_for(context.session, admin.id),
    }
    if body.display_name is not None:
        admin.display_name = body.display_name.strip()
    if body.status is not None:
        if body.status not in {"active", "disabled"}:
            raise ApiError("VALIDATION_ERROR", "Invalid administrator status", 422)
        admin.status = body.status
    if body.password is not None:
        try:
            validate_password(body.password)
        except ValueError as error:
            raise ApiError("VALIDATION_ERROR", "Invalid password", 422) from error
        admin.password_hash = password_hasher(get_settings(context.request)).hash(
            body.password
        )
        admin.password_version += 1
    if body.role_ids is not None:
        _replace_roles(context.session, admin.id, body.role_ids)
    after = {
        "display_name": admin.display_name,
        "status": admin.status,
        "roles": roles_for(context.session, admin.id),
        "password_changed": body.password is not None,
    }
    _audit(
        context,
        action="admin.admins.update",
        resource_type="admin",
        resource_id=admin.id,
        before=before,
        after=after,
    )
    context.session.commit()
    return _ok(
        request_id, "ADMIN_UPDATED", {"admin": _admin_data(context.session, admin)}
    )


def _replace_permissions(
    session: Session, role_id: str, permission_ids: list[str]
) -> None:
    if len(set(permission_ids)) != len(permission_ids):
        raise ApiError("VALIDATION_ERROR", "Duplicate permissions", 422)
    if permission_ids:
        count = (
            session.scalar(
                select(func.count())
                .select_from(AdminPermission)
                .where(AdminPermission.id.in_(permission_ids))
            )
            or 0
        )
        if count != len(permission_ids):
            raise ApiError("VALIDATION_ERROR", "Unknown permission", 422)
    session.query(AdminRolePermission).filter(
        AdminRolePermission.role_id == role_id
    ).delete(synchronize_session=False)
    session.add_all(
        AdminRolePermission(role_id=role_id, permission_id=permission_id)
        for permission_id in permission_ids
    )


@router.get("/roles", response_model=ApiResponse[dict[str, Any]])
def roles(
    context: Annotated[Context, Depends(allowed("admin:rbac:read"))],
    request_id: Annotated[str, Depends(get_request_id)],
    page: int = Query(1, ge=1),
    page_size: int = Query(30, ge=1, le=1000),
    keyword: str | None = Query(None, max_length=128),
) -> ApiResponse[dict[str, Any]]:
    page, page_size = _page(page, page_size)
    conditions: list[Any] = []
    if keyword:
        conditions.append(
            or_(
                AdminRole.code.ilike(f"%{keyword.strip()}%"),
                AdminRole.name.ilike(f"%{keyword.strip()}%"),
            )
        )
    total = (
        context.session.scalar(
            select(func.count()).select_from(AdminRole).where(*conditions)
        )
        or 0
    )
    result = []
    for role in context.session.scalars(
        select(AdminRole)
        .where(*conditions)
        .order_by(AdminRole.code)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ):
        ids = list(
            context.session.scalars(
                select(AdminRolePermission.permission_id).where(
                    AdminRolePermission.role_id == role.id
                )
            )
        )
        result.append(
            _data(
                role,
                (
                    "id",
                    "code",
                    "name",
                    "description",
                    "is_system",
                    "created_at",
                    "updated_at",
                ),
            )
            | {"permission_ids": ids}
        )
    return _ok(
        request_id,
        "ADMIN_ROLES",
        {"items": result, "total": total, "page": page, "page_size": page_size},
    )


@router.post(
    "/roles",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiResponse[dict[str, Any]],
)
def create_role(
    body: RoleRequest,
    context: Annotated[Context, Depends(allowed("admin:rbac:manage"))],
    request_id: Annotated[str, Depends(get_request_id)],
) -> ApiResponse[dict[str, Any]]:
    try:
        code = normalize_username(body.code)
    except ValueError as error:
        raise ApiError("VALIDATION_ERROR", "Invalid role code", 422) from error
    if context.session.scalar(select(AdminRole.id).where(AdminRole.code == code)):
        raise ApiError("ADMIN_CONFLICT", "Role already exists", 409)
    role = AdminRole(
        id=new_id("role"),
        code=code,
        name=body.name.strip(),
        description=body.description,
    )
    context.session.add(role)
    context.session.flush()
    _replace_permissions(context.session, role.id, body.permission_ids)
    _audit(
        context,
        action="admin.roles.create",
        resource_type="role",
        resource_id=role.id,
        after={"code": code, "permission_ids": body.permission_ids},
    )
    context.session.commit()
    return _ok(
        request_id,
        "ADMIN_ROLE_CREATED",
        {
            "role": _data(
                role,
                (
                    "id",
                    "code",
                    "name",
                    "description",
                    "is_system",
                    "created_at",
                    "updated_at",
                ),
            )
            | {"permission_ids": body.permission_ids}
        },
    )


@router.patch("/roles/{role_id}", response_model=ApiResponse[dict[str, Any]])
def update_role(
    role_id: str,
    body: RoleRequest,
    context: Annotated[Context, Depends(allowed("admin:rbac:manage"))],
    request_id: Annotated[str, Depends(get_request_id)],
) -> ApiResponse[dict[str, Any]]:
    role = context.session.get(AdminRole, role_id)
    if role is None:
        raise ApiError("ADMIN_RESOURCE_NOT_FOUND", "Resource not found", 404)
    if role.is_system:
        raise ApiError(
            "ADMIN_SYSTEM_ROLE_PROTECTED", "System role cannot be changed", 409
        )
    try:
        code = normalize_username(body.code)
    except ValueError as error:
        raise ApiError("VALIDATION_ERROR", "Invalid role code", 422) from error
    conflict = context.session.scalar(
        select(AdminRole.id).where(
            and_(AdminRole.code == code, AdminRole.id != role.id)
        )
    )
    if conflict:
        raise ApiError("ADMIN_CONFLICT", "Role already exists", 409)
    before = {
        "code": role.code,
        "name": role.name,
        "permission_ids": list(
            context.session.scalars(
                select(AdminRolePermission.permission_id).where(
                    AdminRolePermission.role_id == role.id
                )
            )
        ),
    }
    role.code, role.name, role.description = code, body.name.strip(), body.description
    _replace_permissions(context.session, role.id, body.permission_ids)
    _audit(
        context,
        action="admin.roles.update",
        resource_type="role",
        resource_id=role.id,
        before=before,
        after={"code": code, "name": role.name, "permission_ids": body.permission_ids},
    )
    context.session.commit()
    return _ok(
        request_id,
        "ADMIN_ROLE_UPDATED",
        {
            "role": _data(
                role, ("id", "code", "name", "description", "is_system", "updated_at")
            )
            | {"permission_ids": body.permission_ids}
        },
    )


@router.get("/permissions", response_model=ApiResponse[dict[str, Any]])
def permissions(
    context: Annotated[Context, Depends(allowed("admin:rbac:read"))],
    request_id: Annotated[str, Depends(get_request_id)],
    page: int = Query(1, ge=1),
    page_size: int = Query(30, ge=1, le=1000),
    keyword: str | None = Query(None, max_length=128),
) -> ApiResponse[dict[str, Any]]:
    page, page_size = _page(page, page_size)
    conditions: list[Any] = []
    if keyword:
        conditions.append(
            or_(
                AdminPermission.code.ilike(f"%{keyword.strip()}%"),
                AdminPermission.name.ilike(f"%{keyword.strip()}%"),
            )
        )
    total = (
        context.session.scalar(
            select(func.count()).select_from(AdminPermission).where(*conditions)
        )
        or 0
    )
    rows = context.session.scalars(
        select(AdminPermission)
        .where(*conditions)
        .order_by(AdminPermission.code)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return _ok(
        request_id,
        "ADMIN_PERMISSIONS",
        {
            "items": [
                _data(row, ("id", "code", "name", "description", "created_at"))
                for row in rows
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
        },
    )


@router.post(
    "/permissions",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiResponse[dict[str, Any]],
)
def create_permission(
    body: PermissionRequest,
    context: Annotated[Context, Depends(allowed("admin:rbac:manage"))],
    request_id: Annotated[str, Depends(get_request_id)],
) -> ApiResponse[dict[str, Any]]:
    # Permission codes are machine identifiers such as admin:users:read.
    if (
        not body.code
        or any(not (c.isalnum() or c in "._:-") for c in body.code)
        or len(body.code) > 128
    ):
        raise ApiError("VALIDATION_ERROR", "Invalid permission code", 422)
    if context.session.scalar(
        select(AdminPermission.id).where(AdminPermission.code == body.code)
    ):
        raise ApiError("ADMIN_CONFLICT", "Permission already exists", 409)
    permission = AdminPermission(
        id=new_id("perm"),
        code=body.code,
        name=body.name.strip(),
        description=body.description,
    )
    context.session.add(permission)
    _audit(
        context,
        action="admin.permissions.create",
        resource_type="permission",
        resource_id=permission.id,
        after={"code": body.code, "name": permission.name},
    )
    context.session.commit()
    return _ok(
        request_id,
        "ADMIN_PERMISSION_CREATED",
        {
            "permission": _data(
                permission, ("id", "code", "name", "description", "created_at")
            )
        },
    )


@router.patch(
    "/permissions/{permission_id}", response_model=ApiResponse[dict[str, Any]]
)
def update_permission(
    permission_id: str,
    body: PermissionRequest,
    context: Annotated[Context, Depends(allowed("admin:rbac:manage"))],
    request_id: Annotated[str, Depends(get_request_id)],
) -> ApiResponse[dict[str, Any]]:
    permission = context.session.get(AdminPermission, permission_id)
    if permission is None:
        raise ApiError("ADMIN_RESOURCE_NOT_FOUND", "Resource not found", 404)
    if not body.code or any(
        not (char.isalnum() or char in "._:-") for char in body.code
    ):
        raise ApiError("VALIDATION_ERROR", "Invalid permission code", 422)
    conflict = context.session.scalar(
        select(AdminPermission.id).where(
            and_(AdminPermission.code == body.code, AdminPermission.id != permission.id)
        )
    )
    if conflict:
        raise ApiError("ADMIN_CONFLICT", "Permission already exists", 409)
    before = _data(permission, ("code", "name", "description"))
    permission.code, permission.name, permission.description = (
        body.code,
        body.name.strip(),
        body.description,
    )
    _audit(
        context,
        action="admin.permissions.update",
        resource_type="permission",
        resource_id=permission.id,
        before=before,
        after=_data(permission, ("code", "name", "description")),
    )
    context.session.commit()
    return _ok(
        request_id,
        "ADMIN_PERMISSION_UPDATED",
        {
            "permission": _data(
                permission, ("id", "code", "name", "description", "created_at")
            )
        },
    )


@router.get("/menus", response_model=ApiResponse[dict[str, Any]])
def menus(
    context: Annotated[Context, Depends(allowed("admin:rbac:read"))],
    request_id: Annotated[str, Depends(get_request_id)],
    page: int = Query(1, ge=1),
    page_size: int = Query(30, ge=1, le=1000),
    keyword: str | None = Query(None, max_length=128),
) -> ApiResponse[dict[str, Any]]:
    page, page_size = _page(page, page_size)
    conditions: list[Any] = []
    if keyword:
        conditions.append(
            or_(
                AdminMenu.code.ilike(f"%{keyword.strip()}%"),
                AdminMenu.name.ilike(f"%{keyword.strip()}%"),
            )
        )
    total = (
        context.session.scalar(
            select(func.count()).select_from(AdminMenu).where(*conditions)
        )
        or 0
    )
    rows = context.session.scalars(
        select(AdminMenu)
        .where(*conditions)
        .order_by(AdminMenu.parent_id, AdminMenu.sort_order)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    fields = (
        "id",
        "parent_id",
        "name",
        "code",
        "path",
        "icon",
        "menu_type",
        "permission_code",
        "is_visible",
        "sort_order",
        "created_at",
        "updated_at",
    )
    return _ok(
        request_id,
        "ADMIN_MENUS",
        {
            "items": [_data(row, fields) for row in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
        },
    )


@router.post(
    "/menus",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiResponse[dict[str, Any]],
)
def create_menu(
    body: MenuRequest,
    context: Annotated[Context, Depends(allowed("admin:rbac:manage"))],
    request_id: Annotated[str, Depends(get_request_id)],
) -> ApiResponse[dict[str, Any]]:
    if body.menu_type not in {"directory", "menu", "button"}:
        raise ApiError("VALIDATION_ERROR", "Invalid menu type", 422)
    if context.session.scalar(select(AdminMenu.id).where(AdminMenu.code == body.code)):
        raise ApiError("ADMIN_CONFLICT", "Menu already exists", 409)
    if body.parent_id and context.session.get(AdminMenu, body.parent_id) is None:
        raise ApiError("VALIDATION_ERROR", "Unknown parent menu", 422)
    row = AdminMenu(id=new_id("menu"), **body.model_dump())
    context.session.add(row)
    _audit(
        context,
        action="admin.menus.create",
        resource_type="menu",
        resource_id=row.id,
        after={"code": row.code, "path": row.path},
    )
    context.session.commit()
    return _ok(
        request_id,
        "ADMIN_MENU_CREATED",
        {
            "menu": _data(
                row,
                (
                    "id",
                    "parent_id",
                    "name",
                    "code",
                    "path",
                    "icon",
                    "menu_type",
                    "permission_code",
                    "is_visible",
                    "sort_order",
                    "created_at",
                    "updated_at",
                ),
            )
        },
    )


@router.patch("/menus/{menu_id}", response_model=ApiResponse[dict[str, Any]])
def update_menu(
    menu_id: str,
    body: MenuRequest,
    context: Annotated[Context, Depends(allowed("admin:rbac:manage"))],
    request_id: Annotated[str, Depends(get_request_id)],
) -> ApiResponse[dict[str, Any]]:
    row = context.session.get(AdminMenu, menu_id)
    if row is None:
        raise ApiError("ADMIN_RESOURCE_NOT_FOUND", "Resource not found", 404)
    if (
        body.menu_type not in {"directory", "menu", "button"}
        or body.parent_id == row.id
    ):
        raise ApiError("VALIDATION_ERROR", "Invalid menu", 422)
    if body.parent_id and context.session.get(AdminMenu, body.parent_id) is None:
        raise ApiError("VALIDATION_ERROR", "Unknown parent menu", 422)
    conflict = context.session.scalar(
        select(AdminMenu.id).where(
            and_(AdminMenu.code == body.code, AdminMenu.id != row.id)
        )
    )
    if conflict:
        raise ApiError("ADMIN_CONFLICT", "Menu already exists", 409)
    before = _data(
        row,
        (
            "parent_id",
            "name",
            "code",
            "path",
            "icon",
            "menu_type",
            "permission_code",
            "is_visible",
            "sort_order",
        ),
    )
    for key, value in body.model_dump().items():
        setattr(row, key, value)
    _audit(
        context,
        action="admin.menus.update",
        resource_type="menu",
        resource_id=row.id,
        before=before,
        after=_data(
            row,
            (
                "parent_id",
                "name",
                "code",
                "path",
                "icon",
                "menu_type",
                "permission_code",
                "is_visible",
                "sort_order",
            ),
        ),
    )
    context.session.commit()
    return _ok(
        request_id,
        "ADMIN_MENU_UPDATED",
        {
            "menu": _data(
                row,
                (
                    "id",
                    "parent_id",
                    "name",
                    "code",
                    "path",
                    "icon",
                    "menu_type",
                    "permission_code",
                    "is_visible",
                    "sort_order",
                    "updated_at",
                ),
            )
        },
    )
