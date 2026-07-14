from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Any, Optional, Literal, Tuple

from pydantic import BaseModel, Field


class ShotInfo(BaseModel):
    """单个镜头信息"""
    shot_id: int = Field(..., description="镜头编号(从1开始)")
    start_time: float = Field(..., description="起始时间(秒)")
    end_time: float = Field(..., description="结束时间(秒)")
    duration: float = Field(..., description="持续时间(秒)")
    keyframe_path: str = Field(..., description="关键帧图片路径")
    content_description: str = Field(default="", description="LLM生成的内容描述")
    quality_status: Literal["pass", "warning", "error"] = Field(default="pass", description="质量状态")
    issues: List[str] = Field(default_factory=list, description="问题列表")
    suggestions: List[str] = Field(default_factory=list, description="修改建议")


class DimensionScore(BaseModel):
    """单个维度的评分"""
    dimension: Literal["consistency", "coherence", "duplicate", "rhythm", "waste"] = Field(..., description="维度名称")
    status: Literal["pass", "warning", "error"] = Field(..., description="状态")
    score: float = Field(..., ge=0, le=100, description="0-100分")
    description: str = Field(..., description="简要说明")
    reason: str = Field(default="", description="评分原因")
    evidence: List[str] = Field(default_factory=list, description="评分依据/证据")
    suggestions: List[str] = Field(default_factory=list, description="改进建议")
    confidence: float = Field(default=0.5, ge=0, le=1, description="评分置信度")
    details: Dict[str, Any] = Field(default_factory=dict, description="详细数据")


class DiagnosisResult(BaseModel):
    """完整诊断结果"""
    task_id: str = Field(..., description="任务ID")
    video_path: str = Field(..., description="视频路径")
    video_duration: float = Field(..., description="视频总时长(秒)")
    total_shots: int = Field(..., description="镜头总数")
    overall_grade: Literal["A", "B", "C", "D"] = Field(default="B", description="总体评级")
    summary: str = Field(default="", description="LLM生成的总结文案")
    dimension_scores: List[DimensionScore] = Field(default_factory=list, description="各维度评分")
    shot_details: List[ShotInfo] = Field(default_factory=list, description="逐镜详情")
    editing_plan: Optional[Dict[str, Any]] = Field(default=None, description="智能剪辑方案")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


@dataclass
class PreprocessedVideo:
    """预处理后的视频信息"""
    video_path: str
    duration: float
    width: int
    height: int
    fps: float
    shots: List[Tuple[float, float]]  # 镜头列表 [(start, end), ...]
    keyframe_dir: str
    keyframe_paths: List[str] = field(default_factory=list)
