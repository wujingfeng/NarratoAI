from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Literal


SegmentStatus = Literal["keep", "adjust", "delete", "error"]
HighlightLevel = Literal["low", "medium", "high"]


@dataclass
class OverallScriptDiagnosis:
    total_segments: int
    target_original_sound_ratio: int
    current_original_sound_ratio: float
    target_original_sound_count: int
    current_original_sound_count: int
    ratio_status: Literal["ok", "low", "high"]
    ratio_gap_count: int
    ratio_adjustment_suggestions: List[str] = field(default_factory=list)


@dataclass
class SegmentDiagnosis:
    item_id: Any
    status: SegmentStatus
    score: int
    highlight_score: int
    highlight_level: HighlightLevel
    decision: str
    reason: str
    evidence: List[str] = field(default_factory=list)
    suggestions: List[Dict[str, Any]] = field(default_factory=list)
    ratio_impact: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.7
    needs_visual_review: bool = False


@dataclass
class ScriptDiagnosisResult:
    overall: OverallScriptDiagnosis
    segments: List[SegmentDiagnosis]
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
