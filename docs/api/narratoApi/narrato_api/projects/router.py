from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal, cast

from fastapi import APIRouter, Depends, Query, Request, status
from pydantic import Field
from sqlalchemy.orm import Session

from narrato_api.api.dependencies import get_request_id, get_settings
from narrato_api.api.errors import ApiError
from narrato_api.api.responses import ApiResponse, StrictModel
from narrato_api.assets.router import get_upload_service
from narrato_api.assets.service import UploadService
from narrato_api.auth.router import bearer_token, get_auth_service
from narrato_api.auth.service import AuthService
from narrato_api.config import Settings
from narrato_api.exports.service import (
    JianyingManifestSnapshotNotFoundError,
    build_owned_completed_project_jianying_manifest,
)
from narrato_api.integrations.core_client import CoreClientError, HttpCoreClient
from narrato_api.workflows.orchestrator import (
    WorkflowDispatchError,
    WorkflowOrchestrator,
)
from narrato_api.projects.service import (
    BackgroundMusicSetting,
    ProjectNotFoundError,
    ProjectLifecycleConflict,
    ProjectResultLookupError,
    create_project,
    estimate_project_cost,
    lookup_completed_project_result,
    request_project_deletion,
    start_project,
    get_background_music_setting,
    get_narration_settings as get_saved_narration_settings,
    save_background_music_setting,
    ProjectStateConflict,
    advance_project_stage,
    get_project_stage_detail,
    list_owned_projects,
    save_narration_settings,
    save_settings_and_start_analysis,
    create_retry_draft,
)

router = APIRouter()


def get_jianying_core_client(
    settings: Annotated[Settings, Depends(get_settings)],
) -> HttpCoreClient:
    """创建仅用于剪映 Manifest 的 Core 客户端。"""

    return HttpCoreClient(
        base_url=str(settings.core_base_url), request_token=settings.core_request_token
    )


def get_analysis_core_client(
    settings: Annotated[Settings, Depends(get_settings)],
) -> HttpCoreClient:
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


class ProjectListItemData(StrictModel):
    id: str
    product: str
    status: str
    current_stage: str
    title: str
    video_count: int
    duration_seconds: int
    thumbnail_url: str | None = None
    credits: int
    created_at: str


class ProjectListData(StrictModel):
    items: list[ProjectListItemData]
    page: int
    page_size: int
    total: int


class ProjectCostData(StrictModel):
    credits: int
    total_seconds: int
    estimated_output_seconds: int
    credits_per_minute: int


class ProjectStartData(StrictModel):
    workflow_id: str


class BackgroundMusicData(StrictModel):
    asset_id: str
    filename: str
    cdn_url: str
    volume: int


class SubtitleRegionData(StrictModel):
    """以源视频画面为坐标系的归一化字幕遮罩位置。"""

    x: float = Field(default=0, ge=0, le=1)
    y: float = Field(ge=0, le=1)
    width: float = Field(default=1, gt=0, le=1)
    height: float = Field(gt=0, le=1)


class SourceSubtitleLayoutData(StrictModel):
    status: Literal["detected", "confirmed", "none"]
    region: SubtitleRegionData | None = None
    detected_confidence: float | None = Field(default=None, ge=0, le=1)


class NarrationSubtitlePositionData(StrictModel):
    y: float = Field(default=0.82, ge=0, le=1)
    font_scale: float = Field(default=0.9, ge=0.7, le=1.5)


class NarrationSettingsData(StrictModel):
    background_music: BackgroundMusicData | None = None
    narration_style: str | None = None
    video_ratio: str | None = None
    voice_id: str | None = None
    subtitle_style: str | None = None
    custom_style: str | None = None
    requirements: str | None = None
    target_duration_seconds: int | None = Field(default=None, ge=10, le=1800)
    original_sound_ratio: int = Field(default=30, ge=0, le=100)
    execution_mode: Literal["manual", "auto"] = "manual"
    source_subtitle_layouts: dict[str, SourceSubtitleLayoutData] = Field(default_factory=dict)
    narration_subtitle_position: NarrationSubtitlePositionData = Field(default_factory=NarrationSubtitlePositionData)


