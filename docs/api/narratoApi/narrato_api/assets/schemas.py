from __future__ import annotations

from typing import Literal

from pydantic import Field

from narrato_api.api.responses import StrictModel


class UploadPolicyRequest(StrictModel):
    """申请单个 OSS 表单所需的受限文件声明。"""

    asset_type: Literal["video", "subtitle"]
    filename: str = Field(min_length=1, max_length=255)
    size_bytes: int = Field(ge=0)
    content_type: str = Field(min_length=1, max_length=128)


class UploadCompleteRequest(UploadPolicyRequest):
    """浏览器直传完成后提交的对象定位信息。"""

    object_key: str = Field(min_length=1, max_length=1024)


class UploadPolicyData(StrictModel):
    """前端直接提交 OSS 的短期策略响应。"""

    url: str
    key: str
    fields: dict[str, str]
    max_size_bytes: int


class AssetData(StrictModel):
    """上传确认后可轮询的资产状态。"""

    id: str
    status: Literal["validating", "ready", "invalid"]
