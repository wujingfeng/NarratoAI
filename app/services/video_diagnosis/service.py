"""
视频诊断服务 - 完整流水线编排

串联5个Phase完成视频诊断:
  Phase 0: 初始化任务状态
  Phase 1: 视频预处理(场景检测 + 关键帧提取)
  Phase 2: 多维度质量评估(5维度)
  Phase 3: 逐镜分析与建议
  Phase 4: 智能剪辑方案生成
  Phase 5: 结果整合与输出(JSON + PDF)
"""

import asyncio
import json
import os
from datetime import datetime
from typing import Optional, Dict, Any, List, Literal
import logging

from app.models.diagnosis_schema import DiagnosisResult, DimensionScore, ShotInfo, PreprocessedVideo
from app.models import const
from app.services.video_diagnosis.preprocessor import VideoPreprocessor
from app.services.video_diagnosis.quality_analyzer import MultiDimensionAnalyzer
from app.services.video_diagnosis.shot_analyzer import ShotLevelAnalyzer, EditingPlanGenerator
from app.services.video_diagnosis.pdf_reporter import PDFReporter
from app.services.video_diagnosis.profiles import get_video_type_profile

_HAS_EDITING_PLANNER = True

from app.services.state import state

logger = logging.getLogger(__name__)


class VideoDiagnosisService:
    """视频诊断服务 - 完整流水线编排"""

    def __init__(self):
        self.preprocessor = VideoPreprocessor()
        self.quality_analyzer = MultiDimensionAnalyzer()
        self.shot_analyzer = ShotLevelAnalyzer()
        self.editing_planner = EditingPlanGenerator() if _HAS_EDITING_PLANNER else None
        self.pdf_reporter = PDFReporter()

    async def diagnose(
        self,
        video_path: str,
        task_id: str,
        subtitle_path: Optional[str] = None,
        mode: Literal["fast", "full", "standard", "deep"] = "full",
        editing_mode: Literal["conservative", "aggressive"] = "conservative",
        video_type: str = "general",
    ) -> DiagnosisResult:
        """
        执行完整的视频诊断流程

        Args:
            video_path: 视频文件路径
            task_id: 任务ID
            subtitle_path: 可选的字幕文件路径
            mode: 诊断模式
                - fast: 快速模式(抽样分析,减少LLM调用)
                - full: 全量分析
            editing_mode: 剪辑模式

        Returns:
            DiagnosisResult: 诊断结果

        Raises:
            RuntimeError: 诊断过程失败
        """
        try:
            # Phase 0: 初始化任务状态
            analysis_mode = "standard" if mode == "full" else mode
            profile = get_video_type_profile(video_type=video_type, mode=analysis_mode)
            await self._update_progress(task_id, 0, "初始化诊断任务...")

            # Phase 1: 视频预处理 (进度: 0-20%)
            await self._update_progress(
                task_id,
                5,
                f"正在检测场景切换...（{profile.display_name}/{profile.mode.value}）",
            )
            preprocessed = await asyncio.to_thread(
                VideoPreprocessor(profile=profile).preprocess, video_path, task_id
            )
            await self._update_progress(
                task_id, 20, f"预处理完成,检测到{len(preprocessed.shots)}个镜头"
            )

            # Phase 2: 多维度质量评估 (进度: 20-50%)
            await self._update_progress(task_id, 25, "正在进行一致性检查...")
            quality_results = await MultiDimensionAnalyzer(profile=profile).analyze_all(
                keyframe_paths=preprocessed.keyframe_paths,
                shots=preprocessed.shots,
                video_path=video_path,
            )
            await self._update_progress(task_id, 50, "质量评估完成")

            # Phase 3: 逐镜分析与建议 (进度: 50-75%)
            await self._update_progress(task_id, 55, "正在生成逐镜描述...")
            shot_details = await ShotLevelAnalyzer(profile=profile).analyze_all_shots(
                keyframe_paths=preprocessed.keyframe_paths,
                shots=preprocessed.shots,
                quality_results=quality_results,
            )
            await self._update_progress(task_id, 75, "逐镜分析完成")

            # Phase 4: 智能剪辑方案生成 (进度: 75-85%)
            await self._update_progress(task_id, 80, "正在生成剪辑方案...")
            if self.editing_planner is not None:
                editing_plan = await asyncio.to_thread(
                    self.editing_planner.generate_plan,
                    video_path=video_path,
                    shot_details=shot_details,
                    mode=editing_mode,
                )
            else:
                logger.warning("EditingPlanGenerator 不可用，跳过剪辑方案生成")
                editing_plan = {"video_clips": [], "transitions": [], "mode": editing_mode, "total_duration": 0}
            await self._update_progress(task_id, 85, "剪辑方案生成完成")

            # Phase 5: 结果整合与输出 (进度: 85-100%)
            await self._update_progress(task_id, 90, "正在生成诊断报告...")

            # 构建 DiagnosisResult
            diagnosis_result = self._build_diagnosis_result(
                task_id=task_id,
                video_path=video_path,
                preprocessed=preprocessed,
                quality_results=quality_results,
                shot_details=shot_details,
                editing_plan=editing_plan,
            )

            # 保存结构化结果
            await self._save_results(task_id, diagnosis_result)

            # 生成PDF报告
            pdf_path = await self.pdf_reporter.generate_report(
                diagnosis_result, task_id
            )

            result_path = f"storage/tasks/{task_id}/diagnosis_result.json"
            await self._update_progress(task_id, 100, "诊断完成")
            # 将最终结果路径写入 state，供前端读取
            state.update_task(
                task_id,
                state=const.TASK_STATE_COMPLETE,
                progress=100,
                message="诊断完成",
                result_path=result_path,
                pdf_path=pdf_path or "",
            )
            logger.info(f"诊断完成(task_id={task_id}), PDF: {pdf_path}")

            return diagnosis_result

        except Exception as e:
            logger.error(f"诊断失败(task_id={task_id}): {str(e)}")
            state.update_task(
                task_id,
                state=const.TASK_STATE_FAILED,
                progress=0,
                message=f"诊断失败: {str(e)}",
            )
            raise RuntimeError(f"视频诊断失败: {str(e)}") from e

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    async def _update_progress(self, task_id: str, progress: int, message: str):
        """更新任务进度"""
        task_state = (
            const.TASK_STATE_FAILED
            if progress < 0
            else (
                const.TASK_STATE_COMPLETE
                if progress >= 100
                else const.TASK_STATE_PROCESSING
            )
        )
        state.update_task(
            task_id, state=task_state, progress=progress, message=message
        )

    def _build_diagnosis_result(
        self,
        task_id: str,
        video_path: str,
        preprocessed: PreprocessedVideo,
        quality_results: Dict[str, Any],
        shot_details: List[ShotInfo],
        editing_plan: Dict[str, Any],
    ) -> DiagnosisResult:
        """构建完整的诊断结果对象"""

        # 将质量评估结果转换为 DimensionScore 列表
        dimension_scores: List[DimensionScore] = []
        for dim_name, dim_result in quality_results.items():
            if isinstance(dim_result, dict) and "status" in dim_result:
                score = DimensionScore(
                    dimension=dim_name,
                    status=dim_result.get("status", "warning"),
                    score=dim_result.get("score", 50.0),
                    description=dim_result.get("description", ""),
                    reason=self._extract_dimension_reason(dim_result),
                    evidence=self._extract_dimension_evidence(dim_name, dim_result),
                    suggestions=self._extract_dimension_suggestions(dim_result),
                    confidence=self._extract_dimension_confidence(dim_result),
                    details=dim_result.get("details", {}),
                )
                dimension_scores.append(score)

        # 计算总体评级
        overall_grade = self._calculate_overall_grade(dimension_scores)

        # 生成总结文案
        summary = self._generate_summary(
            preprocessed.duration,
            len(preprocessed.shots),
            dimension_scores,
            shot_details,
        )

        return DiagnosisResult(
            task_id=task_id,
            video_path=video_path,
            video_duration=preprocessed.duration,
            total_shots=len(preprocessed.shots),
            overall_grade=overall_grade,
            summary=summary,
            dimension_scores=dimension_scores,
            shot_details=shot_details,
            editing_plan=editing_plan,
            created_at=datetime.now(),
        )

    @staticmethod
    def _extract_dimension_reason(dim_result: Dict[str, Any]) -> str:
        """从维度分析结果中提取可读评分原因"""
        reason = dim_result.get("reason") or dim_result.get("description") or ""
        return str(reason).strip()

    @staticmethod
    def _extract_dimension_evidence(dim_name: str, dim_result: Dict[str, Any]) -> List[str]:
        """把不同维度的原始问题字段整理成统一证据列表"""
        evidence: List[str] = []
        evidence.extend(VideoDiagnosisService._normalize_string_list(dim_result.get("evidence")))
        evidence.extend(VideoDiagnosisService._normalize_string_list(dim_result.get("issues")))

        for pair in dim_result.get("problematic_transitions") or []:
            if isinstance(pair, (list, tuple)) and len(pair) >= 2:
                evidence.append(f"转场: 镜头{pair[0]} -> 镜头{pair[1]}")
            elif pair:
                evidence.append(str(pair))

        for pair in dim_result.get("duplicate_pairs") or []:
            if isinstance(pair, (list, tuple)) and len(pair) >= 2:
                confidence = pair[2] if len(pair) >= 3 else None
                suffix = f"，相似度{float(confidence):.2f}" if isinstance(confidence, (int, float)) else ""
                evidence.append(f"重复: 镜头{pair[0]} 与 镜头{pair[1]}{suffix}")
            elif pair:
                evidence.append(str(pair))

        for item in dim_result.get("problematic_ranges") or []:
            if isinstance(item, (list, tuple)) and len(item) >= 3:
                evidence.append(f"异常区间: 镜头{item[0]}-{item[1]}，{item[2]}")
            elif item:
                evidence.append(str(item))

        for clip in dim_result.get("confirmed_waste_clips") or []:
            if isinstance(clip, dict):
                shot_id = clip.get("shot_id") or clip.get("shot") or clip.get("index")
                reason = clip.get("reason") or clip.get("description") or clip.get("type") or "疑似废片"
                action = clip.get("recommended_action") or clip.get("action")
                prefix = f"镜头{shot_id}: " if shot_id is not None else ""
                suffix = f"，建议{action}" if action else ""
                evidence.append(f"{prefix}{reason}{suffix}")
            elif clip:
                evidence.append(str(clip))

        if not evidence and dim_result.get("description"):
            evidence.append(str(dim_result["description"]))

        return VideoDiagnosisService._dedupe_keep_order(evidence)[:8]

    @staticmethod
    def _extract_dimension_suggestions(dim_result: Dict[str, Any]) -> List[str]:
        """提取或兜底生成维度改进建议"""
        suggestions = VideoDiagnosisService._normalize_string_list(dim_result.get("suggestions"))
        if suggestions:
            return VideoDiagnosisService._dedupe_keep_order(suggestions)[:6]

        generated: List[str] = []
        for clip in dim_result.get("confirmed_waste_clips") or []:
            if isinstance(clip, dict):
                action = clip.get("recommended_action") or clip.get("action")
                reason = clip.get("reason") or clip.get("description") or "疑似废片"
                shot_id = clip.get("shot_id") or clip.get("shot") or clip.get("index")
                if action:
                    target = f"镜头{shot_id}" if shot_id is not None else "对应片段"
                    generated.append(f"{target}建议{action}: {reason}")

        return VideoDiagnosisService._dedupe_keep_order(generated)[:6]

    @staticmethod
    def _extract_dimension_confidence(dim_result: Dict[str, Any]) -> float:
        """估算维度评分置信度，允许分析器未来直接传入 confidence"""
        raw_confidence = dim_result.get("confidence")
        if isinstance(raw_confidence, (int, float)):
            confidence = float(raw_confidence)
            if confidence > 1:
                confidence = confidence / 100
            return max(0.0, min(1.0, confidence))

        details = dim_result.get("details") or {}
        description = str(dim_result.get("description", ""))
        if isinstance(details, dict) and details.get("error"):
            return 0.35
        if "降级" in description or "异常" in description:
            return 0.35
        if dim_result.get("status") == "pass" and float(dim_result.get("score", 0) or 0) >= 85:
            return 0.8
        if dim_result.get("status") == "error":
            return 0.65
        return 0.7

    @staticmethod
    def _normalize_string_list(value: Any) -> List[str]:
        """把 prompt/分析器返回的 str/list 等值统一成字符串列表"""
        if value is None:
            return []
        if isinstance(value, str):
            return [value.strip()] if value.strip() else []
        if isinstance(value, (list, tuple, set)):
            result = []
            for item in value:
                if item is None:
                    continue
                text = str(item).strip()
                if text:
                    result.append(text)
            return result
        text = str(value).strip()
        return [text] if text else []

    @staticmethod
    def _dedupe_keep_order(items: List[str]) -> List[str]:
        """去重并保留原始顺序"""
        seen = set()
        result = []
        for item in items:
            text = str(item).strip()
            if not text or text in seen:
                continue
            seen.add(text)
            result.append(text)
        return result

    @staticmethod
    def _calculate_overall_grade(
        dimension_scores: List[DimensionScore],
    ) -> Literal["A", "B", "C", "D"]:
        """根据各维度评分计算总体评级"""
        if not dimension_scores:
            return "B"

        avg_score = sum(s.score for s in dimension_scores) / len(dimension_scores)

        if avg_score >= 85:
            return "A"
        elif avg_score >= 70:
            return "B"
        elif avg_score >= 55:
            return "C"
        else:
            return "D"

    def _generate_summary(
        self,
        duration: float,
        total_shots: int,
        dimension_scores: List[DimensionScore],
        shot_details: List[ShotInfo],
    ) -> str:
        """生成诊断总结文案

        简化版: 使用模板生成。
        完整版: 可调用LLM生成(使用 summary_generation.txt prompt)。
        """
        good_dims = [s for s in dimension_scores if s.status == "pass"]
        bad_dims = [s for s in dimension_scores if s.status == "error"]

        grade = self._calculate_overall_grade(dimension_scores)

        summary_parts = [
            f"本视频总时长{duration:.0f}秒,共{total_shots}个镜头。",
            f"整体评级为{grade}级。",
        ]

        if good_dims:
            dims_str = ", ".join(
                [self._translate_dim_name(d.dimension) for d in good_dims]
            )
            summary_parts.append(f"在{dims_str}方面表现良好。")

        if bad_dims:
            dims_str = ", ".join(
                [self._translate_dim_name(d.dimension) for d in bad_dims]
            )
            summary_parts.append(f"需要重点改进{dims_str}方面的问题。")

        return " ".join(summary_parts)

    @staticmethod
    def _translate_dim_name(dim_name: str) -> str:
        """翻译维度名称为中文"""
        translations = {
            "consistency": "一致性",
            "coherence": "连贯度",
            "duplicate": "重复镜头",
            "rhythm": "节奏",
            "waste": "废片识别",
        }
        return translations.get(dim_name, dim_name)

    @staticmethod
    async def _save_results(task_id: str, diagnosis_result: DiagnosisResult):
        """保存诊断结果到JSON文件"""
        storage_dir = f"storage/tasks/{task_id}"
        os.makedirs(storage_dir, exist_ok=True)

        result_path = os.path.join(storage_dir, "diagnosis_result.json")

        with open(result_path, "w", encoding="utf-8") as f:
            f.write(json.dumps(
                VideoDiagnosisService._model_to_dict(diagnosis_result),
                indent=2,
                ensure_ascii=False,
                default=str,
            ))

        logger.info(f"诊断结果已保存: {result_path}")

    @staticmethod
    def _model_to_dict(model: DiagnosisResult) -> Dict[str, Any]:
        """兼容 Pydantic v1/v2 的模型序列化"""
        if hasattr(model, "model_dump"):
            return model.model_dump()
        return model.dict()
