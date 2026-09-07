from __future__ import annotations

from collections.abc import Iterable
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
import secrets
import time
from typing import TypeVar

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from narrato_api.artifacts.models import RegisteredArtifact
from narrato_api.artifacts.service import list_registered_artifacts
from narrato_api.assets.models import Asset
from narrato_api.editor.models import EditorDraft, EditorRevision
from narrato_api.editor.render_snapshot import (
    RenderSnapshotError,
    editor_draft_from_script,
    render_snapshot_from_draft,
)
from narrato_api.billing.models import CreditLedger, ProductPrice
from narrato_api.billing.pricing import (
    estimate_short_drama_cost,
    estimate_short_drama_output_seconds,
)
from narrato_api.billing.service import InsufficientCreditsError, _apply_credit
from narrato_api.projects.models import (
    DeletionJob,
    Project,
    ProjectBackgroundMusic,
    ProjectNarrationSettings,
    ProjectStageHistory,
)
from narrato_api.workflows.models import (
    Workflow,
    WorkflowNode,
    WorkflowNodeAttempt,
    WorkflowOutbox,
    WorkflowTemplateSnapshot,
)
from narrato_api.workflows.service import _new_id


Artifact = TypeVar("Artifact")
_PROJECT_SETTINGS_LOCKED_STATES = frozenset(
    {"completed", "failed", "deleting", "deleted"}
)
PROJECT_STAGES = ("created", "settings", "analysis", "edit", "generate", "export")
ANALYSIS_NODES = (
    ("subtitle_recognition", "字幕识别"),
    ("plot_structure", "剧情结构理解"),
    ("conflict_highlights", "冲突与爽点定位"),
    ("highlight_scoring", "高光片段评分"),
)
ANALYSIS_DEPENDENCIES = {
    "subtitle_recognition": (),
    "plot_structure": ("subtitle_recognition",),
    "conflict_highlights": ("plot_structure",),
    "highlight_scoring": ("conflict_highlights",),
}
SCRIPT_GENERATION_NODE = "script_generation"
EDIT_GATE_NODE = "waiting_for_edit"
VIDEO_RENDER_NODE = "video_render"
PUBLISH_ARTIFACTS_NODE = "publish_artifacts"
_REQUIRED_NARRATION_SETTINGS = (
    "narration_style",
    "video_ratio",
    "voice_id",
    "subtitle_style",
)
_REQUIRED_RENDER_ARTIFACT_KINDS = frozenset({"video", "subtitle", "voice", "timeline"})


class ProjectStateConflict(ValueError):
    """项目状态不满足当前操作前置条件时抛出。"""

    code = "PROJECT_NOT_TERMINAL"


class ProjectResultLookupError(LookupError):
    """项目结果不存在、非归属或尚不可读取时抛出。"""

    code = "PROJECT_RESULT_NOT_FOUND"


class ProjectNotFoundError(LookupError):
    """项目不存在或不属于当前用户时抛出，避免泄露归属。"""

    code = "PROJECT_NOT_FOUND"


