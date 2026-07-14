from __future__ import annotations

import math
import json
import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Sequence

from app.services.llm.migration_adapter import _run_async_safely
from app.services.llm.unified_service import UnifiedLLMService
from app.services.short_drama_narration_validation import (
    SubtitleCue,
    build_subtitle_index,
    count_narration_chars,
    max_narration_chars_for_duration,
    normalize_script_video_sources,
    parse_script_timestamp_range,
    validate_narration_script_items,
)

from .schema import (
    HighlightLevel,
    OverallScriptDiagnosis,
    ScriptDiagnosisResult,
    SegmentDiagnosis,
)


@dataclass(frozen=True)
class ContentProfile:
    content_type: str
    display_name: str
    score_label: str
    keywords: Dict[str, int]
    ideal_original_sound_max: float = 10.0
    matched_bonus: int = 6
    original_sound_bonus: int = 10


CONTENT_PROFILES: Dict[str, ContentProfile] = {
    "short_drama_narration": ContentProfile(
        content_type="short_drama_narration",
        display_name="短剧解说",
        score_label="高燃",
        keywords={
            "冲突": 10, "误会": 8, "羞辱": 10, "证据": 12, "真相": 12,
            "反转": 14, "身份": 12, "揭露": 12, "震惊": 12, "反派": 10,
            "慌": 8, "崩溃": 10, "打脸": 14, "危机": 10, "悬念": 10,
            "爆发": 10, "怒": 8, "哭": 8, "跪": 8,
        },
    ),
    "film_tv_narration": ContentProfile(
        content_type="film_tv_narration",
        display_name="影视解说",
        score_label="剧情价值",
        keywords={
            "关键": 10, "剧情": 8, "人物": 6, "动机": 12, "真相": 12,
            "线索": 12, "危机": 10, "转折": 12, "反转": 10, "名场面": 12,
            "选择": 8, "冲突": 8, "悬念": 10, "信息": 8, "原因": 8,
        },
        ideal_original_sound_max=12.0,
    ),
    "short_drama_mix": ContentProfile(
        content_type="short_drama_mix",
        display_name="短剧混剪",
        score_label="混剪价值",
        keywords={
            "爽点": 14, "高燃": 14, "打脸": 14, "关键对白": 12, "原声": 8,
            "冲突": 10, "反转": 12, "身份": 10, "震惊": 10, "情绪爆发": 12,
            "爆发": 10, "证据": 10, "反派": 8, "慌": 8, "名场面": 10,
        },
        matched_bonus=8,
        original_sound_bonus=14,
    ),
    "documentary": ContentProfile(
        content_type="documentary",
        display_name="纪录片/画面解说",
        score_label="信息价值",
        keywords={
            "真实": 12, "现场": 12, "记录": 10, "历史": 10, "数据": 12,
            "事实": 12, "环境": 8, "变化": 8, "过程": 8, "原因": 10,
            "背景": 8, "细节": 8, "观察": 8, "解释": 8, "证据": 8,
        },
        ideal_original_sound_max=15.0,
        matched_bonus=8,
        original_sound_bonus=4,
    ),
}


CONTENT_TYPE_ALIASES = {
    "short_drama": "short_drama_narration",
    "film_tv": "film_tv_narration",
    "short": "short_drama_mix",
    "auto": "documentary",
}