class NarrationSettingsPatchRequest(StrictModel):
    """传 null 可移除背景音乐；仅改音量时仍需带当前 asset id。"""

    background_music_asset_id: str | None = None
    background_music_volume: int | None = Field(default=None, ge=0, le=100)
    narration_style: str | None = None
    video_ratio: str | None = None
    voice_id: str | None = None
    subtitle_style: str | None = None
    custom_style: str | None = None
    requirements: str | None = None
    target_duration_seconds: int | None = Field(default=None, ge=10, le=1800)
    original_sound_ratio: int = Field(default=30, ge=0, le=100)
    execution_mode: Literal["manual", "auto"] = "manual"
    source_subtitle_layouts: dict[str, SourceSubtitleLayoutData] | None = None
    narration_subtitle_position: NarrationSubtitlePositionData | None = None


class NarrationSettingsStartRequest(StrictModel):
    narration_style: str
    video_ratio: str
    voice_id: str
    subtitle_style: str
    custom_style: str | None = None
    requirements: str | None = None
    target_duration_seconds: int | None = Field(default=None, ge=10, le=1800)
    original_sound_ratio: int = Field(default=30, ge=0, le=100)
    execution_mode: Literal["manual", "auto"] = "manual"
    source_subtitle_layouts: dict[str, SourceSubtitleLayoutData]
    narration_subtitle_position: NarrationSubtitlePositionData


class AnalysisTaskData(StrictModel):
    id: str
    name: str
    state: str
    updated_at: datetime | None = None
    error_code: str | None = None
    error_reason: str | None = None
    error_details: dict[str, object] | None = None


class ProjectVideoAssetData(StrictModel):
    id: str
    filename: str
    cdn_url: str
    duration_seconds: float | None = None
    subtitle_asset_id: str | None = None
    subtitle_filename: str | None = None


class ProjectRetryData(StrictModel):
    project_id: str
    status: str


class ProjectStageData(StrictModel):
    project_id: str
    project_title: str
    project_status: str
    current_stage: str
    execution_mode: Literal["manual", "auto"]
    workflow_state: str | None = None
    failure_code: str | None = None
    updated_at: datetime
    stages: list[str]
    analysis_tasks: list[AnalysisTaskData]
    video_assets: list[ProjectVideoAssetData]


class ProjectStageAdvanceRequest(StrictModel):
    target_stage: str


def _background_music_data(setting: BackgroundMusicSetting) -> BackgroundMusicData:
    return BackgroundMusicData(
        asset_id=setting.asset_id,
        filename=setting.filename,
        cdn_url=setting.cdn_url,
        volume=setting.volume,
    )


def _narration_data(
    settings: dict | None, setting: BackgroundMusicSetting | None
) -> NarrationSettingsData:
    settings = settings or {}
    return NarrationSettingsData(
        background_music=_background_music_data(setting) if setting else None,
        narration_style=settings.get("narration_style"),
        video_ratio=settings.get("video_ratio"),
        voice_id=settings.get("voice_id"),
        subtitle_style=settings.get("subtitle_style"),
        custom_style=settings.get("custom_style"),
        requirements=settings.get("requirements"),
        target_duration_seconds=settings.get("target_duration_seconds"),
        original_sound_ratio=settings.get("original_sound_ratio", 30),
        execution_mode=settings.get("execution_mode", "manual"),
        source_subtitle_layouts=settings.get("source_subtitle_layouts") or {},
        narration_subtitle_position=settings.get("narration_subtitle_position") or {"y": 0.82, "font_scale": 0.9},
    )


def _stage_data(detail) -> ProjectStageData:
    return ProjectStageData(
        project_id=detail.project_id,
        project_title=detail.project_title,
        project_status=detail.project_status,
        current_stage=detail.current_stage,
        execution_mode=detail.execution_mode,
        workflow_state=detail.workflow_state,
        failure_code=detail.failure_code,
        updated_at=detail.updated_at,
        stages=list(detail.stages),
        analysis_tasks=[AnalysisTaskData(**task) for task in detail.analysis_tasks],
        video_assets=[ProjectVideoAssetData(**asset) for asset in detail.video_assets],
    )


def _lifecycle_error(error: Exception) -> ApiError:
    if isinstance(error, ProjectNotFoundError):
        return ApiError("PROJECT_NOT_FOUND", "Project not found", 404)
    if isinstance(error, ProjectLifecycleConflict):
        return ApiError(error.code, str(error), 409)
    raise error