class ProjectLifecycleConflict(ValueError):
    """创建、报价或启动项目的业务前置条件不成立。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class CompletedProjectResult:
    """已完成项目的最小结果记录。"""

    project_id: str
    artifacts: tuple[RegisteredArtifact, ...]


@dataclass(frozen=True)
class ProjectDeletionRequest:
    """已持久化的最小删除请求响应。"""

    job_id: str
    project_id: str
    status: str


@dataclass(frozen=True)
class BackgroundMusicSetting:
    """供 API 返回的已校验背景音乐设置。"""

    asset_id: str
    filename: str
    cdn_url: str
    volume: int


@dataclass(frozen=True)
class ProjectStageDetail:
    project_id: str
    project_title: str
    project_status: str
    current_stage: str
    execution_mode: str
    workflow_state: str | None
    failure_code: str | None
    updated_at: datetime
    stages: tuple[str, ...]
    analysis_tasks: tuple[dict[str, object], ...]
    video_assets: tuple[dict[str, object], ...]


@dataclass(frozen=True)
class ProjectRetryDraft:
    """从失败项目复用已校验源素材生成的可编辑草稿。"""

    project_id: str
    status: str


@dataclass(frozen=True)
class ProjectListItem:
    """项目列表页所需的、仅属于当前用户的项目摘要。"""

    id: str
    product: str
    status: str
    current_stage: str
    title: str
    video_count: int
    duration_seconds: int
    thumbnail_url: str | None
    credits: int
    created_at: datetime


@dataclass(frozen=True)
class ProjectListPage:
    items: tuple[ProjectListItem, ...]
    total: int


_TERMINAL_DELETABLE_PROJECT_STATES = frozenset({"completed", "failed"})
_PRE_ANALYSIS_DELETABLE_PROJECT_STAGES = frozenset({"created", "settings"})
_DELETION_STATES = frozenset({"deleting", "deleted"})
_ARTIFACT_VISIBLE_PROJECT_STATES = frozenset({"completed"})
_EXPORTABLE_PROJECT_STATES = frozenset({"completed"})


def _new_project_id() -> str:
    return f"prj_{time.time_ns():016x}{secrets.token_hex(8)}"


def _new_stage_history_id() -> str:
    return f"pst_{time.time_ns():016x}{secrets.token_hex(8)}"


def _record_stage(
    session: Session,
    *,
    project: Project,
    target_stage: str,
    settings_snapshot: dict | None,
) -> None:
    """只允许按固定顺序前进一次，并为每一阶段留下不可变审计记录。"""

    if target_stage not in PROJECT_STAGES:
        raise ProjectLifecycleConflict(
            "PROJECT_STAGE_INVALID", "Project stage is invalid"
        )
    current_index = PROJECT_STAGES.index(project.current_stage)
    target_index = PROJECT_STAGES.index(target_stage)
    if target_index <= current_index:
        raise ProjectLifecycleConflict(
            "PROJECT_STAGE_REWIND_FORBIDDEN",
            "Project stages cannot be revisited or rewound",
        )
    if target_index != current_index + 1:
        raise ProjectLifecycleConflict(
            "PROJECT_STAGE_SKIP_FORBIDDEN",
            "Project stages must advance one step at a time",
        )
    existing = session.scalar(
        select(ProjectStageHistory).where(
            ProjectStageHistory.project_id == project.id,
            ProjectStageHistory.to_stage == target_stage,
        )
    )
    if existing is not None:
        # 修复历史记录已落库、但项目阶段未更新的旧数据，避免重试触发数据库唯一键异常。
        project.current_stage = target_stage
        return
    session.add(
        ProjectStageHistory(
            id=_new_stage_history_id(),
            project_id=project.id,
            from_stage=project.current_stage,
            to_stage=target_stage,
            settings_snapshot=settings_snapshot,
        )
    )
    project.current_stage = target_stage


def _settings_snapshot(session: Session, project_id: str) -> dict | None:
    record = session.get(ProjectNarrationSettings, project_id)
    return dict(record.settings) if record is not None else None


def _validate_complete_narration_settings(settings: dict | None) -> dict:
    if not settings or any(
        not isinstance(settings.get(key), str) or not settings[key].strip()
        for key in _REQUIRED_NARRATION_SETTINGS
    ):
        raise ProjectLifecycleConflict(
            "PROJECT_SETTINGS_INCOMPLETE",
            "Narration settings must be saved before AI analysis",
        )
    if (
        settings["narration_style"] == "自定义类型"
        and not str(settings.get("custom_style", "")).strip()
    ):
        raise ProjectLifecycleConflict(
            "PROJECT_SETTINGS_INCOMPLETE", "A custom narration style is required"
        )
    if settings.get("execution_mode", "manual") not in {"manual", "auto"}:
        raise ProjectLifecycleConflict(
            "PROJECT_SETTINGS_INCOMPLETE", "Execution mode is invalid"
        )
    original_sound_ratio = settings.get("original_sound_ratio", 30)
    if type(original_sound_ratio) is not int or not 0 <= original_sound_ratio <= 100:
        raise ProjectLifecycleConflict(
            "PROJECT_SETTINGS_INCOMPLETE", "Original sound ratio is invalid"
        )
    settings["original_sound_ratio"] = original_sound_ratio
    return settings


def _validate_source_subtitle_layouts(
    session: Session, *, project_id: str, settings: dict
) -> None:
    """分析开始前将所有输入视频的字幕处理决策冻结进设置快照。"""

    layouts = settings.get("source_subtitle_layouts")
    if not isinstance(layouts, dict):
        raise ProjectLifecycleConflict(
            "SOURCE_SUBTITLE_LAYOUTS_REQUIRED",
            "Confirm the source subtitle region or choose no subtitles for every video",
        )
    videos = list(
        session.scalars(
            select(Asset).where(
                Asset.project_id == project_id,
                Asset.asset_type == "video",
                Asset.status == "ready",
            )
        )
    )
    missing = [asset.id for asset in videos if asset.id not in layouts]
    if missing:
        raise ProjectLifecycleConflict(
            "SOURCE_SUBTITLE_LAYOUTS_REQUIRED",
            "Confirm the source subtitle region or choose no subtitles for every video",
        )
    for asset in videos:
        layout = layouts.get(asset.id)
        if not isinstance(layout, dict) or layout.get("status") not in {
            "confirmed",
            "none",
        }:
            raise ProjectLifecycleConflict(
                "SOURCE_SUBTITLE_LAYOUTS_REQUIRED",
                "Each video needs a confirmed subtitle region or a no-subtitle decision",
            )
        region = layout.get("region")
        if layout["status"] == "confirmed":
            if not isinstance(region, dict):
                raise ProjectLifecycleConflict(
                    "SOURCE_SUBTITLE_LAYOUT_INVALID",
                    "A confirmed subtitle region is required",
                )
            x, y, width, height = (
                region.get(key) for key in ("x", "y", "width", "height")
            )
            if not all(
                isinstance(value, (int, float)) and not isinstance(value, bool)
                for value in (x, y, width, height)
            ):
                raise ProjectLifecycleConflict(
                    "SOURCE_SUBTITLE_LAYOUT_INVALID",
                    "Subtitle region coordinates are invalid",
                )
            if not (
                0 <= x <= 1
                and 0 <= y <= 1
                and 0 < width <= 1
                and 0 < height <= 1
                and x + width <= 1
                and y + height <= 1
            ):
                raise ProjectLifecycleConflict(
                    "SOURCE_SUBTITLE_LAYOUT_INVALID",
                    "Subtitle region must stay inside the source video",
                )
        elif region is not None:
            raise ProjectLifecycleConflict(
                "SOURCE_SUBTITLE_LAYOUT_INVALID",
                "No-subtitle videos cannot have a subtitle region",
            )
    target_duration = settings.get("target_duration_seconds")
    if target_duration is not None and (
        not isinstance(target_duration, int)
        or isinstance(target_duration, bool)
        or not 10 <= target_duration <= 1800
    ):
        raise ProjectLifecycleConflict(
            "TARGET_DURATION_INVALID",
            "Target duration must be an integer between 10 and 1800 seconds",
        )
    position = settings.get("narration_subtitle_position")
    if (
        not isinstance(position, dict)
        or not isinstance(position.get("y"), (int, float))
        or isinstance(position.get("y"), bool)
        or not 0 <= position["y"] <= 1
        or not isinstance(position.get("font_scale", 0.9), (int, float))
        or isinstance(position.get("font_scale", 0.9), bool)
        or not 0.7 <= position.get("font_scale", 0.9) <= 1.5
    ):
        raise ProjectLifecycleConflict(
            "NARRATION_SUBTITLE_POSITION_REQUIRED",
            "Confirm the narration subtitle position before starting AI analysis",
        )


def create_project(session: Session, *, user_id: str, product: str) -> Project:
    """创建短剧解说草稿；对 Web 的 kebab-case 产品名做唯一映射。"""

    if product not in {"short-drama-narration", "video-translation"}:
        raise ProjectLifecycleConflict(
            "PROJECT_PRODUCT_UNSUPPORTED", "Project product is unsupported"
        )
    project = Project(
        id=_new_project_id(),
        user_id=user_id,
        product="short_drama_narration" if product == "short-drama-narration" else "video_translation",
        status="draft",
    )
    session.add(project)
    session.flush()
    session.add(
        ProjectStageHistory(
            id=_new_stage_history_id(),
            project_id=project.id,
            from_stage=None,
            to_stage="created",
            settings_snapshot=None,
        )
    )
    return project


def create_retry_draft(
    session: Session, *, user_id: str, source_project_id: str
) -> ProjectRetryDraft:
    """复用 ready 素材，并将每个源视频的字幕区域映射到新草稿 asset。"""

    source = _owned_project(
        session, user_id=user_id, project_id=source_project_id, lock=True
    )
    if source.status in _DELETION_STATES:
        raise ProjectLifecycleConflict(
            "PROJECT_RETRY_FORBIDDEN",
            "Projects being deleted cannot be regenerated",
        )

    source_assets = list(
        session.scalars(
            select(Asset)
            .where(
                Asset.project_id == source.id,
                Asset.user_id == user_id,
                Asset.asset_type.in_(("video", "subtitle")),
                Asset.status == "ready",
            )
            .order_by(Asset.asset_type, Asset.sort_order, Asset.created_at, Asset.id)
        )
    )
    # 没有可复用视频时创建空草稿，避免把孤立字幕带入用户后续上传的新素材。
    if not any(asset.asset_type == "video" for asset in source_assets):
        source_assets = []
    retry_product = {
        "short_drama_narration": "short-drama-narration",
        "video_translation": "video-translation",
    }.get(source.product)
    if retry_product is None:
        raise ProjectLifecycleConflict(
            "PROJECT_PRODUCT_UNSUPPORTED", "Project product is unsupported"
        )
    project = create_project(session, user_id=user_id, product=retry_product)
    source_video_id_to_draft_id: dict[str, str] = {}
    for asset in source_assets:
        draft_asset_id = f"ast_{time.time_ns():016x}{secrets.token_hex(8)}"
        session.add(
            Asset(
                id=draft_asset_id,
                user_id=user_id,
                project_id=project.id,
                asset_type=asset.asset_type,
                status="ready",
                filename=asset.filename,
                bucket=asset.bucket,
                object_key=asset.object_key,
                cdn_url=asset.cdn_url,
                size_bytes=asset.size_bytes,
                sort_order=asset.sort_order,
                duration_seconds=asset.duration_seconds,
            )
        )
        if asset.asset_type == "video":
            source_video_id_to_draft_id[asset.id] = draft_asset_id

    if source.product == "short_drama_narration":
        source_settings = session.get(ProjectNarrationSettings, source.id)
        source_layouts = (
            source_settings.settings.get("source_subtitle_layouts")
            if source_settings is not None and isinstance(source_settings.settings, dict)
            else None
        )
        if isinstance(source_layouts, dict):
            draft_layouts = {
                draft_asset_id: deepcopy(source_layouts[source_asset_id])
                for source_asset_id, draft_asset_id in source_video_id_to_draft_id.items()
                if isinstance(source_layouts.get(source_asset_id), dict)
            }
            if draft_layouts:
                session.add(
                    ProjectNarrationSettings(
                        project_id=project.id,
                        settings={"source_subtitle_layouts": draft_layouts},
                    )
                )
    elif source.product == "video_translation":
        # 复用语言、音轨和字幕布局配置；背景音乐 asset 属于源项目，不能把
        # 旧 asset ID 写进新草稿。
        from narrato_api.products.video_translation import VideoTranslationSettings

        source_settings = session.get(VideoTranslationSettings, source.id)
        if source_settings is not None and isinstance(source_settings.settings, dict):
            draft_settings = deepcopy(source_settings.settings)
            draft_settings["background_music_asset_id"] = None
            session.add(
                VideoTranslationSettings(
                    project_id=project.id,
                    settings=draft_settings,
                )
            )
    session.flush()
    return ProjectRetryDraft(project_id=project.id, status=project.status)


_PROJECT_LIST_STATUS_FILTERS = {
    "complete": ("completed",),
    "processing": (
        "uploading",
        "validating",
        "ready",
        "queued",
        "analyzing",
        "waiting_for_edit",
        "render_queued",
        "rendering",
    ),
    "draft": ("draft",),
    "failed": ("failed",),
}


def list_owned_projects(
    session: Session,
    *,
    user_id: str,
    page: int,
    page_size: int,
    query: str | None = None,
    status: str | None = None,
    product: str | None = None,
) -> ProjectListPage:
    """返回当前用户可见项目，筛选和分页均在数据库层执行。"""

    filters = [
        Project.user_id == user_id,
        Project.status.not_in(tuple(_DELETION_STATES)),
    ]
    if status:
        filters.append(Project.status.in_(_PROJECT_LIST_STATUS_FILTERS[status]))
    if product:
        filters.append(Project.product == product)
    if query:
        needle = f"%{query.strip()}%"
        if needle != "%%":
            filters.append(
                or_(
                    Project.id.ilike(needle),
                    Project.id.in_(
                        select(Asset.project_id).where(Asset.filename.ilike(needle))
                    ),
                )
            )

    total = (
        session.scalar(select(func.count()).select_from(Project).where(*filters)) or 0
    )
    projects = list(
        session.scalars(
            select(Project)
            .where(*filters)
            .order_by(Project.created_at.desc(), Project.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    if not projects:
        return ProjectListPage(items=(), total=total)

    project_ids = [project.id for project in projects]
    assets_by_project: dict[str, list[Asset]] = {
        project_id: [] for project_id in project_ids
    }
    for asset in session.scalars(
        select(Asset)
        .where(Asset.project_id.in_(project_ids))
        .order_by(
            Asset.project_id,
            Asset.asset_type,
            Asset.sort_order,
            Asset.created_at,
            Asset.id,
        )
    ):
        assets_by_project[asset.project_id].append(asset)
    charge_rows = (
        session.execute(
            select(
                CreditLedger.reference_id,
                func.coalesce(func.sum(CreditLedger.amount), 0),
            )
            .where(
                CreditLedger.user_id == user_id,
                CreditLedger.reference_id.in_(project_ids),
                CreditLedger.entry_type.in_(("charge", "refund")),
            )
            .group_by(CreditLedger.reference_id)
        )
        .tuples()
        .all()
    )
    charges: dict[str, int] = {
        reference_id: amount
        for reference_id, amount in charge_rows
        if reference_id is not None
    }

    items = []
    for project in projects:
        videos = [
            asset
            for asset in assets_by_project[project.id]
            if asset.asset_type == "video"
        ]
        primary_video = videos[0] if videos else None
        total_duration = round(sum(asset.duration_seconds or 0 for asset in videos))
        title = primary_video.filename if primary_video else project.id
        items.append(
            ProjectListItem(
                id=project.id,
                product=project.product,
                status=project.status,
                current_stage=project.current_stage,
                title=title,
                video_count=len(videos),
                duration_seconds=total_duration,
                thumbnail_url=primary_video.cdn_url if primary_video else None,
                credits=max(0, -int(charges.get(project.id, 0))),
                created_at=project.created_at,
            )
        )
    return ProjectListPage(items=tuple(items), total=total)


def _owned_project(
    session: Session, *, user_id: str, project_id: str, lock: bool = False
) -> Project:
    statement = select(Project).where(
        Project.id == project_id, Project.user_id == user_id
    )
    if lock:
        statement = statement.with_for_update()
    project = session.scalar(statement)
    if project is None:
        raise ProjectNotFoundError("project was not found")
    return project


def _ready_quote(session: Session, *, project: Project) -> tuple[int, int, int, int]:
    assets = list(session.scalars(select(Asset).where(Asset.project_id == project.id)))
    videos = [asset for asset in assets if asset.asset_type == "video"]
    if not videos or any(asset.status != "ready" for asset in assets):
        raise ProjectLifecycleConflict(
            "PROJECT_ASSETS_NOT_READY", "Project assets are not ready"
        )
    if any(asset.duration_seconds is None for asset in videos):
        raise ProjectLifecycleConflict(
            "PROJECT_DURATION_UNAVAILABLE", "Project media duration is unavailable"
        )
    if project.product == "short_drama_narration" and any(
        not (0 < float(asset.duration_seconds or 0) <= 600) for asset in videos
    ):
        # 方舟公网 video_url 多模态输入按单素材限制十分钟。必须在报价和
        # start_project 扣费之前拒绝，不能依赖下游 Core 再失败退款。
        raise ProjectLifecycleConflict(
            "PROJECT_VIDEO_DURATION_UNSUPPORTED",
            "Each short drama video must be longer than 0 and no longer than 600 seconds",
        )
    price = session.scalar(
        select(ProductPrice)
        .where(ProductPrice.product == project.product)
        .order_by(ProductPrice.version.desc())
    )
    if price is None:
        raise ProjectLifecycleConflict(
            "PROJECT_PRICE_UNAVAILABLE", "Project price is unavailable"
        )
    total_seconds = int(sum(asset.duration_seconds or 0 for asset in videos))
    return (
        estimate_short_drama_cost(
            total_seconds, credits_per_minute=price.credits_per_minute
        ),
        total_seconds,
        estimate_short_drama_output_seconds(total_seconds),
        price.credits_per_minute,
    )


def estimate_project_cost(
    session: Session, *, user_id: str, project_id: str
) -> tuple[int, int, int, int]:
    """返回由已验证媒体真实时长和当前产品价目计算的报价。"""

    return _ready_quote(
        session, project=_owned_project(session, user_id=user_id, project_id=project_id)
    )


def get_background_music_setting(
    session: Session, *, user_id: str, project_id: str
) -> BackgroundMusicSetting | None:
    """读取当前用户项目的背景音乐；无设置是正常的可选状态。"""

    _owned_project(session, user_id=user_id, project_id=project_id)
    row = session.execute(
        select(ProjectBackgroundMusic, Asset)
        .join(Asset, Asset.id == ProjectBackgroundMusic.asset_id)
        .where(ProjectBackgroundMusic.project_id == project_id)
    ).one_or_none()
    if row is None:
        return None
    setting, asset = row
    return BackgroundMusicSetting(
        asset_id=asset.id,
        filename=asset.filename,
        cdn_url=asset.cdn_url,
        volume=setting.volume,
    )


def get_narration_settings(
    session: Session, *, user_id: str, project_id: str
) -> dict | None:
    _owned_project(session, user_id=user_id, project_id=project_id)
    return _settings_snapshot(session, project_id)


def save_background_music_setting(
    session: Session,
    *,
    user_id: str,
    project_id: str,
    asset_id: str | None,
    volume: int | None,
) -> BackgroundMusicSetting | None:
    """任务终态前原子保存或清空背景音乐，并阻止无效资源引用。"""

    project = _owned_project(session, user_id=user_id, project_id=project_id, lock=True)
    if (
        project.current_stage not in {"created", "settings"}
        or project.status in _PROJECT_SETTINGS_LOCKED_STATES
    ):
        raise ProjectLifecycleConflict(
            "PROJECT_SETTINGS_LOCKED",
            "Project settings cannot be changed after task completion",
        )
    existing = session.get(ProjectBackgroundMusic, project_id)
    if asset_id is None:
        if existing is not None:
            session.delete(existing)
            session.flush()
        return None
    asset = session.scalar(
        select(Asset).where(
            Asset.id == asset_id,
            Asset.user_id == user_id,
            Asset.project_id == project_id,
            Asset.asset_type == "audio",
            Asset.status == "ready",
        )
    )
    if asset is None:
        raise ProjectLifecycleConflict(
            "BACKGROUND_MUSIC_ASSET_INVALID",
            "Background music must be a ready audio asset owned by this project",
        )
    selected_volume = (
        volume if volume is not None else (existing.volume if existing else 50)
    )
    if existing is None:
        session.add(
            ProjectBackgroundMusic(
                project_id=project.id, asset_id=asset.id, volume=selected_volume
            )
        )
    else:
        existing.asset_id = asset.id
        existing.volume = selected_volume
    session.flush()
    return BackgroundMusicSetting(
        asset_id=asset.id,
        filename=asset.filename,
        cdn_url=asset.cdn_url,
        volume=selected_volume,
    )


def save_narration_settings(
    session: Session, *, user_id: str, project_id: str, settings: dict
) -> dict:
    """在参数阶段保存完整/部分表单，任何后续阶段都不能再次编辑。"""

    project = _owned_project(session, user_id=user_id, project_id=project_id, lock=True)
    if (
        project.current_stage not in {"created", "settings"}
        or project.status in _PROJECT_SETTINGS_LOCKED_STATES
    ):
        raise ProjectLifecycleConflict(
            "PROJECT_SETTINGS_LOCKED",
            "Project settings are locked after AI analysis starts",
        )
    existing = session.get(ProjectNarrationSettings, project.id)
    merged = dict(existing.settings) if existing is not None else {}
    # 每个视频独立产生探测结果；PATCH 单个视频时不能覆盖其他视频的确认结果。
    incoming_layouts = settings.get("source_subtitle_layouts")
    if isinstance(incoming_layouts, dict):
        existing_layouts = merged.get("source_subtitle_layouts")
        merged["source_subtitle_layouts"] = {
            **(existing_layouts if isinstance(existing_layouts, dict) else {}),
            **incoming_layouts,
        }
        settings = {
            key: value
            for key, value in settings.items()
            if key != "source_subtitle_layouts"
        }
    merged.update(settings)
    if existing is None:
        session.add(ProjectNarrationSettings(project_id=project.id, settings=merged))
    else:
        existing.settings = merged
    if project.current_stage == "created":
        _record_stage(
            session, project=project, target_stage="settings", settings_snapshot=None
        )
    session.flush()
    return merged


def get_project_stage_detail(
    session: Session, *, user_id: str, project_id: str
) -> ProjectStageDetail:
    project = _owned_project(session, user_id=user_id, project_id=project_id)
    workflow = session.scalar(select(Workflow).where(Workflow.project_id == project.id))
    task_by_name: dict[str, WorkflowNode] = {}
    latest_attempt_by_node: dict[str, WorkflowNodeAttempt] = {}
    failure_code: str | None = None
    if workflow is not None:
        nodes = list(
            session.scalars(
                select(WorkflowNode).where(WorkflowNode.workflow_id == workflow.id)
            )
        )
        task_by_name = {node.name: node for node in nodes}
        attempts = (
            list(
                session.scalars(
                    select(WorkflowNodeAttempt)
                    .where(
                        WorkflowNodeAttempt.workflow_node_id.in_(
                            [node.id for node in nodes]
                        )
                    )
                    .order_by(
                        WorkflowNodeAttempt.workflow_node_id,
                        WorkflowNodeAttempt.attempt_number.desc(),
                    )
                )
            )
            if nodes
            else []
        )
        for attempt in attempts:
            latest_attempt_by_node.setdefault(attempt.workflow_node_id, attempt)
        if project.status in {"failed", "cancelled"}:
            failed_attempt = next(
                (
                    attempt
                    for attempt in sorted(
                        attempts,
                        key=lambda item: item.completed_at or item.created_at,
                        reverse=True,
                    )
                    if attempt.state in {"failed", "cancelled"}
                ),
                None,
            )
            raw_error = (
                failed_attempt.result.get("error")
                if failed_attempt is not None
                and isinstance(failed_attempt.result, dict)
                else None
            )
            if isinstance(raw_error, dict) and isinstance(raw_error.get("code"), str):
                failure_code = raw_error["code"]
    videos = list(
        session.scalars(
            select(Asset)
            .where(
                Asset.project_id == project.id,
                Asset.asset_type == "video",
                Asset.status == "ready",
            )
            .order_by(Asset.sort_order, Asset.created_at, Asset.id)
        )
    )
    subtitles = list(
        session.scalars(
            select(Asset)
            .where(
                Asset.project_id == project.id,
                Asset.asset_type == "subtitle",
                Asset.status == "ready",
            )
            .order_by(Asset.sort_order, Asset.created_at, Asset.id)
        )
    )
    subtitles_by_stem: dict[str, list[Asset]] = {}
    for subtitle in subtitles:
        subtitles_by_stem.setdefault(
            subtitle.filename.rsplit(".", 1)[0].casefold(), []
        ).append(subtitle)
    matched_subtitles: dict[str, Asset] = {}
    for video in videos:
        candidates = subtitles_by_stem.get(
            video.filename.rsplit(".", 1)[0].casefold(), []
        )
        if candidates:
            matched_subtitles[video.id] = candidates.pop(0)
        elif len(videos) == 1 and len(subtitles) == 1:
            matched_subtitles[video.id] = subtitles[0]
    narration = session.get(ProjectNarrationSettings, project.id)
    settings = dict(narration.settings) if narration is not None else {}

    def task_detail(name: str, label: str) -> dict[str, object]:
        node = task_by_name.get(name)
        attempt = latest_attempt_by_node.get(node.id) if node is not None else None
        raw_error = (
            attempt.result.get("error")
            if attempt is not None and isinstance(attempt.result, dict)
            else None
        )
        return {
            "id": name,
            "name": label,
            "state": node.state if node is not None else "not_started",
            "updated_at": (
                (attempt.completed_at or attempt.created_at)
                if attempt is not None
                else node.updated_at
                if node is not None
                else None
            ),
            "error_code": (
                raw_error.get("code")
                if isinstance(raw_error, dict)
                and isinstance(raw_error.get("code"), str)
                else None
            ),
            "error_reason": (
                raw_error.get("reason")
                if isinstance(raw_error, dict)
                and isinstance(raw_error.get("reason"), str)
                else None
            ),
            "error_details": (
                raw_error.get("details")
                if isinstance(raw_error, dict)
                and isinstance(raw_error.get("details"), dict)
                else None
            ),
        }

    return ProjectStageDetail(
        project_id=project.id,
        project_title=videos[0].filename if videos else project.id,
        project_status=project.status,
        current_stage=project.current_stage,
        execution_mode="auto" if settings.get("execution_mode") == "auto" else "manual",
        workflow_state=workflow.state if workflow is not None else None,
        failure_code=failure_code,
        updated_at=project.updated_at,
        stages=PROJECT_STAGES,
        # 脚本生成是 Revision 的直接上游，也必须出现在公开阶段投影中；
        # 否则四项分析完成时前端会错误显示 100%，掩盖仍在执行的脚本任务。
        analysis_tasks=tuple(
            task_detail(name, label)
            for name, label in (
                *ANALYSIS_NODES,
                (SCRIPT_GENERATION_NODE, "生成解说文案"),
            )
        ),
        video_assets=tuple(
            {
                "id": video.id,
                "filename": video.filename,
                "cdn_url": video.cdn_url,
                "duration_seconds": video.duration_seconds,
                "subtitle_asset_id": matched_subtitles[video.id].id
                if video.id in matched_subtitles
                else None,
                "subtitle_filename": matched_subtitles[video.id].filename
                if video.id in matched_subtitles
                else None,
            }
            for video in videos
        ),
    )


def advance_project_stage(
    session: Session, *, user_id: str, project_id: str, target_stage: str
) -> ProjectStageDetail:
    """只开放已满足真实执行条件的下一阶段，禁止客户端绕过阶段锁。"""

    project = _owned_project(session, user_id=user_id, project_id=project_id, lock=True)
    if target_stage == "edit":
        if project.current_stage != "analysis":
            raise ProjectLifecycleConflict(
                "PROJECT_STAGE_ADVANCE_FORBIDDEN", "Project is not in AI analysis stage"
            )
        workflow = session.scalar(
            select(Workflow).where(Workflow.project_id == project.id)
        )
        required_nodes = [name for name, _ in ANALYSIS_NODES] + [SCRIPT_GENERATION_NODE]
        states = (
            []
            if workflow is None
            else list(
                session.scalars(
                    select(WorkflowNode.state).where(
                        WorkflowNode.workflow_id == workflow.id,
                        WorkflowNode.name.in_(required_nodes),
                    )
                )
            )
        )
        if len(states) != len(required_nodes) or any(
            state != "completed" for state in states
        ):
            raise ProjectLifecycleConflict(
                "PROJECT_ANALYSIS_INCOMPLETE", "AI analysis is not complete"
            )
        materialize_editor_draft(session, project=project)
        _record_stage(
            session, project=project, target_stage="edit", settings_snapshot=None
        )
        project.status = "waiting_for_edit"
        workflow.state = "waiting_for_edit"
        workflow.state_version += 1
    elif target_stage == "export":
        if project.current_stage != "generate" or project.status != "completed":
            raise ProjectLifecycleConflict(
                "PROJECT_EXPORT_NOT_READY", "Video generation is not complete"
            )
        _record_stage(
            session, project=project, target_stage="export", settings_snapshot=None
        )
    else:
        raise ProjectLifecycleConflict(
            "PROJECT_STAGE_ADVANCE_FORBIDDEN",
            "Use the stage-specific action to advance this project",
        )
    session.flush()
    return get_project_stage_detail(session, user_id=user_id, project_id=project_id)


def materialize_editor_draft(session: Session, *, project: Project) -> None:
    """将已完成脚本节点的规范化结果映射为真实且可编辑的草稿。"""

    videos = list(
        session.scalars(
            select(Asset)
            .where(
                Asset.project_id == project.id,
                Asset.asset_type == "video",
                Asset.status == "ready",
            )
            .order_by(Asset.sort_order, Asset.created_at, Asset.id)
        )
    )
    if not videos or any(
        asset.duration_seconds is None or asset.duration_seconds <= 0
        for asset in videos
    ):
        raise ProjectLifecycleConflict(
            "EDITOR_SOURCE_UNAVAILABLE",
            "Ready video assets with duration are required for editor",
        )
    settings = session.get(ProjectNarrationSettings, project.id)
    setting_values = dict(settings.settings) if settings is not None else {}
    background_music = session.execute(
        select(ProjectBackgroundMusic, Asset)
        .join(Asset, Asset.id == ProjectBackgroundMusic.asset_id)
        .where(ProjectBackgroundMusic.project_id == project.id, Asset.status == "ready")
    ).one_or_none()
    background_music_snapshot: dict[str, object] | None = None
    if background_music is not None:
        music, asset = background_music
        background_music_snapshot = {
            "asset_id": asset.id,
            "cdn_url": asset.cdn_url,
            "filename": asset.filename,
            "volume": music.volume,
        }
    workflow = session.scalar(select(Workflow).where(Workflow.project_id == project.id))
    script_attempt = (
        None
        if workflow is None
        else session.scalar(
            select(WorkflowNodeAttempt)
            .join(WorkflowNode)
            .where(
                WorkflowNode.workflow_id == workflow.id,
                WorkflowNode.name == SCRIPT_GENERATION_NODE,
                WorkflowNodeAttempt.state == "completed",
            )
            .order_by(WorkflowNodeAttempt.completed_at.desc())
        )
    )
    raw_result = script_attempt.result if script_attempt is not None else None
    payload = raw_result.get("result") if isinstance(raw_result, dict) else None
    editor_payload = payload.get("editor_draft") if isinstance(payload, dict) else None
    tracks = editor_payload.get("tracks") if isinstance(editor_payload, dict) else None
    timeline = (
        tracks[0].get("items")
        if isinstance(tracks, list) and tracks and isinstance(tracks[0], dict)
        else None
    )
    if not isinstance(timeline, list):
        raise ProjectLifecycleConflict(
            "PROJECT_SCRIPT_UNAVAILABLE",
            "Generated script is unavailable for the editor",
        )
    try:
        content = editor_draft_from_script(
            timeline=timeline,
            assets=videos,
            voice_id=str(setting_values.get("voice_id") or ""),
            background_music=background_music_snapshot,
            subtitle_style=str(setting_values.get("subtitle_style") or ""),
            video_ratio=str(setting_values.get("video_ratio") or ""),
        )
    except RenderSnapshotError as error:
        raise ProjectLifecycleConflict("PROJECT_SCRIPT_INVALID", str(error)) from error
    draft = session.get(EditorDraft, project.id)
    if draft is None:
        session.add(
            EditorDraft(id=_new_id("edr"), project_id=project.id, content=content)
        )
    else:
        draft.content = content


def advance_to_generate_from_editor(session: Session, *, project: Project) -> None:
    """编辑提交渲染是 edit -> generate 的唯一合法入口。"""

    if project.current_stage != "edit":
        raise ProjectLifecycleConflict(
            "PROJECT_STAGE_ADVANCE_FORBIDDEN", "Project is not in edit stage"
        )
    _record_stage(
        session, project=project, target_stage="generate", settings_snapshot=None
    )


def _render_snapshot_for_project(
    session: Session, *, project: Project, content: dict
) -> dict[str, object]:
    """从项目真实素材、设置与草稿构建唯一的 Core Render 快照。"""

    videos = list(
        session.scalars(
            select(Asset)
            .where(
                Asset.project_id == project.id,
                Asset.asset_type == "video",
                Asset.status == "ready",
            )
            .order_by(Asset.sort_order, Asset.created_at, Asset.id)
        )
    )
    narration = session.get(ProjectNarrationSettings, project.id)
    settings = dict(narration.settings) if narration is not None else {}
    row = session.execute(
        select(ProjectBackgroundMusic, Asset)
        .join(Asset, Asset.id == ProjectBackgroundMusic.asset_id)
        .where(
            ProjectBackgroundMusic.project_id == project.id,
            Asset.status == "ready",
        )
    ).one_or_none()
    background_music = (
        None
        if row is None
        else {
            "asset_id": row[1].id,
            "cdn_url": row[1].cdn_url,
            "volume": row[0].volume,
        }
    )
    try:
        return render_snapshot_from_draft(
            content=content,
            assets=videos,
            narration_settings=settings,
            background_music=background_music,
        )
    except RenderSnapshotError as error:
        raise ProjectLifecycleConflict("PROJECT_RENDER_INVALID", str(error)) from error


def queue_project_render(
    session: Session,
    *,
    project: Project,
    workflow: Workflow,
    idempotency_key: str,
    automatic: bool = False,
) -> str:
    """冻结 Revision、闭合编辑门并只通过 Outbox 请求真实 Core Render。"""

    if automatic and project.current_stage == "analysis":
        materialize_editor_draft(session, project=project)
        _record_stage(
            session, project=project, target_stage="edit", settings_snapshot=None
        )
        project.status = "waiting_for_edit"
        session.flush()
    if project.current_stage != "edit" or project.is_locked:
        raise ProjectLifecycleConflict(
            "PROJECT_STAGE_ADVANCE_FORBIDDEN", "Project is not ready to render"
        )
    draft = session.get(EditorDraft, project.id)
    if draft is None:
        raise ProjectLifecycleConflict(
            "PROJECT_SCRIPT_UNAVAILABLE", "Editor draft is unavailable"
        )
    render_node = session.scalar(
        select(WorkflowNode)
        .where(
            WorkflowNode.workflow_id == workflow.id,
            WorkflowNode.name == VIDEO_RENDER_NODE,
        )
        .with_for_update()
    )
    edit_gate = session.scalar(
        select(WorkflowNode)
        .where(
            WorkflowNode.workflow_id == workflow.id,
            WorkflowNode.name == EDIT_GATE_NODE,
        )
        .with_for_update()
    )
    if render_node is None or edit_gate is None or edit_gate.state != "queued":
        raise ProjectLifecycleConflict(
            "PROJECT_WORKFLOW_UNAVAILABLE", "Render workflow gate is unavailable"
        )
    render_snapshot = _render_snapshot_for_project(
        session, project=project, content=draft.content
    )
    revision = EditorRevision(
        id=_new_id("erv"),
        project_id=project.id,
        content={**draft.content, "render_snapshot": render_snapshot},
    )
    session.add(revision)
    edit_gate.state = "completed"
    project.is_locked = True
    advance_to_generate_from_editor(session, project=project)
    project.status = "render_queued"
    workflow.state = "render_queued"
    workflow.state_version += 1
    session.flush()
    session.add(
        WorkflowOutbox(
            id=_new_id("obx"),
            workflow_id=workflow.id,
            workflow_node_id=render_node.id,
            event_type="workflow.render_requested",
            idempotency_key=idempotency_key,
            payload={
                "state": "render_queued",
                "workflow_node_id": render_node.id,
                "revision_id": revision.id,
                "execution_mode": "auto" if automatic else "manual",
            },
            status="pending",
        )
    )
    return revision.id


def mark_project_render_completed(session: Session, *, project: Project) -> None:
    """将已经完成的渲染以服务端状态机方式收口到可导出阶段。"""

    if project.current_stage == "generate":
        _record_stage(
            session, project=project, target_stage="export", settings_snapshot=None
        )
    project.status = "completed"


def start_project(session: Session, *, user_id: str, project_id: str) -> str:
    """在已保存参数后创建真实 AI 分析四节点；不得由页面跳转绕过。"""

    project = _owned_project(session, user_id=user_id, project_id=project_id, lock=True)
    if project.current_stage != "settings" or project.status not in {"draft", "ready"}:
        raise ProjectLifecycleConflict(
            "PROJECT_SETTINGS_REQUIRED",
            "Save narration settings before starting AI analysis",
        )
    narration_settings = _validate_complete_narration_settings(
        _settings_snapshot(session, project.id)
    )
    _validate_source_subtitle_layouts(
        session, project_id=project.id, settings=narration_settings
    )
    credits, _, _, _ = _ready_quote(session, project=project)
    background_music = get_background_music_setting(
        session, user_id=user_id, project_id=project.id
    )
    snapshot = session.scalar(
        select(WorkflowTemplateSnapshot)
        .where(WorkflowTemplateSnapshot.template_name == project.product)
        .order_by(
            WorkflowTemplateSnapshot.created_at.desc(),
            WorkflowTemplateSnapshot.version.desc(),
        )
    )
    if snapshot is None:
        raise ProjectLifecycleConflict(
            "PROJECT_WORKFLOW_UNAVAILABLE", "Project workflow is unavailable"
        )
    try:
        _apply_credit(
            session,
            user_id=user_id,
            entry_type="charge",
            amount=-credits,
            idempotency_key=f"charge:{project.id}",
            reference_id=project.id,
            reason="project_charge",
        )
    except InsufficientCreditsError as error:
        raise ProjectLifecycleConflict(
            "INSUFFICIENT_CREDITS", "Insufficient credits"
        ) from error
    workflow = Workflow(
        id=_new_id("wfl"),
        user_id=user_id,
        project_id=project.id,
        template_snapshot_id=snapshot.id,
        state="queued",
        state_version=1,
    )
    session.add(workflow)
    # 新工作流的节点图必须覆盖完整手动链路；编辑和产物发布属于
    # 服务端可审计的门，不允许 EditorService 在提交时临时插入节点。
    for name, _label in ANALYSIS_NODES:
        session.add(
            WorkflowNode(
                id=_new_id("wnd"),
                workflow_id=workflow.id,
                name=name,
                state="queued",
                # 四项分析不是并发的装饰状态：每一步只消费已完成的上游结果。
                depends_on=list(ANALYSIS_DEPENDENCIES[name]),
                retryable=True,
                manual_gate=False,
                max_attempts=3,
            )
        )
    session.add(
        WorkflowNode(
            id=_new_id("wnd"),
            workflow_id=workflow.id,
            name=SCRIPT_GENERATION_NODE,
            state="queued",
            depends_on=["highlight_scoring"],
            retryable=True,
            manual_gate=False,
            max_attempts=3,
        )
    )
    session.add_all(
        (
            WorkflowNode(
                id=_new_id("wnd"),
                workflow_id=workflow.id,
                name=EDIT_GATE_NODE,
                state="queued",
                depends_on=[SCRIPT_GENERATION_NODE],
                retryable=False,
                manual_gate=True,
                max_attempts=1,
            ),
            WorkflowNode(
                id=_new_id("wnd"),
                workflow_id=workflow.id,
                name=VIDEO_RENDER_NODE,
                state="queued",
                depends_on=[EDIT_GATE_NODE],
                retryable=True,
                manual_gate=False,
                max_attempts=3,
            ),
            WorkflowNode(
                id=_new_id("wnd"),
                workflow_id=workflow.id,
                name=PUBLISH_ARTIFACTS_NODE,
                state="queued",
                depends_on=[VIDEO_RENDER_NODE],
                retryable=False,
                manual_gate=True,
                max_attempts=1,
            ),
        )
    )
    full_snapshot: dict[str, object] = {"narration": narration_settings}
    outbox_payload: dict[str, object] = {
        "state": "queued",
        "state_version": 1,
        "stage": "analysis",
        "analysis_tasks": [name for name, _label in ANALYSIS_NODES]
        + [SCRIPT_GENERATION_NODE],
        "settings_snapshot": full_snapshot,
    }
    if background_music is not None:
        # 将经项目归属和 ready 状态校验的音乐参数冻结到启动事件，避免后续设置变更影响本次渲染。
        outbox_payload["background_music"] = {
            "asset_id": background_music.asset_id,
            "cdn_url": background_music.cdn_url,
            "volume": background_music.volume,
        }
        full_snapshot["background_music"] = dict(outbox_payload["background_music"])
    session.add(
        WorkflowOutbox(
            id=_new_id("obx"),
            workflow_id=workflow.id,
            workflow_node_id=None,
            event_type="workflow.state_changed",
            idempotency_key=f"workflow-state:queued:{project.id}",
            payload=outbox_payload,
            status="pending",
        )
    )
    project.status = "queued"
    _record_stage(
        session,
        project=project,
        target_stage="analysis",
        settings_snapshot=full_snapshot,
    )
    return workflow.id


def save_settings_and_start_analysis(
    session: Session, *, user_id: str, project_id: str, settings: dict
) -> str:
    """设置页唯一的启动入口：在同一数据库事务中保存全量参数并创建分析任务。"""

    save_narration_settings(
        session, user_id=user_id, project_id=project_id, settings=settings
    )
    return start_project(session, user_id=user_id, project_id=project_id)


def ensure_project_deletable(status: str, current_stage: str | None = None) -> None:
    """按执行状态和生命周期阶段校验删除资格，不执行实际删除。"""

    is_terminal = status in _TERMINAL_DELETABLE_PROJECT_STATES
    is_before_analysis = (
        current_stage in _PRE_ANALYSIS_DELETABLE_PROJECT_STAGES
        and status not in _DELETION_STATES
    )
    if not (is_terminal or is_before_analysis):
        raise ProjectStateConflict(
            "project must be completed, failed, or not yet in AI analysis before deletion"
        )


def _new_deletion_job_id() -> str:
    """生成服务端删除审计记录 ID。"""

    return f"dlj_{time.time_ns():016x}{secrets.token_hex(8)}"


def request_project_deletion(
    session: Session, *, user_id: str, project_id: str
) -> ProjectDeletionRequest:
    """原子登记符合当前状态/阶段的删除请求；不执行 OSS 或 Worker 操作。"""

    project = session.scalar(
        select(Project)
        .where(Project.id == project_id, Project.user_id == user_id)
        .with_for_update()
    )
    if project is None:
        raise ProjectNotFoundError("project was not found")

    existing = session.scalar(
        select(DeletionJob).where(
            DeletionJob.project_id == project.id,
            DeletionJob.user_id == user_id,
        )
    )
    if existing is not None:
        return ProjectDeletionRequest(
            job_id=existing.id, project_id=project.id, status=existing.status
        )

    ensure_project_deletable(project.status, project.current_stage)
    job = DeletionJob(
        id=_new_deletion_job_id(),
        project_id=project.id,
        user_id=user_id,
        status="pending",
    )
    project.status = "deleting"
    session.add(job)
    session.flush()
    return ProjectDeletionRequest(
        job_id=job.id, project_id=project.id, status=job.status
    )


def ensure_project_exportable(status: str) -> None:
    """只校验项目是否具备导出资格，不执行导出。"""

    if status not in _EXPORTABLE_PROJECT_STATES:
        conflict = ProjectStateConflict("project must be completed before export")
        conflict.code = "PROJECT_NOT_COMPLETED"
        raise conflict


def visible_artifacts(status: str, artifacts: Iterable[Artifact]) -> list[Artifact]:
    """仅让已完成项目展示已登记的可导出产物。"""

    # 失败项目可能遗留中间文件，但不能向用户暴露任何产物。
    if status not in _ARTIFACT_VISIBLE_PROJECT_STATES:
        return []
    return list(artifacts)


def lookup_completed_project_result(
    session: Session, *, user_id: str, project_id: str
) -> CompletedProjectResult:
    """读取当前用户的已完成项目及其已登记产物。"""

    statement = select(Project).where(
        Project.id == project_id,
        Project.user_id == user_id,
    )
    project = session.scalar(statement)
    if project is None:
        raise ProjectResultLookupError("project result was not found")
    if project.status != "completed":
        error = ProjectResultLookupError("project result is not completed")
        error.code = "PROJECT_RESULT_NOT_COMPLETED"
        raise error

    artifacts = tuple(list_registered_artifacts(session, project=project))
    if (
        len(artifacts) != len(_REQUIRED_RENDER_ARTIFACT_KINDS)
        or {artifact.kind for artifact in artifacts} != _REQUIRED_RENDER_ARTIFACT_KINDS
    ):
        error = ProjectResultLookupError("project result artifacts are incomplete")
        error.code = "PROJECT_RESULT_ARTIFACTS_INCOMPLETE"
        raise error

    return CompletedProjectResult(project_id=project.id, artifacts=artifacts)
