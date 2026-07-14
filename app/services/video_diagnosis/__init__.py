"""视频诊断模块"""

from app.services.video_diagnosis.preprocessor import (
    ShotDetector,
    KeyframeExtractor,
    VideoPreprocessor,
    PreprocessedVideo
)

from app.services.video_diagnosis.quality_analyzer import (
    DimensionAnalyzer,
    MultiDimensionAnalyzer,
    ConsistencyChecker,
    CoherenceChecker,
    DuplicateDetector,
    RhythmAnalyzer,
    WasteClipDetector
)

from app.services.video_diagnosis.shot_analyzer import ShotLevelAnalyzer, EditingPlanGenerator
from app.services.video_diagnosis.service import VideoDiagnosisService
from app.services.video_diagnosis.pdf_reporter import PDFReporter

__all__ = [
    # 预处理
    'ShotDetector',
    'KeyframeExtractor',
    'VideoPreprocessor',
    'PreprocessedVideo',
    
    # 质量评估
    'DimensionAnalyzer',
    'MultiDimensionAnalyzer',
    'ConsistencyChecker',
    'CoherenceChecker',
    'DuplicateDetector',
    'RhythmAnalyzer',
    'WasteClipDetector',
    
    # 逐镜分析
    'ShotLevelAnalyzer',
    
    # 剪辑方案
    'EditingPlanGenerator',
    
    # 主服务
    'VideoDiagnosisService',
    'PDFReporter'
]