@router.get(
    "/projects/{project_id}/narration/settings",
    response_model=ApiResponse[NarrationSettingsData],
)
def get_narration_settings(
    project_id: str,
    request: Request,
    token: Annotated[str, Depends(bearer_token)],
    auth: Annotated[AuthService, Depends(get_auth_service)],
    request_id: Annotated[str, Depends(get_request_id)],
) -> ApiResponse[NarrationSettingsData]:
    user = auth.resolve_user(token)
    with Session(request.app.state.database_engine) as session:
        try:
            setting = get_background_music_setting(
                session, user_id=user.id, project_id=project_id
            )
            narration = get_saved_narration_settings(
                session, user_id=user.id, project_id=project_id
            )
        except ProjectNotFoundError as error:
            raise _lifecycle_error(error) from error
    return ApiResponse(
        code="NARRATION_SETTINGS_RETRIEVED",
        message="Narration settings retrieved",
        data=_narration_data(narration, setting),
        request_id=request_id,
    )


@router.patch(
    "/projects/{project_id}/narration/settings",
    response_model=ApiResponse[NarrationSettingsData],
)
def update_narration_settings(
    project_id: str,
    body: NarrationSettingsPatchRequest,
    request: Request,
    token: Annotated[str, Depends(bearer_token)],
    auth: Annotated[AuthService, Depends(get_auth_service)],
    request_id: Annotated[str, Depends(get_request_id)],
) -> ApiResponse[NarrationSettingsData]:
    user = auth.resolve_user(token)
    asset_id_was_provided = "background_music_asset_id" in body.model_fields_set
    volume_was_provided = "background_music_volume" in body.model_fields_set
    with Session(request.app.state.database_engine) as session:
        try:
            with session.begin():
                field_settings = {
                    key: getattr(body, key)
                    for key in (
                        "narration_style",
                        "video_ratio",
                        "voice_id",
                        "subtitle_style",
                        "custom_style",
                        "requirements",
                        "target_duration_seconds",
                        "original_sound_ratio",
                        "execution_mode",
                        "source_subtitle_layouts",
                        "narration_subtitle_position",
                    )
                    if key in body.model_fields_set
                }
                narration = (
                    save_narration_settings(
                        session,
                        user_id=user.id,
                        project_id=project_id,
                        settings=field_settings,
                    )
                    if field_settings
                    else get_saved_narration_settings(
                        session, user_id=user.id, project_id=project_id
                    )
                )
                # PATCH 的缺省字段不能与显式 null 混为一谈：只有显式 null 才移除。
                if not asset_id_was_provided:
                    current = get_background_music_setting(
                        session, user_id=user.id, project_id=project_id
                    )
                    if not volume_was_provided:
                        setting = current
                    elif current is None:
                        raise ApiError(
                            "BACKGROUND_MUSIC_ASSET_REQUIRED",
                            "An audio asset must be selected before setting volume",
                            422,
                        )
                    else:
                        setting = save_background_music_setting(
                            session,
                            user_id=user.id,
                            project_id=project_id,
                            asset_id=current.asset_id,
                            volume=body.background_music_volume,
                        )
                else:
                    setting = save_background_music_setting(
                        session,
                        user_id=user.id,
                        project_id=project_id,
                        asset_id=body.background_music_asset_id,
                        volume=body.background_music_volume,
                    )
        except (ProjectNotFoundError, ProjectLifecycleConflict) as error:
            raise _lifecycle_error(error) from error
    return ApiResponse(
        code="NARRATION_SETTINGS_UPDATED",
        message="Narration settings updated",
        data=_narration_data(narration, setting),
        request_id=request_id,
    )


@router.post(
    "/projects/{project_id}/narration/settings/start-analysis",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=ApiResponse[ProjectStartData],
)
def save_settings_and_start_owned_analysis(
    project_id: str,
    body: NarrationSettingsStartRequest,
    request: Request,
    token: Annotated[str, Depends(bearer_token)],
    auth: Annotated[AuthService, Depends(get_auth_service)],
    settings: Annotated[Settings, Depends(get_settings)],
    core_client: Annotated[HttpCoreClient, Depends(get_analysis_core_client)],
    request_id: Annotated[str, Depends(get_request_id)],
) -> ApiResponse[ProjectStartData]:
    """原子保存设置并进入 AI 分析，避免前端跳转造成未持久化任务。"""

    user = auth.resolve_user(token)
    with Session(request.app.state.database_engine) as session:
        try:
            with session.begin():
                workflow_id = save_settings_and_start_analysis(
                    session,
                    user_id=user.id,
                    project_id=project_id,
                    settings=body.model_dump(),
                )
        except (ProjectNotFoundError, ProjectLifecycleConflict) as error:
            raise _lifecycle_error(error) from error
    # 立即尝试发出首个 ASR；失败时保留初始 Outbox，beat 会用相同 attempt 幂等重放。
    try:
        WorkflowOrchestrator(
            lambda: Session(request.app.state.database_engine, expire_on_commit=False),
            video_translation_model_id=settings.video_translation_model_id,
        ).dispatch_ready(workflow_id=workflow_id, core_client=core_client)
    except WorkflowDispatchError:
        # 仍返回已持久化的 202；Outbox scheduler 会重放同一个 attempt。
        pass
    return ApiResponse(
        code="PROJECT_ANALYSIS_STARTED",
        message="Narration settings saved and AI analysis started",
        data=ProjectStartData(workflow_id=workflow_id),
        request_id=request_id,
    )


