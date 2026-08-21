from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from narrato_api.api.dependencies import get_request_id, get_settings
from narrato_api.api.errors import ApiError
from narrato_api.api.responses import ApiResponse, StrictModel
from narrato_api.config import Settings
from narrato_api.integrations.core_client import CoreClientError, HttpCoreClient

router = APIRouter()


class Option(StrictModel):
    """供前端直接渲染的稳定产品选项。"""

    id: str
    name: str


class NarrationStyleOption(Option):
    """短剧解说风格的展示信息，由产品配置统一下发。"""

    eyebrow: str
    description: str
    tags: list[str]
    is_custom: bool = False


class VoiceOption(Option):
    """Core 当前可调用音色的真实公开元数据。"""

    provider_code: str
    languages: list[str]
    gender: str | None = None
    styles: list[str]
    sample_url: str | None = None


class NarrationConfig(StrictModel):
    """短剧解说设置页的后端单一配置来源。"""

    narration_styles: list[NarrationStyleOption]
    video_ratios: list[Option]
    voices: list[VoiceOption]
    subtitle_styles: list[Option]
    original_sound_ratios: list[int]


_NARRATION_STYLE_OPTIONS = (
    ("霸总/甜宠", "高糖情感", "强情绪拉扯，突出心动与反转", ("甜宠", "强代入")),
    ("逆袭/复仇", "高能爽感", "节奏利落，放大逆转与高光时刻", ("逆袭", "爽点")),
    ("家庭伦理", "现实共鸣", "抓住人物关系与冲突张力", ("关系", "冲突")),
    ("古装/权谋", "沉浸叙事", "铺陈局势与人物博弈，语气克制", ("古风", "权谋")),
    ("悬疑/犯罪", "悬念推进", "保留关键线索，逐步制造压迫感", ("悬念", "线索")),
    ("都市情感", "细腻共情", "聚焦人物心绪与当下关系变化", ("情感", "共鸣")),
    ("年代/乡村", "生活质感", "突出时代氛围与朴实的人情味", ("年代", "烟火")),
    ("自定义类型", "自由设定", "输入你的题材或专属表达方向", ("自定义", "灵活")),
)


@router.get(
    "/products/short-drama-narration/config",
    response_model=ApiResponse[NarrationConfig],
)
def get_short_drama_narration_config(
    request_id: Annotated[str, Depends(get_request_id)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ApiResponse[NarrationConfig]:
    """返回产品选项；音色必须来自 Core 当前真实能力目录。"""

    try:
        voices = HttpCoreClient(
            base_url=str(settings.core_base_url),
            request_token=settings.core_request_token,
        ).get_voice_capabilities()
    except CoreClientError as error:
        raise ApiError(
            "CORE_CAPABILITIES_UNAVAILABLE",
            "Core voice capabilities are unavailable",
            503,
        ) from error
    if not voices:
        raise ApiError(
            "CORE_VOICE_UNAVAILABLE", "No callable Core voice is configured", 503
        )

    config = NarrationConfig(
        narration_styles=[
            NarrationStyleOption(
                id=name,
                name=name,
                eyebrow=eyebrow,
                description=description,
                tags=list(tags),
                is_custom=name == "自定义类型",
            )
            for name, eyebrow, description, tags in _NARRATION_STYLE_OPTIONS
        ],
        video_ratios=[
            Option(id=item, name=item) for item in ("9:16", "16:9", "4:3", "3:4", "1:1")
        ],
        voices=[
            VoiceOption(
                id=item.voice_id,
                name=item.name,
                provider_code=item.provider_code,
                languages=list(item.languages),
                gender=item.gender,
                styles=list(item.styles),
                sample_url=item.sample_url,
            )
            for item in voices
        ],
        subtitle_styles=[
            Option(id=item, name=item) for item in ("霓虹描边", "经典白色", "白字蓝边")
        ],
        # 与 `streamlit run webui.py` 的 SHORT_DRAMA_ORIGINAL_SOUND_RATIO_OPTIONS
        # 保持同一组可选值，默认值由设置契约固定为 30。
        original_sound_ratios=list(range(0, 100, 10)),
    )
    return ApiResponse(
        code="OK", message="短剧解说配置读取成功", data=config, request_id=request_id
    )
