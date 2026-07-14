"""
视频诊断类型配置。

不同类型的视频对节奏、长镜头、抽帧和 VLM 调用预算的容忍度不同。
本模块集中定义这些差异，避免分析器里散落硬编码阈值。
"""

from dataclasses import dataclass, replace
from enum import Enum
from typing import Dict, Tuple


class VideoType(str, Enum):
    SHORT_DRAMA = "short_drama"
    FILM_TV = "film_tv"
    DOCUMENTARY = "documentary"
    GENERAL = "general"


class AnalysisMode(str, Enum):
    FAST = "fast"
    STANDARD = "standard"
    DEEP = "deep"


@dataclass(frozen=True)
class AnalysisBudget:
    max_keyframes: int
    max_vlm_calls: int
    max_duplicate_pairs: int
    max_transition_checks: int
    max_shot_descriptions: int


@dataclass(frozen=True)
class RhythmProfile:
    fast_pace_threshold: float
    slow_pace_threshold: float
    long_shot_threshold: float
    unstable_std_threshold: float
    short_shot_threshold: float = 1.0
    abnormal_run_length: int = 3


@dataclass(frozen=True)
class WasteProfile:
    black_overlap_threshold: float = 0.3
    silence_overlap_ratio: float = 0.8


@dataclass(frozen=True)
class VideoTypeProfile:
    video_type: VideoType
    mode: AnalysisMode
    display_name: str
    prompt_context: str
    scene_threshold: float
    rhythm: RhythmProfile
    waste: WasteProfile
    budget: AnalysisBudget
    focus_dimensions: Tuple[str, ...]


_STANDARD_BUDGET = AnalysisBudget(
    max_keyframes=80,
    max_vlm_calls=20,
    max_duplicate_pairs=20,
    max_transition_checks=20,
    max_shot_descriptions=30,
)

_FAST_BUDGET = AnalysisBudget(
    max_keyframes=40,
    max_vlm_calls=8,
    max_duplicate_pairs=8,
    max_transition_checks=8,
    max_shot_descriptions=12,
)

_DEEP_BUDGET = AnalysisBudget(
    max_keyframes=160,
    max_vlm_calls=45,
    max_duplicate_pairs=50,
    max_transition_checks=50,
    max_shot_descriptions=80,
)

_BASE_PROFILES: Dict[VideoType, VideoTypeProfile] = {
    VideoType.SHORT_DRAMA: VideoTypeProfile(
        video_type=VideoType.SHORT_DRAMA,
        mode=AnalysisMode.STANDARD,
        display_name="短剧",
        prompt_context="这是短剧/爽剧视频，快节奏和情绪反转是正常表达；重点关注剧情连贯、人物/场景连续性、废片和重复镜头。",
        scene_threshold=0.35,
        rhythm=RhythmProfile(
            fast_pace_threshold=1.5,
            slow_pace_threshold=6.0,
            long_shot_threshold=8.0,
            unstable_std_threshold=4.0,
        ),
        waste=WasteProfile(),
        budget=_STANDARD_BUDGET,
        focus_dimensions=("coherence", "waste", "duplicate", "rhythm"),
    ),
    VideoType.FILM_TV: VideoTypeProfile(
        video_type=VideoType.FILM_TV,
        mode=AnalysisMode.STANDARD,
        display_name="影视解说",
        prompt_context="这是影视解说/影视混剪视频，原片片段可适当偏长；重点关注画面是否服务剧情文案、原声片段是否承载信息、剪辑承接是否自然。",
        scene_threshold=0.4,
        rhythm=RhythmProfile(
            fast_pace_threshold=2.0,
            slow_pace_threshold=8.0,
            long_shot_threshold=12.0,
            unstable_std_threshold=5.0,
        ),
        waste=WasteProfile(),
        budget=_STANDARD_BUDGET,
        focus_dimensions=("coherence", "rhythm", "duplicate", "waste"),
    ),
    VideoType.DOCUMENTARY: VideoTypeProfile(
        video_type=VideoType.DOCUMENTARY,
        mode=AnalysisMode.STANDARD,
        display_name="纪录片/纪实",
        prompt_context="这是纪录片/纪实视频，长镜头、环境音和空镜可能承担信息表达；不要仅因镜头较长或静音就判为问题。",
        scene_threshold=0.45,
        rhythm=RhythmProfile(
            fast_pace_threshold=3.0,
            slow_pace_threshold=14.0,
            long_shot_threshold=20.0,
            unstable_std_threshold=8.0,
        ),
        waste=WasteProfile(silence_overlap_ratio=0.95),
        budget=replace(_STANDARD_BUDGET, max_vlm_calls=14, max_transition_checks=12),
        focus_dimensions=("consistency", "rhythm", "waste"),
    ),
    VideoType.GENERAL: VideoTypeProfile(
        video_type=VideoType.GENERAL,
        mode=AnalysisMode.STANDARD,
        display_name="通用",
        prompt_context="这是通用视频，请按常规短视频剪辑标准判断，避免过度裁剪不确定片段。",
        scene_threshold=0.4,
        rhythm=RhythmProfile(
            fast_pace_threshold=2.0,
            slow_pace_threshold=8.0,
            long_shot_threshold=10.0,
            unstable_std_threshold=5.0,
        ),
        waste=WasteProfile(),
        budget=_STANDARD_BUDGET,
        focus_dimensions=("consistency", "coherence", "duplicate", "rhythm", "waste"),
    ),
}


def normalize_video_type(value: str | VideoType | None) -> VideoType:
    if isinstance(value, VideoType):
        return value
    if not value:
        return VideoType.GENERAL
    try:
        return VideoType(str(value))
    except ValueError:
        return VideoType.GENERAL


def normalize_analysis_mode(value: str | AnalysisMode | None) -> AnalysisMode:
    if isinstance(value, AnalysisMode):
        return value
    if not value:
        return AnalysisMode.STANDARD
    try:
        return AnalysisMode(str(value))
    except ValueError:
        return AnalysisMode.STANDARD


def _budget_for_mode(profile: VideoTypeProfile, mode: AnalysisMode) -> AnalysisBudget:
    if mode == AnalysisMode.FAST:
        return _FAST_BUDGET
    if mode == AnalysisMode.DEEP:
        return _DEEP_BUDGET
    return profile.budget


def get_video_type_profile(
    video_type: str | VideoType | None = None,
    mode: str | AnalysisMode | None = None,
) -> VideoTypeProfile:
    resolved_type = normalize_video_type(video_type)
    resolved_mode = normalize_analysis_mode(mode)
    base = _BASE_PROFILES[resolved_type]
    return replace(base, mode=resolved_mode, budget=_budget_for_mode(base, resolved_mode))


VIDEO_TYPE_LABELS = {
    "短剧": VideoType.SHORT_DRAMA.value,
    "影视解说": VideoType.FILM_TV.value,
    "纪录片/纪实": VideoType.DOCUMENTARY.value,
    "通用": VideoType.GENERAL.value,
}