@router.get(
    "/projects/{project_id}/stage", response_model=ApiResponse[ProjectStageData]
)
def get_owned_project_stage(
    project_id: str,
    request: Request,
    token: Annotated[str, Depends(bearer_token)],
    auth: Annotated[AuthService, Depends(get_auth_service)],
    core_client: Annotated[HttpCoreClient, Depends(get_analysis_core_client)],
    request_id: Annotated[str, Depends(get_request_id)],
) -> ApiResponse[ProjectStageData]:
    user = auth.resolve_user(token)
    with Session(request.app.state.database_engine) as session:
        try:
            detail = get_project_stage_detail(
                session, user_id=user.id, project_id=project_id
            )
        except ProjectNotFoundError as error:
            raise _lifecycle_error(error) from error
    return ApiResponse(
        code="PROJECT_STAGE_RETRIEVED",
        message="Project stage retrieved",
        data=_stage_data(detail),
        request_id=request_id,
    )


@router.post(
    "/projects/{project_id}/stage/advance", response_model=ApiResponse[ProjectStageData]
)
def advance_owned_project_stage(
    project_id: str,
    body: ProjectStageAdvanceRequest,
    request: Request,
    token: Annotated[str, Depends(bearer_token)],
    auth: Annotated[AuthService, Depends(get_auth_service)],
    request_id: Annotated[str, Depends(get_request_id)],
) -> ApiResponse[ProjectStageData]:
    user = auth.resolve_user(token)
    with Session(request.app.state.database_engine) as session:
        try:
            with session.begin():
                detail = advance_project_stage(
                    session,
                    user_id=user.id,
                    project_id=project_id,
                    target_stage=body.target_stage,
                )
        except (ProjectNotFoundError, ProjectLifecycleConflict) as error:
            raise _lifecycle_error(error) from error
    return ApiResponse(
        code="PROJECT_STAGE_ADVANCED",
        message="Project stage advanced",
        data=_stage_data(detail),
        request_id=request_id,
    )


@router.get("/projects", response_model=ApiResponse[ProjectListData])
def list_projects(
    request: Request,
    token: Annotated[str, Depends(bearer_token)],
    auth: Annotated[AuthService, Depends(get_auth_service)],
    request_id: Annotated[str, Depends(get_request_id)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=50)] = 10,
    query: Annotated[str | None, Query(max_length=255)] = None,
    status_filter: Annotated[
        Literal["complete", "processing", "draft", "failed"] | None,
        Query(alias="status"),
    ] = None,
    product: Annotated[str | None, Query(max_length=64)] = None,
) -> ApiResponse[ProjectListData]:
    """分页返回当前登录用户的项目摘要，不暴露其他用户项目。"""

    user = auth.resolve_user(token)
    with Session(request.app.state.database_engine) as session:
        result = list_owned_projects(
            session,
            user_id=user.id,
            page=page,
            page_size=page_size,
            query=query,
            status=status_filter,
            product=product,
        )
    return ApiResponse(
        code="PROJECTS_LISTED",
        message="Projects listed",
        data=ProjectListData(
            items=[
                ProjectListItemData(
                    id=item.id,
                    product=item.product,
                    status=item.status,
                    current_stage=item.current_stage,
                    title=item.title,
                    video_count=item.video_count,
                    duration_seconds=item.duration_seconds,
                    thumbnail_url=item.thumbnail_url,
                    credits=item.credits,
                    created_at=item.created_at.isoformat(),
                )
                for item in result.items
            ],
            page=page,
            page_size=page_size,
            total=result.total,
        ),
        request_id=request_id,
    )