class ScriptDiagnosisService:
    """基于剪辑脚本 JSON 的分镜诊断。

    该服务诊断的是已经拆分好的脚本片段，而不是完整成片。评分重点是单个
    分镜在原视频中的高价值程度、原声占比目标，以及用户可手动执行的调整建议。
    """

    def diagnose(
        self,
        items: Sequence[Dict[str, Any]],
        subtitle_content: str = "",
        video_paths: Iterable[str] | None = None,
        original_sound_ratio: int = 30,
        content_type: str = "short_drama",
        plot_analysis: str = "",
        narration_copy: str = "",
        analysis_mode: str = "llm",
        llm_batch_size: int = 30,
    ) -> ScriptDiagnosisResult:
        profile = self._resolve_profile(content_type)
        normalized_items = normalize_script_video_sources(items or [], video_paths)
        subtitle_index = build_subtitle_index(subtitle_content or "", video_paths)
        validation = validate_narration_script_items(
            normalized_items,
            subtitle_index,
            video_paths,
        )

        overall = self._build_overall(normalized_items, original_sound_ratio)
        segments = [
            self._diagnose_segment(
                item=item,
                subtitle_index=subtitle_index,
                overall=overall,
                profile=profile,
            )
            for item in normalized_items
            if isinstance(item, dict)
        ]
        warnings: List[str] = []

        if str(analysis_mode or "").lower() in {"llm", "default"} and segments:
            try:
                segments = self._apply_llm_analysis(
                    items=normalized_items,
                    segments=segments,
                    subtitle_index=subtitle_index,
                    overall=overall,
                    profile=profile,
                    plot_analysis=plot_analysis,
                    narration_copy=narration_copy,
                    llm_batch_size=llm_batch_size,
                )
            except Exception as exc:
                warnings.append(f"LLM 分镜分析失败，已降级为规则分析: {exc}")

        return ScriptDiagnosisResult(
            overall=overall,
            segments=segments,
            errors=validation.errors,
            warnings=warnings,
        )

    def _build_overall(
        self,
        items: Sequence[Dict[str, Any]],
        target_ratio: int,
    ) -> OverallScriptDiagnosis:
        total = len([item for item in items if isinstance(item, dict)])
        current_count = sum(1 for item in items if self._ost(item) == 1)
        target_ratio = max(0, min(100, int(target_ratio or 0)))
        target_count = int(math.floor(total * target_ratio / 100 + 0.5))
        current_ratio = round((current_count / total * 100), 1) if total else 0.0
        gap = target_count - current_count

        if gap > 0:
            status = "low"
            suggestions = [
                f"目标原声占比 {target_ratio}%，当前 {current_count}/{total}={current_ratio:.1f}%，建议增加 {gap} 个高燃原声片段。"
            ]
        elif gap < 0:
            status = "high"
            suggestions = [
                f"目标原声占比 {target_ratio}%，当前 {current_count}/{total}={current_ratio:.1f}%，建议减少 {abs(gap)} 个普通原声片段或改为解说承接。"
            ]
        else:
            status = "ok"
            suggestions = [f"当前原声片段数量与 {target_ratio}% 目标基本一致。"]

        return OverallScriptDiagnosis(
            total_segments=total,
            target_original_sound_ratio=target_ratio,
            current_original_sound_ratio=current_ratio,
            target_original_sound_count=target_count,
            current_original_sound_count=current_count,
            ratio_status=status,
            ratio_gap_count=gap,
            ratio_adjustment_suggestions=suggestions,
        )

    def _diagnose_segment(
        self,
        item: Dict[str, Any],
        subtitle_index: Sequence[SubtitleCue],
        overall: OverallScriptDiagnosis,
        profile: ContentProfile,
    ) -> SegmentDiagnosis:
        item_id = item.get("_id")
        evidence: List[str] = []
        suggestions: List[Dict[str, Any]] = []
        penalties = 0

        try:
            start_ms, end_ms, normalized_timestamp = parse_script_timestamp_range(item.get("timestamp", ""))
            duration = max(0.0, (end_ms - start_ms) / 1000)
        except ValueError as exc:
            return SegmentDiagnosis(
                item_id=item_id,
                status="error",
                score=0,
                highlight_score=0,
                highlight_level="low",
                decision="fix_timestamp",
                reason=f"时间戳不可用: {exc}",
                evidence=[str(exc)],
                suggestions=[{"type": "fix_timestamp", "reason": "请先修正 timestamp 后再判断分镜价值"}],
                ratio_impact=self._ratio_impact(overall),
                confidence=0.9,
            )

        subtitle_text = self._subtitle_text_for_item(item, subtitle_index, start_ms, end_ms)
        highlight_score = self._calculate_highlight_score(item, subtitle_text, duration, profile)
        highlight_level = self._highlight_level(highlight_score)
        ost = self._ost(item)

        if subtitle_text:
            evidence.append(f"原字幕: {subtitle_text[:120]}")

        if ost == 0:
            narration_chars = count_narration_chars(item.get("narration", ""))
            max_chars = max_narration_chars_for_duration(start_ms, end_ms)
            if narration_chars > max_chars:
                needed_seconds = narration_chars / 5.0
                evidence.append(
                    f"解说过密: {narration_chars} 字约需 {needed_seconds:.1f} 秒，当前画面 {duration:.1f} 秒"
                )
                suggestions.append({
                    "type": "extend_or_shorten_narration",
                    "reason": "当前画面承载不了这段解说，建议拉长分镜或压缩解说文案",
                    "target_min_duration": round(needed_seconds, 1),
                    "max_suggested_chars": max_chars,
                })
                penalties += 22
        elif ost == 1:
            if duration < 3:
                evidence.append(f"原声片段偏短: 当前 {duration:.1f} 秒，可能无法承载完整对白或情绪")
                suggestions.append({
                    "type": "extend_original_sound",
                    "reason": "原声片段通常建议至少 3 秒，避免只截到孤立半句对白",
                })
                penalties += 12
            elif duration > profile.ideal_original_sound_max:
                evidence.append(f"原声片段偏长: 当前 {duration:.1f} 秒，可能包含无效铺垫")
                suggestions.append({
                    "type": "trim_original_sound",
                    "reason": f"{profile.display_name}原声片段建议优先保留{profile.score_label}最高的部分，去掉弱信息铺垫",
                })
                penalties += 8

        self._append_ratio_suggestions(item, overall, highlight_score, suggestions, evidence)

        score = max(0, min(100, int(round(highlight_score - penalties))))
        status = self._status(score, suggestions)
        decision = self._decision(item, status, highlight_score, overall, suggestions)
        reason = self._reason(status, decision, highlight_score, highlight_level, suggestions, profile)

        return SegmentDiagnosis(
            item_id=item_id,
            status=status,
            score=score,
            highlight_score=highlight_score,
            highlight_level=highlight_level,
            decision=decision,
            reason=reason,
            evidence=self._dedupe(evidence),
            suggestions=suggestions,
            ratio_impact=self._ratio_impact(overall, item),
            confidence=0.72,
            needs_visual_review=self._needs_visual_review(status, score, highlight_score, suggestions),
        )

    def _apply_llm_analysis(
        self,
        items: Sequence[Dict[str, Any]],
        segments: Sequence[SegmentDiagnosis],
        subtitle_index: Sequence[SubtitleCue],
        overall: OverallScriptDiagnosis,
        profile: ContentProfile,
        plot_analysis: str,
        narration_copy: str,
        llm_batch_size: int,
    ) -> List[SegmentDiagnosis]:
        segment_by_id = {str(segment.item_id): segment for segment in segments}
        item_by_id = {str(item.get("_id")): item for item in items if isinstance(item, dict)}
        merged_segments = list(segments)
        llm_batch_size = max(1, min(50, int(llm_batch_size or 30)))

        item_batches = [
            [item for item in items[index:index + llm_batch_size] if isinstance(item, dict)]
            for index in range(0, len(items), llm_batch_size)
        ]
        for batch_index, batch in enumerate(item_batches, start=1):
            if not batch:
                continue
            prompt = self._build_llm_prompt(
                batch=batch,
                subtitle_index=subtitle_index,
                overall=overall,
                profile=profile,
                plot_analysis=plot_analysis,
                narration_copy=narration_copy,
                batch_index=batch_index,
                batch_count=len(item_batches),
            )
            response_text = _run_async_safely(
                UnifiedLLMService.generate_text,
                prompt=prompt,
                system_prompt=self._llm_system_prompt(profile),
                temperature=0.2,
                response_format="json",
            )
            parsed = self._parse_llm_response(response_text)
            for payload in parsed.get("segments", []):
                item_id = str(payload.get("item_id", ""))
                base = segment_by_id.get(item_id)
                item = item_by_id.get(item_id)
                if base is None or item is None:
                    continue
                updated = self._merge_llm_segment(base, item, payload, overall)
                segment_by_id[item_id] = updated

        return [segment_by_id.get(str(segment.item_id), segment) for segment in merged_segments]

    def _build_llm_prompt(
        self,
        batch: Sequence[Dict[str, Any]],
        subtitle_index: Sequence[SubtitleCue],
        overall: OverallScriptDiagnosis,
        profile: ContentProfile,
        plot_analysis: str,
        narration_copy: str,
        batch_index: int,
        batch_count: int,
    ) -> str:
        compact_segments = []
        for item in batch:
            try:
                start_ms, end_ms, _ = parse_script_timestamp_range(item.get("timestamp", ""))
                duration = round(max(0.0, (end_ms - start_ms) / 1000), 1)
                subtitle_text = self._subtitle_text_for_item(item, subtitle_index, start_ms, end_ms)
            except ValueError:
                duration = 0.0
                subtitle_text = ""
            compact_segments.append({
                "item_id": item.get("_id"),
                "video_id": item.get("video_id"),
                "timestamp": item.get("timestamp"),
                "duration_seconds": duration,
                "OST": self._ost(item),
                "picture": self._clip_text(item.get("picture"), 160),
                "narration": self._clip_text(item.get("narration"), 180),
                "subtitle": self._clip_text(subtitle_text, 260),
            })

        payload = {
            "analysis_goal": "评估当前拆分后的分镜是否值得保留、是否需要手动调整，以及如何调整。",
            "content_type": profile.display_name,
            "score_label": profile.score_label,
            "batch": {"index": batch_index, "count": batch_count},
            "original_sound_target": {
                "target_ratio": overall.target_original_sound_ratio,
                "current_ratio": overall.current_original_sound_ratio,
                "current_count": overall.current_original_sound_count,
                "target_count": overall.target_original_sound_count,
                "status": overall.ratio_status,
            },
            "global_context": {
                "plot_analysis": self._clip_text(plot_analysis, 3500),
                "narration_copy": self._clip_text(narration_copy, 2500),
            },
            "segments": compact_segments,
        }
        return (
            "请基于全局剧情理解和当前分镜脚本，批量评估每个分镜。\n"
            "重点不是完整成片诊断，而是判断拆分后的分镜是否合理、是否保留、如何手动调整。\n"
            "不要使用画面关键帧；如果仅凭文本无法确认画面表现，请将 needs_visual_review 设为 true。\n"
            "请严格返回 JSON，格式为: {\"segments\": [...]}。每个 segment 字段包括: "
            "item_id, highlight_score, score, status, decision, reason, evidence, suggestions, confidence, needs_visual_review。\n"
            "score/highlight_score 为 0-100 整数；status 只能是 keep/adjust/delete；"
            "decision 建议使用 keep_as_original_sound/keep_as_narration/adjust/delete；"
            "suggestions 是对象数组，每个对象包含 type 和 reason。\n\n"
            f"{json.dumps(payload, ensure_ascii=False, indent=2)}"
        )

    @staticmethod
    def _llm_system_prompt(profile: ContentProfile) -> str:
        return (
            "你是一个短视频分镜脚本评估专家。"
            f"当前创作类型是{profile.display_name}，评分重点是{profile.score_label}、剧情价值、解说承载、原声保留价值和剪辑可用性。"
            "你只能依据输入的剧情理解、解说文案、字幕和分镜文本判断；不要虚构画面细节。"
            "输出必须是可解析 JSON。"
        )

    @staticmethod
    def _parse_llm_response(response_text: str) -> Dict[str, Any]:
        text = str(response_text or "").strip()
        if not text:
            return {"segments": []}
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            code_block = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
            if code_block:
                parsed = json.loads(code_block.group(1))
            else:
                match = re.search(r"\{.*\}", text, re.DOTALL)
                parsed = json.loads(match.group()) if match else {"segments": []}
        if isinstance(parsed, list):
            return {"segments": parsed}
        if not isinstance(parsed, dict):
            return {"segments": []}
        segments = parsed.get("segments")
        if not isinstance(segments, list):
            parsed["segments"] = []
        return parsed

    def _merge_llm_segment(
        self,
        base: SegmentDiagnosis,
        item: Dict[str, Any],
        payload: Dict[str, Any],
        overall: OverallScriptDiagnosis,
    ) -> SegmentDiagnosis:
        suggestions = payload.get("suggestions")
        if not isinstance(suggestions, list):
            suggestions = []
        evidence = payload.get("evidence")
        if not isinstance(evidence, list):
            evidence = []

        combined_suggestions = self._merge_suggestions(base.suggestions, suggestions)
        highlight_score = self._bounded_int(payload.get("highlight_score"), base.highlight_score)
        score = self._bounded_int(payload.get("score"), base.score)
        if any(s.get("type") in {"change_ost", "fix_timestamp"} for s in combined_suggestions):
            status = "adjust"
            decision = self._decision(item, status, highlight_score, overall, combined_suggestions)
        else:
            status = self._safe_status(payload.get("status"), self._status(score, combined_suggestions))
            decision = str(payload.get("decision") or self._decision(item, status, highlight_score, overall, combined_suggestions))
        confidence = self._bounded_float(payload.get("confidence"), base.confidence)
        needs_visual_review = bool(payload.get("needs_visual_review")) or self._needs_visual_review(
            status,
            score,
            highlight_score,
            combined_suggestions,
            confidence,
        )

        return SegmentDiagnosis(
            item_id=base.item_id,
            status=status,
            score=score,
            highlight_score=highlight_score,
            highlight_level=self._highlight_level(highlight_score),
            decision=decision,
            reason=str(payload.get("reason") or base.reason),
            evidence=self._dedupe([str(item) for item in evidence] + base.evidence),
            suggestions=combined_suggestions,
            ratio_impact=base.ratio_impact,
            confidence=confidence,
            needs_visual_review=needs_visual_review,
        )

    def _calculate_highlight_score(
        self,
        item: Dict[str, Any],
        subtitle_text: str,
        duration: float,
        profile: ContentProfile,
    ) -> int:
        text = " ".join(
            [
                str(item.get("picture") or ""),
                str(item.get("narration") or ""),
                subtitle_text,
            ]
        )
        score = 35
        matched = 0
        for keyword, weight in profile.keywords.items():
            if keyword in text:
                score += weight
                matched += 1

        if self._ost(item) == 1 and matched:
            score += profile.original_sound_bonus
        if matched >= 2:
            score += profile.matched_bonus
        if 3 <= duration <= 10:
            score += 8
        elif duration < 2:
            score -= 15
        elif duration > 20:
            score -= 10

        return max(0, min(100, score))

    def _append_ratio_suggestions(
        self,
        item: Dict[str, Any],
        overall: OverallScriptDiagnosis,
        highlight_score: int,
        suggestions: List[Dict[str, Any]],
        evidence: List[str],
    ) -> None:
        ost = self._ost(item)
        if overall.target_original_sound_ratio == 0 and ost == 1:
            evidence.append("目标原声占比为 0%，当前片段仍是 OST=1")
            suggestions.append({
                "type": "change_ost",
                "to": 0,
                "reason": "用户目标是不保留原声，建议改为解说画面或删除该原声片段",
            })
            return

        if overall.ratio_status == "low" and ost == 0 and highlight_score >= 75:
            evidence.append("当前全局原声占比低于目标，且该片段高燃价值较高")
            suggestions.append({
                "type": "change_ost",
                "to": 1,
                "reason": "该片段具备高燃/关键对白潜力，可优先改为原声以接近目标占比",
            })
        elif overall.ratio_status == "high" and ost == 1 and highlight_score < 70:
            evidence.append("当前全局原声占比高于目标，且该原声片段高燃价值不突出")
            suggestions.append({
                "type": "change_ost",
                "to": 0,
                "reason": "为降低原声占比，建议把普通原声片段改为解说承接或删除",
            })

    @staticmethod
    def _subtitle_text_for_item(
        item: Dict[str, Any],
        subtitle_index: Sequence[SubtitleCue],
        start_ms: int,
        end_ms: int,
    ) -> str:
        video_id = item.get("video_id")
        try:
            video_id = int(video_id)
        except (TypeError, ValueError):
            return ""

        matched = [
            cue.text
            for cue in subtitle_index
            if cue.video_id == video_id and start_ms < cue.end_ms and end_ms > cue.start_ms
        ]
        return " ".join(text for text in matched if text).strip()

    @staticmethod
    def _highlight_level(score: int) -> HighlightLevel:
        if score >= 75:
            return "high"
        if score >= 50:
            return "medium"
        return "low"

    @staticmethod
    def _status(score: int, suggestions: Sequence[Dict[str, Any]]) -> str:
        if any(s.get("type") in {"change_ost", "fix_timestamp"} for s in suggestions):
            return "adjust"
        if score < 40:
            return "delete"
        if suggestions or score < 65:
            return "adjust"
        return "keep"

    def _decision(
        self,
        item: Dict[str, Any],
        status: str,
        highlight_score: int,
        overall: OverallScriptDiagnosis,
        suggestions: Sequence[Dict[str, Any]],
    ) -> str:
        if status == "delete":
            return "delete"
        if any(s.get("type") == "change_ost" and s.get("to") == 0 for s in suggestions):
            return "keep_as_narration"
        if any(s.get("type") == "change_ost" and s.get("to") == 1 for s in suggestions):
            return "keep_as_original_sound"
        if status == "adjust":
            return "adjust"
        if self._ost(item) == 1 and highlight_score >= 70:
            return "keep_as_original_sound"
        if self._ost(item) == 0:
            return "keep_as_narration"
        return "keep"

    @staticmethod
    def _reason(
        status: str,
        decision: str,
        highlight_score: int,
        highlight_level: str,
        suggestions: Sequence[Dict[str, Any]],
        profile: ContentProfile,
    ) -> str:
        if suggestions:
            return str(suggestions[0].get("reason") or "该分镜需要人工调整")
        if decision == "keep_as_original_sound":
            return f"该片段{profile.score_label}等级为 {highlight_level}，原视频价值较高，适合保留原声"
        if decision == "keep_as_narration":
            return f"该片段{profile.score_label}评分 {highlight_score}，适合作为解说承载画面"
        if status == "delete":
            return f"该片段{profile.score_label}较低，建议考虑删除或替换"
        if status == "adjust":
            if highlight_score < 50:
                return f"该片段{profile.score_label}评分仅 {highlight_score}，缺少明显符合「{profile.display_name}」的高价值信号，建议人工复核是否保留"
            return f"该片段{profile.score_label}评分 {highlight_score}，价值中等但未命中明确调整规则，建议人工复核时间范围和用途"
        return "当前分镜基本合理"

    @staticmethod
    def _needs_visual_review(
        status: str,
        score: int,
        highlight_score: int,
        suggestions: Sequence[Dict[str, Any]],
        confidence: float = 0.72,
    ) -> bool:
        if any(s.get("type") in {"visual_review", "vlm_review", "keyframe_review"} for s in suggestions):
            return True
        if confidence < 0.65:
            return True
        if status == "delete" and highlight_score >= 55:
            return True
        return 40 <= score <= 65 and highlight_score >= 50

    @staticmethod
    def _resolve_profile(content_type: str | None) -> ContentProfile:
        normalized = CONTENT_TYPE_ALIASES.get(str(content_type or ""), str(content_type or ""))
        return CONTENT_PROFILES.get(normalized, CONTENT_PROFILES["short_drama_narration"])

    @staticmethod
    def _ratio_impact(
        overall: OverallScriptDiagnosis,
        item: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        impact = {
            "target_original_sound_ratio": overall.target_original_sound_ratio,
            "current_original_sound_ratio": overall.current_original_sound_ratio,
            "current_original_sound_count": overall.current_original_sound_count,
            "target_original_sound_count": overall.target_original_sound_count,
        }
        if item is not None:
            impact["item_ost"] = ScriptDiagnosisService._ost(item)
        return impact

    @staticmethod
    def _ost(item: Dict[str, Any]) -> int | None:
        try:
            return int(item.get("OST"))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _dedupe(items: Sequence[str]) -> List[str]:
        result: List[str] = []
        seen = set()
        for item in items:
            text = re.sub(r"\s+", " ", str(item or "")).strip()
            if not text or text in seen:
                continue
            seen.add(text)
            result.append(text)
        return result

    @staticmethod
    def _merge_suggestions(
        base_suggestions: Sequence[Dict[str, Any]],
        llm_suggestions: Sequence[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        result: List[Dict[str, Any]] = []
        seen = set()
        for suggestion in list(base_suggestions or []) + list(llm_suggestions or []):
            if not isinstance(suggestion, dict):
                continue
            key = (
                str(suggestion.get("type") or ""),
                str(suggestion.get("to") or ""),
                str(suggestion.get("reason") or ""),
            )
            if key in seen:
                continue
            seen.add(key)
            result.append(suggestion)
        return result

    @staticmethod
    def _bounded_int(value: Any, default: int) -> int:
        try:
            parsed = int(round(float(value)))
        except (TypeError, ValueError):
            parsed = int(default)
        return max(0, min(100, parsed))

    @staticmethod
    def _bounded_float(value: Any, default: float) -> float:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            parsed = float(default)
        return max(0.0, min(1.0, parsed))

    @staticmethod
    def _safe_status(value: Any, default: str) -> str:
        status = str(value or "").strip()
        if status in {"keep", "adjust", "delete", "error"}:
            return status
        return default

    @staticmethod
    def _clip_text(value: Any, limit: int) -> str:
        text = re.sub(r"\s+", " ", str(value or "")).strip()
        if len(text) <= limit:
            return text
        return text[:limit].rstrip() + "..."
