from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field

from core_api.adapters.narrato.jianying import JianyingBuilder, JianyingInputError
from core_api.api.dependencies import (
    get_request_id,
    get_settings,
    require_service_token,
)
from core_api.api.errors import ApiError
from core_api.api.responses import envelope
from core_api.api.routes.video_analysis import validate_source_url
from core_api.config import Settings


class JianyingResourceInput(BaseModel):
    """一个已登记且可公开下载的剪映资源。"""

    model_config = ConfigDict(extra="forbid")
    kind: str = Field(pattern="^(video|subtitle|voice|timeline)$")
    zip_path: str = Field(min_length=1, max_length=1024)
    url: str = Field(min_length=1, max_length=2048)
    size: int = Field(gt=0, le=10 * 1024 * 1024 * 1024)
    checksum: str = Field(min_length=8, max_length=128)
    content_type: str = Field(min_length=1, max_length=160)
    width: int | None = Field(default=None, ge=1, le=16_384)
    height: int | None = Field(default=None, ge=1, le=16_384)
    duration: float | None = Field(default=None, gt=0, le=86_400)


class JianyingTimelineInput(BaseModel):
    """不可变编辑 revision 中的一段显式来源时间线。"""

    model_config = ConfigDict(extra="forbid")
    source_asset_id: str = Field(min_length=1, max_length=80)
    start: float = Field(ge=0, le=86_400)
    end: float = Field(gt=0, le=86_400)
    narration: str = Field(min_length=1, max_length=10_000)


class JianyingManifestRequest(BaseModel):
    """剪映 Manifest 同步无状态请求。"""

    model_config = ConfigDict(extra="forbid")
    snapshot_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,80}$")
    timeline: list[JianyingTimelineInput] = Field(min_length=1, max_length=500)
    resources: list[JianyingResourceInput] = Field(
        default_factory=list, max_length=1_000
    )


router = APIRouter(dependencies=[Depends(require_service_token)])


@router.post("/manifests/build")
def build_jianying_manifest(
    payload: JianyingManifestRequest,
    request_id: str = Depends(get_request_id),
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    """同步返回基础文件和资源映射，不创建导出任务、ZIP 或数据库记录。"""
    try:
        result = JianyingBuilder().build(
            snapshot_id=payload.snapshot_id,
            timeline=[item.model_dump(mode="json") for item in payload.timeline],
            resources=[
                {
                    **item.model_dump(mode="json"),
                    "url": validate_source_url(settings, item.url, core_artifact=True),
                }
                for item in payload.resources
            ],
        )
    except JianyingInputError as exc:
        raise ApiError(exc.code, "剪映 Manifest 输入无效", 422) from exc
    return envelope(
        request_id=request_id,
        code="JIANYING_MANIFEST_BUILT",
        message="Manifest 已生成",
        data=result.to_dict(),
    )