@router.post(
    "/projects",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiResponse[ProjectData],
)
def create_owned_project(
    body: ProjectCreateRequest,
    request: Request,
    token: Annotated[str, Depends(bearer_token)],
    auth: Annotated[AuthService, Depends(get_auth_service)],
    request_id: Annotated[str, Depends(get_request_id)],
) -> ApiResponse[ProjectData]:
    user = auth.resolve_user(token)
    with Session(request.app.state.database_engine) as session:
        with session.begin():
            try:
                project = create_project(session, user_id=user.id, product=body.product)
                data = ProjectData(id=project.id, status=project.status)
            except ProjectLifecycleConflict as error:
                raise _lifecycle_error(error) from error
    return ApiResponse(
        code="PROJECT_CREATED",
        message="Project created",
        data=data,
        request_id=request_id,
    )


@router.post(
    "/projects/{project_id}/retry-draft",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiResponse[ProjectRetryData],
)
def create_project_retry_draft(
    project_id: str,
    request: Request,
    token: Annotated[str, Depends(bearer_token)],
    auth: Annotated[AuthService, Depends(get_auth_service)],
    request_id: Annotated[str, Depends(get_request_id)],
) -> ApiResponse[ProjectRetryData]:
    """为任意可见项目创建草稿，并复用同一用户已校验的视频和字幕素材。"""

    user = auth.resolve_user(token)
    with Session(request.app.state.database_engine) as session:
        with session.begin():
            try:
                draft = create_retry_draft(
                    session, user_id=user.id, source_project_id=project_id
                )
            except (ProjectNotFoundError, ProjectLifecycleConflict) as error:
                raise _lifecycle_error(error) from error
    return ApiResponse(
        code="PROJECT_RETRY_DRAFT_CREATED",
        message="Project retry draft created",
        data=ProjectRetryData(project_id=draft.project_id, status=draft.status),
        request_id=request_id,
    )


@router.post(
    "/projects/{project_id}/cost-estimate", response_model=ApiResponse[ProjectCostData]
)
def estimate_owned_project(
    project_id: str,
    request: Request,
    token: Annotated[str, Depends(bearer_token)],
    auth: Annotated[AuthService, Depends(get_auth_service)],
    upload_service: Annotated[UploadService, Depends(get_upload_service)],
    request_id: Annotated[str, Depends(get_request_id)],
) -> ApiResponse[ProjectCostData]:
    user = auth.resolve_user(token)
    upload_service.reconcile_owned_project_assets(
        user_id=user.id, project_id=project_id
    )
    with Session(request.app.state.database_engine) as session:
        try:
            credits, total_seconds, estimated_output_seconds, credits_per_minute = (
                estimate_project_cost(session, user_id=user.id, project_id=project_id)
            )
        except (ProjectNotFoundError, ProjectLifecycleConflict) as error:
            raise _lifecycle_error(error) from error
    return ApiResponse(
        code="PROJECT_COST_ESTIMATED",
        message="Project cost estimated",
        data=ProjectCostData(
            credits=credits,
            total_seconds=total_seconds,
            estimated_output_seconds=estimated_output_seconds,
            credits_per_minute=credits_per_minute,
        ),
        request_id=request_id,
    )


@router.post(
    "/projects/{project_id}/start",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=ApiResponse[ProjectStartData],
)
def start_owned_project(
    project_id: str,
    request: Request,
    token: Annotated[str, Depends(bearer_token)],
    auth: Annotated[AuthService, Depends(get_auth_service)],
    request_id: Annotated[str, Depends(get_request_id)],
) -> ApiResponse[ProjectStartData]:
    user = auth.resolve_user(token)
    with Session(request.app.state.database_engine) as session:
        try:
            with session.begin():
                workflow_id = start_project(
                    session, user_id=user.id, project_id=project_id
                )
        except (ProjectNotFoundError, ProjectLifecycleConflict) as error:
            raise _lifecycle_error(error) from error
    return ApiResponse(
        code="PROJECT_STARTED",
        message="Project started",
        data=ProjectStartData(workflow_id=workflow_id),
        request_id=request_id,
    )


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
    """按当前状态/阶段为当前用户项目登记幂等删除审计请求。"""

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
                "PROJECT_NOT_TERMINAL",
                "Project cannot be deleted in its current state",
                409,
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
                JianyingManifestFileData.model_validate(file)
                for file in cast(list[object], manifest.to_dict()["files"])
            ],
        ),
        request_id=request_id,
    )
