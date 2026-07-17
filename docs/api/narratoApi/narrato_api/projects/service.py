from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
import secrets
import time
from typing import TypeVar

from sqlalchemy import select
from sqlalchemy.orm import Session

from narrato_api.artifacts.models import RegisteredArtifact
from narrato_api.artifacts.service import list_registered_artifacts
from narrato_api.assets.models import Asset
from narrato_api.billing.models import ProductPrice
from narrato_api.billing.pricing import estimate_short_drama_cost
from narrato_api.billing.service import InsufficientCreditsError, _apply_credit
from narrato_api.projects.models import DeletionJob, Project
from narrato_api.workflows.models import Workflow, WorkflowNode, WorkflowOutbox, WorkflowTemplateSnapshot
from narrato_api.workflows.service import _new_id, _snapshot_nodes


Artifact = TypeVar("Artifact")


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


_DELETABLE_PROJECT_STATES = frozenset({"completed", "failed"})
_ARTIFACT_VISIBLE_PROJECT_STATES = frozenset({"completed"})
_EXPORTABLE_PROJECT_STATES = frozenset({"completed"})


def _new_project_id() -> str:
    return f"prj_{time.time_ns():016x}{secrets.token_hex(8)}"


def create_project(session: Session, *, user_id: str, product: str) -> Project:
    """创建短剧解说草稿；对 Web 的 kebab-case 产品名做唯一映射。"""

    if product != "short-drama-narration":
        raise ProjectLifecycleConflict("PROJECT_PRODUCT_UNSUPPORTED", "Project product is unsupported")
    project = Project(id=_new_project_id(), user_id=user_id, product="short_drama_narration", status="draft")
    session.add(project)
    session.flush()
    return project


def _owned_project(session: Session, *, user_id: str, project_id: str, lock: bool = False) -> Project:
    statement = select(Project).where(Project.id == project_id, Project.user_id == user_id)
    if lock:
        statement = statement.with_for_update()
    project = session.scalar(statement)
    if project is None:
        raise ProjectNotFoundError("project was not found")
    return project


def _ready_quote(session: Session, *, project: Project) -> tuple[int, int, int]:
    assets = list(session.scalars(select(Asset).where(Asset.project_id == project.id)))
    videos = [asset for asset in assets if asset.asset_type == "video"]
    if not videos or any(asset.status != "ready" for asset in assets):
        raise ProjectLifecycleConflict("PROJECT_ASSETS_NOT_READY", "Project assets are not ready")
    if any(asset.duration_seconds is None for asset in videos):
        raise ProjectLifecycleConflict("PROJECT_DURATION_UNAVAILABLE", "Project media duration is unavailable")
    price = session.scalar(select(ProductPrice).where(ProductPrice.product == project.product).order_by(ProductPrice.version.desc()))
    if price is None:
        raise ProjectLifecycleConflict("PROJECT_PRICE_UNAVAILABLE", "Project price is unavailable")
    total_seconds = int(sum(asset.duration_seconds or 0 for asset in videos))
    return estimate_short_drama_cost(total_seconds, credits_per_minute=price.credits_per_minute), total_seconds, price.credits_per_minute


def estimate_project_cost(session: Session, *, user_id: str, project_id: str) -> tuple[int, int, int]:
    """返回由已验证媒体真实时长和当前产品价目计算的报价。"""

    return _ready_quote(session, project=_owned_project(session, user_id=user_id, project_id=project_id))


def start_project(session: Session, *, user_id: str, project_id: str) -> str:
    """在同一事务内复核素材、扣费、冻结模板并创建 queued 工作流。"""

    project = _owned_project(session, user_id=user_id, project_id=project_id, lock=True)
    if project.status not in {"draft", "ready"}:
        raise ProjectLifecycleConflict("PROJECT_NOT_STARTABLE", "Project cannot be started")
    credits, _, _ = _ready_quote(session, project=project)
    snapshot = session.scalar(select(WorkflowTemplateSnapshot).where(WorkflowTemplateSnapshot.template_name == project.product).order_by(WorkflowTemplateSnapshot.created_at.desc()))
    if snapshot is None:
        raise ProjectLifecycleConflict("PROJECT_WORKFLOW_UNAVAILABLE", "Project workflow is unavailable")
    try:
        _apply_credit(session, user_id=user_id, entry_type="charge", amount=-credits, idempotency_key=f"charge:{project.id}", reference_id=project.id, reason="project_charge")
    except InsufficientCreditsError as error:
        raise ProjectLifecycleConflict("INSUFFICIENT_CREDITS", "Insufficient credits") from error
    workflow = Workflow(id=_new_id("wfl"), user_id=user_id, project_id=project.id, template_snapshot_id=snapshot.id, state="queued", state_version=1)
    session.add(workflow)
    for node in _snapshot_nodes(snapshot.definition):
        session.add(WorkflowNode(id=_new_id("wnd"), workflow_id=workflow.id, name=node["name"], state="queued", depends_on=node["depends_on"], retryable=node["retryable"], manual_gate=node["manual_gate"], max_attempts=node["max_attempts"]))
    session.add(WorkflowOutbox(id=_new_id("obx"), workflow_id=workflow.id, workflow_node_id=None, event_type="workflow.state_changed", idempotency_key=f"workflow-state:queued:{project.id}", payload={"state": "queued", "state_version": 1}, status="pending"))
    project.status = "queued"
    return workflow.id


def ensure_project_deletable(status: str) -> None:
    """只校验终态项目是否具备删除资格，不执行删除。"""

    if status not in _DELETABLE_PROJECT_STATES:
        raise ProjectStateConflict(
            "project must be completed or failed before deletion"
        )


def _new_deletion_job_id() -> str:
    """生成服务端删除审计记录 ID。"""

    return f"dlj_{time.time_ns():016x}{secrets.token_hex(8)}"


def request_project_deletion(
    session: Session, *, user_id: str, project_id: str
) -> ProjectDeletionRequest:
    """原子登记终态项目删除请求；只写审计 Job，不执行 OSS 或 Worker 操作。"""

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

    ensure_project_deletable(project.status)
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

    return CompletedProjectResult(
        project_id=project.id,
        artifacts=tuple(list_registered_artifacts(session, project=project)),
    )
