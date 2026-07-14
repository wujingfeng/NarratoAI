"""
视频质量分析器 - 5维度质量评估

提供以下维度的视频质量评估:
1. ConsistencyChecker  - 一致性检查(色调/构图/人物形象)
2. CoherenceChecker    - 连贯度评估(转场自然度/叙事逻辑)
3. DuplicateDetector   - 重复镜头检测(pHash + VLM双重验证)
4. RhythmAnalyzer      - 节奏分析(镜头时长分布/节奏稳定性)
5. WasteClipDetector   - 废片识别(黑屏/静音/无效内容)
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Tuple
import asyncio
import hashlib
import json
import math
import os
import re
import subprocess

from loguru import logger

from app.services.llm.unified_service import UnifiedLLMService
from app.services.prompts import PromptManager
from app.services.video_diagnosis.profiles import AnalysisMode, VideoTypeProfile, get_video_type_profile


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def _load_prompt(name: str, parameters: Optional[Dict[str, Any]] = None) -> str:
    """
    加载 video_diagnosis 类别下的 Prompt 模板。

    优先使用 PromptManager（已注册），失败时回退到直接读取 txt 文件。
    """
    try:
        return PromptManager.get_prompt(
            category="video_diagnosis",
            name=name,
            parameters=parameters or {},
        )
    except Exception:
        # Fallback: 直接读取模板文件
        template_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "prompts", "video_diagnosis", f"{name}.txt",
        )
        if os.path.exists(template_path):
            with open(template_path, "r", encoding="utf-8") as f:
                template = f.read()
            # 简单替换 {{key}} 或 {key}
            if parameters:
                for k, v in parameters.items():
                    template = template.replace("{{" + k + "}}", str(v))
                    template = template.replace("{" + k + "}", str(v))
            return template
        logger.warning(f"Prompt 模板 '{name}' 未找到，使用空模板")
        return ""


def _robust_json_parse(text: str) -> Dict[str, Any]:
    """
    从 LLM 返回的文本中 robust 地提取 JSON 对象。

    LLM 可能在 JSON 前后附加说明文字，此函数尝试多种策略提取。
    """
    if not text:
        return {}

    # 策略 1: 直接解析
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        pass

    # 策略 2: 提取 ```json ... ``` 代码块
    code_block = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if code_block:
        try:
            return json.loads(code_block.group(1))
        except (json.JSONDecodeError, TypeError):
            pass

    # 策略 3: 找到第一个 { 和最后一个 } 之间的内容
    first_brace = text.find("{")
    last_brace = text.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        try:
            return json.loads(text[first_brace:last_brace + 1])
        except (json.JSONDecodeError, TypeError):
            pass

    # 策略 4: 找到第一个 [ 和最后一个 ] (数组格式)
    first_bracket = text.find("[")
    last_bracket = text.rfind("]")
    if first_bracket != -1 and last_bracket != -1 and last_bracket > first_bracket:
        try:
            parsed = json.loads(text[first_bracket:last_bracket + 1])
            return {"items": parsed}
        except (json.JSONDecodeError, TypeError):
            pass

    logger.warning(f"无法从 LLM 返回文本中解析 JSON，原文前200字符: {text[:200]}")
    return {}


def _cache_key(*args: str) -> str:
    """基于输入参数生成缓存 key（MD5 hash）"""
    raw = "|".join(str(a) for a in args)
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def _determine_status(score: int, warning_threshold: int = 60,
                      error_threshold: int = 40) -> str:
    """根据分数判定 status"""
    if score >= warning_threshold:
        return "pass"
    elif score >= error_threshold:
        return "warning"
    else:
        return "error"


# ---------------------------------------------------------------------------
# 基类
# ---------------------------------------------------------------------------

class DimensionAnalyzer(ABC):
    """维度分析器基类"""

    def __init__(self, llm_timeout: int = 30, profile: VideoTypeProfile | None = None):
        """
        Args:
            llm_timeout: LLM 调用超时秒数
        """
        self._cache: Dict[str, Any] = {}
        self._llm_timeout = llm_timeout
        self.profile = profile or get_video_type_profile()

    @abstractmethod
    async def analyze(self, **kwargs) -> Dict[str, Any]:
        """执行分析，返回结构化结果"""
        ...

    async def _call_llm_with_timeout(self, coro) -> Any:
        """带超时的 LLM 调用"""
        try:
            return await asyncio.wait_for(coro, timeout=self._llm_timeout)
        except asyncio.TimeoutError:
            logger.warning(f"LLM 调用超时 ({self._llm_timeout}s)")
            return None
        except Exception as e:
            logger.error(f"LLM 调用失败: {e}")
            return None


# ---------------------------------------------------------------------------
# 1. ConsistencyChecker - 一致性检查
# ---------------------------------------------------------------------------

class ConsistencyChecker(DimensionAnalyzer):
    """
    使用 VLM 分析所有关键帧的色调、构图、人物形象一致性。

    将所有关键帧分批（每批 10 张）发送给 VLM，汇总各批次结果后
    给出整体一致性评分。
    """

    BATCH_SIZE = 10

    async def analyze(self, keyframe_paths: List[str], **kwargs) -> Dict[str, Any]:
        """
        分析视频的一致性。

        Args:
            keyframe_paths: 所有关键帧路径列表

        Returns:
            {
                "status": "pass/warning/error",
                "score": 0-100,
                "description": "简要说明",
                "inconsistent_shots": [镜头编号列表],
                "details": {...}
            }
        """
        if not keyframe_paths:
            return self._empty_result("无关键帧可供分析")

        cache_k = _cache_key("consistency", *keyframe_paths)
        if cache_k in self._cache:
            return self._cache[cache_k]

        try:
            # 分批发送给 VLM
            analysis_paths = self._select_keyframes_for_consistency(keyframe_paths)
            batch_results = []
            for i in range(0, len(analysis_paths), self.BATCH_SIZE):
                batch = analysis_paths[i:i + self.BATCH_SIZE]
                batch_idx = i // self.BATCH_SIZE + 1
                prompt = _load_prompt("consistency_check", parameters={
                    "num_shots": len(keyframe_paths),
                    "batch_index": batch_idx,
                    "total_batches": math.ceil(len(analysis_paths) / self.BATCH_SIZE),
                    "video_type_context": self.profile.prompt_context,
                })

                result_text = await self._call_llm_with_timeout(
                    UnifiedLLMService.analyze_images(
                        images=batch, prompt=prompt, batch_size=self.BATCH_SIZE,
                    )
                )

                if result_text:
                    # analyze_images 返回 List[str]，取最后一个汇总结果
                    text = result_text[-1] if isinstance(result_text, list) else str(result_text)
                    parsed = _robust_json_parse(text)
                    if parsed:
                        batch_results.append(parsed)

            # 汇总各批次结果
            result = self._aggregate(batch_results, len(keyframe_paths))

        except Exception as e:
            logger.error(f"一致性检查失败: {e}")
            result = self._degraded_result(str(e))

        self._cache[cache_k] = result
        return result

    # -- 内部方法 --

    def _select_keyframes_for_consistency(self, keyframe_paths: List[str]) -> List[str]:
        max_frames = self.profile.budget.max_keyframes
        if len(keyframe_paths) <= max_frames:
            return keyframe_paths
        step = len(keyframe_paths) / max_frames
        selected = []
        used = set()
        for i in range(max_frames):
            pos = min(int(i * step), len(keyframe_paths) - 1)
            if pos not in used:
                used.add(pos)
                selected.append(keyframe_paths[pos])
        return selected

    def _aggregate(self, batch_results: List[Dict], total_shots: int) -> Dict[str, Any]:
        """汇总多批次分析结果"""
        if not batch_results:
            return self._degraded_result("所有批次均未获得有效结果")

        all_inconsistent: List[int] = []
        scores: List[int] = []
        descriptions: List[str] = []

        for br in batch_results:
            scores.append(br.get("score", 50))
            descriptions.append(br.get("description", ""))
            inconsistent = br.get("inconsistent_shots", [])
            if isinstance(inconsistent, list):
                all_inconsistent.extend(inconsistent)

        avg_score = int(sum(scores) / len(scores)) if scores else 50
        status = _determine_status(avg_score)

        return {
            "status": status,
            "score": avg_score,
            "description": "；".join(d for d in descriptions if d)[:300],
            "inconsistent_shots": sorted(set(all_inconsistent)),
            "details": {
                "total_shots": total_shots,
                "batch_count": len(batch_results),
                "batch_scores": scores,
            },
        }

    @staticmethod
    def _empty_result(reason: str) -> Dict[str, Any]:
        return {
            "status": "pass", "score": 100,
            "description": reason,
            "inconsistent_shots": [], "details": {},
        }

    @staticmethod
    def _degraded_result(error: str) -> Dict[str, Any]:
        return {
            "status": "warning", "score": 50,
            "description": f"一致性分析降级（LLM 调用异常）: {error}",
            "inconsistent_shots": [],
            "details": {"error": error},
        }


# ---------------------------------------------------------------------------
# 2. CoherenceChecker - 连贯度评估
# ---------------------------------------------------------------------------

class CoherenceChecker(DimensionAnalyzer):
    """
    评估相邻镜头之间的转场自然度和叙事逻辑。

    将连续 2-3 个镜头的关键帧组合发送给 VLM，同时统计镜头时长分布，
    标记异常（过短 <1s 或过长 >10s）。
    """

    WINDOW_SIZE = 3  # 每次发送给 VLM 的连续镜头数

    async def analyze(self, keyframe_paths: List[str],
                      shots: List[tuple], **kwargs) -> Dict[str, Any]:
        """
        分析镜头连贯性。

        Args:
            keyframe_paths: 关键帧路径列表
            shots: 镜头列表 [(start, end), ...]

        Returns:
            {
                "status": "pass/warning/error",
                "score": 0-100,
                "description": "简要说明",
                "issues": ["问题列表"],
                "problematic_transitions": [[shot_i, shot_j], ...],
                "suggestions": ["建议列表"]
            }
        """
        if not keyframe_paths or not shots:
            return self._empty_result("无关键帧或镜头数据")

        cache_k = _cache_key("coherence", *keyframe_paths)
        if cache_k in self._cache:
            return self._cache[cache_k]

        try:
            # 1. 统计时长异常
            duration_issues = self._check_duration_anomalies(shots)

            # 2. 滑动窗口发送给 VLM
            vlm_results = []
            transition_checks = 0
            for i in range(0, max(len(keyframe_paths) - 1, 0)):
                if transition_checks >= self.profile.budget.max_transition_checks:
                    break
                window = keyframe_paths[i:i + self.WINDOW_SIZE]
                if len(window) < 2:
                    continue
                prompt = _load_prompt("coherence_check", parameters={
                    "window_start": i + 1,
                    "window_end": min(i + self.WINDOW_SIZE, len(keyframe_paths)),
                    "total_shots": len(keyframe_paths),
                    "num_consecutive": len(window),
                    "consecutive_shot_data": self._format_window_data(i, window, shots),
                    "video_type_context": self.profile.prompt_context,
                })
                transition_checks += 1
                result_text = await self._call_llm_with_timeout(
                    UnifiedLLMService.analyze_images(
                        images=window, prompt=prompt, batch_size=len(window),
                    )
                )
                if result_text:
                    text = result_text[-1] if isinstance(result_text, list) else str(result_text)
                    parsed = _robust_json_parse(text)
                    if parsed:
                        vlm_results.append(parsed)

            result = self._aggregate(vlm_results, duration_issues, len(shots))

        except Exception as e:
            logger.error(f"连贯度评估失败: {e}")
            result = self._degraded_result(str(e))

        self._cache[cache_k] = result
        return result

    # -- 内部方法 --

    def _check_duration_anomalies(self, shots: List[tuple]) -> List[str]:
        """检查镜头时长异常"""
        issues: List[str] = []
        for idx, (start, end) in enumerate(shots):
            duration = end - start
            shot_num = idx + 1
            if duration < self.profile.rhythm.short_shot_threshold:
                issues.append(
                    f"镜头 {shot_num} 时长过短 "
                    f"({duration:.2f}s < {self.profile.rhythm.short_shot_threshold:.1f}s)"
                )
            elif duration > self.profile.rhythm.long_shot_threshold:
                issues.append(
                    f"镜头 {shot_num} 时长过长 "
                    f"({duration:.2f}s > {self.profile.rhythm.long_shot_threshold:.1f}s)"
                )
        return issues

    @staticmethod
    def _format_window_data(start_index: int, window: List[str], shots: List[tuple]) -> str:
        rows = []
        for offset, path in enumerate(window):
            shot_index = start_index + offset
            if shot_index < len(shots):
                start, end = shots[shot_index]
                rows.append(
                    f"镜头{shot_index + 1}: {start:.2f}s-{end:.2f}s, "
                    f"时长{end - start:.2f}s, 关键帧={path}"
                )
        return "\n".join(rows)

    @staticmethod
    def _aggregate(vlm_results: List[Dict], duration_issues: List[str],
                   total_shots: int) -> Dict[str, Any]:
        scores: List[int] = []
        all_issues: List[str] = list(duration_issues)
        problematic: List[List[int]] = []
        suggestions: List[str] = []

        for vr in vlm_results:
            scores.append(vr.get("score", 50))
            issues = vr.get("issues", [])
            if isinstance(issues, list):
                all_issues.extend(issues)
            pt = vr.get("problematic_transitions", [])
            if isinstance(pt, list):
                problematic.extend(pt)
            sug = vr.get("suggestions", [])
            if isinstance(sug, list):
                suggestions.extend(sug)

        avg_score = int(sum(scores) / len(scores)) if scores else 50
        # 每个时长 issue 扣分
        penalty = min(len(duration_issues) * 3, 30)
        avg_score = max(avg_score - penalty, 0)

        return {
            "status": _determine_status(avg_score),
            "score": avg_score,
            "description": f"共 {total_shots} 个镜头，发现 {len(all_issues)} 个问题",
            "issues": all_issues,
            "problematic_transitions": problematic,
            "suggestions": suggestions,
        }

    @staticmethod
    def _empty_result(reason: str) -> Dict[str, Any]:
        return {
            "status": "pass", "score": 100,
            "description": reason,
            "issues": [], "problematic_transitions": [], "suggestions": [],
        }

    @staticmethod
    def _degraded_result(error: str) -> Dict[str, Any]:
        return {
            "status": "warning", "score": 50,
            "description": f"连贯度评估降级: {error}",
            "issues": [], "problematic_transitions": [],
            "suggestions": [],
            "details": {"error": error},
        }


# ---------------------------------------------------------------------------
# 3. DuplicateDetector - 重复镜头检测
# ---------------------------------------------------------------------------

def calculate_phash(image_path: str) -> str:
    """计算单张图片的 pHash"""
    from PIL import Image
    import imagehash
    img = Image.open(image_path)
    return str(imagehash.phash(img))


def hamming_distance(hash1: str, hash2: str) -> int:
    """计算两个 pHash 的汉明距离"""
    import imagehash
    return imagehash.hex_to_hash(hash1) - imagehash.hex_to_hash(hash2)


class DuplicateDetector(DimensionAnalyzer):
    """
    使用 pHash + VLM 双重验证识别重复镜头。

    步骤:
    1. 使用 imagehash.phash() 计算所有关键帧的感知哈希
    2. 计算汉明距离，找出相似度 >85%（汉明距离 <5）的候选对
    3. 将候选对的 2 张关键帧发送给 VLM 确认是否为真重复
    """

    HAMMING_THRESHOLD = 5  # 汉明距离阈值，<5 视为候选重复

    async def analyze(self, keyframe_paths: List[str], **kwargs) -> Dict[str, Any]:
        """
        检测重复镜头。

        Returns:
            {
                "status": "pass/warning/error",
                "score": 0-100,
                "description": "简要说明",
                "duplicate_pairs": [[shot_i, shot_j, confidence], ...],
                "suggestions": ["保留镜头X,删除镜头Y"]
            }
        """
        if not keyframe_paths or len(keyframe_paths) < 2:
            return self._empty_result("关键帧数量不足，无法检测重复")

        cache_k = _cache_key("duplicate", *keyframe_paths)
        if cache_k in self._cache:
            return self._cache[cache_k]

        try:
            # 步骤 1: 计算 pHash
            hashes: List[str] = []
            for path in keyframe_paths:
                try:
                    h = calculate_phash(path)
                    hashes.append(h)
                except Exception as e:
                    logger.warning(f"计算 pHash 失败 ({path}): {e}")
                    hashes.append("")

            # 步骤 2: 找出候选重复对
            candidates: List[Tuple[int, int, int]] = []
            for i in range(len(hashes)):
                for j in range(i + 1, len(hashes)):
                    if not hashes[i] or not hashes[j]:
                        continue
                    dist = hamming_distance(hashes[i], hashes[j])
                    if dist < self.HAMMING_THRESHOLD:
                        candidates.append((i, j, dist))
            candidates = sorted(candidates, key=lambda item: item[2])[
                : self.profile.budget.max_duplicate_pairs
            ]

            if not candidates:
                result = {
                    "status": "pass", "score": 100,
                    "description": f"共 {len(keyframe_paths)} 个镜头，未检测到重复",
                    "duplicate_pairs": [], "suggestions": [],
                }
                self._cache[cache_k] = result
                return result

            # 步骤 3: VLM 确认
            confirmed_pairs = await self._vlm_verify(
                keyframe_paths, candidates,
            )

            result = self._build_result(confirmed_pairs, len(keyframe_paths))

        except Exception as e:
            logger.error(f"重复检测失败: {e}")
            result = self._degraded_result(str(e))

        self._cache[cache_k] = result
        return result

    async def _vlm_verify(
        self,
        keyframe_paths: List[str],
        candidates: List[Tuple[int, int, int]],
    ) -> List[Dict[str, Any]]:
        """将候选对发送给 VLM 确认"""
        confirmed: List[Dict[str, Any]] = []

        for idx_i, idx_j, dist in candidates:
            prompt = _load_prompt("duplicate_check", parameters={
                "shot_i": idx_i + 1,
                "shot_j": idx_j + 1,
                "hamming_distance": dist,
                "shot1_description": f"镜头{idx_i + 1}关键帧: {keyframe_paths[idx_i]}",
                "shot2_description": f"镜头{idx_j + 1}关键帧: {keyframe_paths[idx_j]}",
                "video_type_context": self.profile.prompt_context,
            })
            pair_paths = [keyframe_paths[idx_i], keyframe_paths[idx_j]]

            result_text = await self._call_llm_with_timeout(
                UnifiedLLMService.analyze_images(
                    images=pair_paths, prompt=prompt, batch_size=2,
                )
            )

            if result_text:
                text = result_text[-1] if isinstance(result_text, list) else str(result_text)
                parsed = _robust_json_parse(text)
                if parsed:
                    is_dup = parsed.get("is_duplicate", None)
                    confidence = parsed.get("confidence", 0.5)
                    # 如果 VLM 不确定且汉明距离很近，仍标记
                    if is_dup is True or (is_dup is None and dist <= 2):
                        confirmed.append({
                            "i": idx_i, "j": idx_j,
                            "confidence": confidence,
                            "reason": parsed.get("reason", ""),
                        })
            else:
                # VLM 调用失败，基于汉明距离做保守判断
                if dist <= 2:
                    confirmed.append({
                        "i": idx_i, "j": idx_j,
                        "confidence": 0.6,
                        "reason": f"汉明距离={dist}，VLM 调用失败，保守标记",
                    })

        return confirmed

    @staticmethod
    def _build_result(confirmed: List[Dict], total: int) -> Dict[str, Any]:
        dup_pairs = [[c["i"] + 1, c["j"] + 1, c["confidence"]] for c in confirmed]
        suggestions = []
        for c in confirmed:
            suggestions.append(
                f"保留镜头 {c['i'] + 1}，删除镜头 {c['j'] + 1}"
                + (f"（{c['reason']}）" if c.get("reason") else "")
            )

        # 评分: 每个重复对扣 15 分
        penalty = min(len(confirmed) * 15, 60)
        score = max(100 - penalty, 0)

        return {
            "status": _determine_status(score),
            "score": score,
            "description": f"共 {total} 个镜头，检测到 {len(confirmed)} 对重复",
            "duplicate_pairs": dup_pairs,
            "suggestions": suggestions,
        }

    @staticmethod
    def _empty_result(reason: str) -> Dict[str, Any]:
        return {
            "status": "pass", "score": 100,
            "description": reason,
            "duplicate_pairs": [], "suggestions": [],
        }

    @staticmethod
    def _degraded_result(error: str) -> Dict[str, Any]:
        return {
            "status": "warning", "score": 50,
            "description": f"重复检测降级: {error}",
            "duplicate_pairs": [], "suggestions": [],
            "details": {"error": error},
        }


# ---------------------------------------------------------------------------
# 4. RhythmAnalyzer - 节奏分析
# ---------------------------------------------------------------------------

class RhythmAnalyzer(DimensionAnalyzer):
    """
    分析镜头时长分布和节奏稳定性。

    统计镜头时长的均值、标准差、最大/最小值，识别异常区间，
    并将异常区间发送给 VLM 获取主观评价。
    """

    # 判定阈值
    FAST_PACE_THRESHOLD = 2.0   # 平均 <2s → 过快
    SLOW_PACE_THRESHOLD = 8.0   # 平均 >8s → 过慢
    UNSTABLE_STD_THRESHOLD = 5.0  # 标准差 >5s → 不稳定

    async def analyze(self, shots: List[tuple], **kwargs) -> Dict[str, Any]:
        """
        分析视频节奏。

        Args:
            shots: 镜头列表 [(start, end), ...]

        Returns:
            {
                "status": "pass/warning/error",
                "score": 0-100,
                "description": "简要说明",
                "pace_assessment": "过快/适中/过慢",
                "stability_assessment": "稳定/不稳定",
                "problematic_ranges": [[start_shot, end_shot, "描述"], ...],
                "suggestions": ["建议列表"]
            }
        """
        if not shots:
            return self._empty_result("无镜头数据")

        cache_k = _cache_key("rhythm", *(str(s) for s in shots))
        if cache_k in self._cache:
            return self._cache[cache_k]

        try:
            durations = [end - start for start, end in shots]
            stats = self._compute_stats(durations)
            pace, stability = self._assess(stats)
            problematic = self._find_problematic_ranges(durations)

            # 如果有异常区间，发送给 VLM 获取主观评价
            vlm_suggestions: List[str] = []
            if problematic:
                vlm_suggestions = await self._vlm_evaluate_rhythm(
                    shots, problematic,
                )

            result = self._build_result(stats, pace, stability, problematic, vlm_suggestions)

        except Exception as e:
            logger.error(f"节奏分析失败: {e}")
            result = self._degraded_result(str(e))

        self._cache[cache_k] = result
        return result

    # -- 内部方法 --

    @staticmethod
    def _compute_stats(durations: List[float]) -> Dict[str, float]:
        n = len(durations)
        mean = sum(durations) / n
        variance = sum((d - mean) ** 2 for d in durations) / n
        std = math.sqrt(variance)
        return {
            "count": n,
            "mean": round(mean, 2),
            "std": round(std, 2),
            "min": round(min(durations), 2),
            "max": round(max(durations), 2),
            "total": round(sum(durations), 2),
        }

    def _assess(self, stats: Dict[str, float]) -> Tuple[str, str]:
        mean = stats["mean"]
        std = stats["std"]

        rhythm = self.profile.rhythm
        if mean < rhythm.fast_pace_threshold:
            pace = "过快"
        elif mean > rhythm.slow_pace_threshold:
            pace = "过慢"
        else:
            pace = "适中"

        stability = "不稳定" if std > rhythm.unstable_std_threshold else "稳定"
        return pace, stability

    def _find_problematic_ranges(self, durations: List[float]) -> List[List]:
        """识别连续过长或过短的镜头区间"""
        ranges: List[List] = []
        rhythm = self.profile.rhythm
        window = rhythm.abnormal_run_length

        # 连续过短 (<1s)
        run_start = None
        for i, d in enumerate(durations):
            if d < rhythm.short_shot_threshold:
                if run_start is None:
                    run_start = i
            else:
                if run_start is not None and (i - run_start) >= window:
                    ranges.append([run_start + 1, i, f"连续过短 (<{rhythm.short_shot_threshold:.1f}s)"])
                run_start = None
        if run_start is not None and (len(durations) - run_start) >= window:
            ranges.append([run_start + 1, len(durations), f"连续过短 (<{rhythm.short_shot_threshold:.1f}s)"])

        # 连续过长 (>10s)
        run_start = None
        for i, d in enumerate(durations):
            if d > rhythm.long_shot_threshold:
                if run_start is None:
                    run_start = i
            else:
                if run_start is not None and (i - run_start) >= window:
                    ranges.append([run_start + 1, i, f"连续过长 (>{rhythm.long_shot_threshold:.1f}s)"])
                run_start = None
        if run_start is not None and (len(durations) - run_start) >= window:
            ranges.append([run_start + 1, len(durations), f"连续过长 (>{rhythm.long_shot_threshold:.1f}s)"])

        return ranges

    async def _vlm_evaluate_rhythm(
        self,
        shots: List[tuple],
        problematic: List[List],
    ) -> List[str]:
        """将异常区间信息发送给 VLM 获取主观评价"""
        # 构造摘要信息
        range_desc = "; ".join(
            f"镜头 {r[0]}-{r[1]}: {r[2]}" for r in problematic
        )
        prompt = _load_prompt("rhythm_check", parameters={
            "problematic_ranges": range_desc,
            "total_shots": len(shots),
            "video_type_context": self.profile.prompt_context,
        })

        result_text = await self._call_llm_with_timeout(
            UnifiedLLMService.generate_text(prompt=prompt)
        )

        if result_text:
            parsed = _robust_json_parse(result_text)
            if parsed:
                suggestions = parsed.get("suggestions", [])
                if isinstance(suggestions, list):
                    return suggestions
        return []

    @staticmethod
    def _build_result(
        stats: Dict, pace: str, stability: str,
        problematic: List[List], suggestions: List[str],
    ) -> Dict[str, Any]:
        # 评分逻辑
        score = 100
        if pace == "过快":
            score -= 20
        elif pace == "过慢":
            score -= 15
        if stability == "不稳定":
            score -= 20
        score -= min(len(problematic) * 10, 30)
        score = max(score, 0)

        desc_parts = [f"平均镜头时长 {stats['mean']}s"]
        if pace != "适中":
            desc_parts.append(f"节奏{pace}")
        if stability == "不稳定":
            desc_parts.append("节奏不稳定")
        if problematic:
            desc_parts.append(f"{len(problematic)} 个异常区间")

        return {
            "status": _determine_status(score),
            "score": score,
            "description": "，".join(desc_parts),
            "pace_assessment": pace,
            "stability_assessment": stability,
            "problematic_ranges": problematic,
            "suggestions": suggestions,
            "stats": stats,
        }

    @staticmethod
    def _empty_result(reason: str) -> Dict[str, Any]:
        return {
            "status": "pass", "score": 100,
            "description": reason,
            "pace_assessment": "适中",
            "stability_assessment": "稳定",
            "problematic_ranges": [], "suggestions": [],
        }

    @staticmethod
    def _degraded_result(error: str) -> Dict[str, Any]:
        return {
            "status": "warning", "score": 50,
            "description": f"节奏分析降级: {error}",
            "pace_assessment": "未知",
            "stability_assessment": "未知",
            "problematic_ranges": [], "suggestions": [],
            "details": {"error": error},
        }


# ---------------------------------------------------------------------------
# 5. WasteClipDetector - 废片识别
# ---------------------------------------------------------------------------

def detect_black_frames(video_path: str) -> List[Tuple[float, float]]:
    """
    使用 FFmpeg blackdetect 检测黑屏时间段。

    Returns:
        [(start_sec, end_sec), ...]
    """
    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-vf", "blackdetect=d=0.5:pix_th=0.00",
        "-f", "null", "-",
    ]
    try:
        proc = subprocess.run(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, timeout=120,
        )
        return _parse_blackdetect(proc.stderr)
    except Exception as e:
        logger.error(f"黑屏检测失败: {e}")
        return []


def detect_silence(video_path: str) -> List[Tuple[float, float]]:
    """
    使用 FFmpeg silencedetect 检测静音时间段。

    Returns:
        [(start_sec, end_sec), ...]
    """
    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-af", "silencedetect=noise=-50dB:d=1",
        "-f", "null", "-",
    ]
    try:
        proc = subprocess.run(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, timeout=120,
        )
        return _parse_silencedetect(proc.stderr)
    except Exception as e:
        logger.error(f"静音检测失败: {e}")
        return []


def _parse_blackdetect(stderr: str) -> List[Tuple[float, float]]:
    """解析 blackdetect 的 stderr 输出"""
    segments: List[Tuple[float, float]] = []
    # 匹配 black_start ... black_end ...
    pattern = re.compile(
        r"black_start:\s*([\d.]+)\s*black_end:\s*([\d.]+)"
    )
    for m in pattern.finditer(stderr):
        segments.append((float(m.group(1)), float(m.group(2))))
    return segments


def _parse_silencedetect(stderr: str) -> List[Tuple[float, float]]:
    """解析 silencedetect 的 stderr 输出"""
    segments: List[Tuple[float, float]] = []
    # silence_start 和 silence_end 可能成对出现
    starts: List[float] = []
    ends: List[float] = []
    for m in re.finditer(r"silence_start:\s*([\d.]+)", stderr):
        starts.append(float(m.group(1)))
    for m in re.finditer(r"silence_end:\s*([\d.]+)", stderr):
        ends.append(float(m.group(1)))
    for s, e in zip(starts, ends):
        if e > s:
            segments.append((s, e))
    # 如果最后有 silence_start 但没有 silence_end（到视频结尾）
    if len(starts) > len(ends):
        segments.append((starts[-1], starts[-1] + 999.0))
    return segments


class WasteClipDetector(DimensionAnalyzer):
    """
    使用 FFmpeg 滤镜 + VLM 识别黑屏、无效内容等废片。

    步骤:
    1. 使用 FFmpeg blackdetect 检测黑屏片段
    2. 使用 FFmpeg silencedetect 检测静音片段
    3. 将疑似废片的关键帧发送给 VLM 确认
    """

    async def analyze(
        self,
        keyframe_paths: List[str],
        shots: List[tuple],
        video_path: str,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        识别废片。

        Returns:
            {
                "status": "pass/warning/error",
                "score": 0-100,
                "description": "简要说明",
                "confirmed_waste_clips": [
                    {"shot_id": N, "reason": "...", "action": "delete/trim"}
                ],
                "false_positives": [误判的镜头编号列表]
            }
        """
        if not video_path or not os.path.exists(video_path):
            return self._empty_result("视频文件不存在")

        cache_k = _cache_key("waste", video_path)
        if cache_k in self._cache:
            return self._cache[cache_k]

        try:
            # 步骤 1 & 2: FFmpeg 检测（并行执行）
            black_segments, silence_segments = await asyncio.gather(
                asyncio.get_event_loop().run_in_executor(None, detect_black_frames, video_path),
                asyncio.get_event_loop().run_in_executor(None, detect_silence, video_path),
            )

            # 将时间段映射到镜头编号
            suspect_shots = self._map_segments_to_shots(
                black_segments, silence_segments, shots,
            )

            if not suspect_shots:
                result = {
                    "status": "pass", "score": 100,
                    "description": f"共 {len(shots)} 个镜头，未检测到废片",
                    "confirmed_waste_clips": [], "false_positives": [],
                }
                self._cache[cache_k] = result
                return result

            # 步骤 3: VLM 确认
            confirmed, false_positives = await self._vlm_verify_waste(
                keyframe_paths, suspect_shots,
            )

            result = self._build_result(confirmed, false_positives, len(shots))

        except Exception as e:
            logger.error(f"废片识别失败: {e}")
            result = self._degraded_result(str(e))

        self._cache[cache_k] = result
        return result

    # -- 内部方法 --

    def _map_segments_to_shots(
        self,
        black_segments: List[Tuple[float, float]],
        silence_segments: List[Tuple[float, float]],
        shots: List[tuple],
    ) -> List[Dict[str, Any]]:
        """将黑屏/静音时间段映射到对应的镜头"""
        suspects: List[Dict[str, Any]] = []
        seen_shots = set()

        for idx, (shot_start, shot_end) in enumerate(shots):
            shot_num = idx + 1
            if shot_num in seen_shots:
                continue

            reasons = []

            # 检查黑屏重叠
            for bs, be in black_segments:
                if bs < shot_end and be > shot_start:
                    overlap = min(be, shot_end) - max(bs, shot_start)
                    if overlap > self.profile.waste.black_overlap_threshold:
                        reasons.append(f"黑屏 ({bs:.1f}s-{be:.1f}s)")
                        break

            # 检查静音重叠
            for ss, se in silence_segments:
                if ss < shot_end and se > shot_start:
                    overlap = min(se, shot_end) - max(ss, shot_start)
                    duration = shot_end - shot_start
                    # 静音覆盖 >80% 的镜头时长
                    if duration > 0 and overlap / duration > self.profile.waste.silence_overlap_ratio:
                        reasons.append(f"静音 ({ss:.1f}s-{se:.1f}s)")
                        break

            if reasons:
                suspects.append({
                    "shot_id": shot_num,
                    "shot_index": idx,
                    "reasons": reasons,
                })
                seen_shots.add(shot_num)

        return suspects

    async def _vlm_verify_waste(
        self,
        keyframe_paths: List[str],
        suspects: List[Dict[str, Any]],
    ) -> Tuple[List[Dict], List[int]]:
        """VLM 确认疑似废片"""
        confirmed: List[Dict] = []
        false_positives: List[int] = []

        for suspect in suspects:
            idx = suspect["shot_index"]
            if idx >= len(keyframe_paths):
                continue

            prompt = _load_prompt("waste_check", parameters={
                "shot_id": suspect["shot_id"],
                "reasons": "，".join(suspect["reasons"]),
                "waste_candidates": (
                    f"镜头{suspect['shot_id']}，疑似原因："
                    f"{'，'.join(suspect['reasons'])}"
                ),
                "video_type_context": self.profile.prompt_context,
            })

            result_text = await self._call_llm_with_timeout(
                UnifiedLLMService.analyze_images(
                    images=[keyframe_paths[idx]], prompt=prompt, batch_size=1,
                )
            )

            if result_text:
                text = result_text[-1] if isinstance(result_text, list) else str(result_text)
                parsed = _robust_json_parse(text)
                if parsed:
                    is_waste = parsed.get("is_waste", None)
                    if is_waste is True:
                        confirmed.append({
                            "shot_id": suspect["shot_id"],
                            "reason": parsed.get("reason", "，".join(suspect["reasons"])),
                            "action": parsed.get("action", "delete"),
                        })
                    elif is_waste is False:
                        false_positives.append(suspect["shot_id"])
                    else:
                        # 不确定时保守处理：标记为 trim
                        confirmed.append({
                            "shot_id": suspect["shot_id"],
                            "reason": f"VLM 不确定，保守标记（{', '.join(suspect['reasons'])}）",
                            "action": "trim",
                        })
            else:
                # VLM 失败，保守标记
                confirmed.append({
                    "shot_id": suspect["shot_id"],
                    "reason": f"VLM 调用失败，保守标记（{', '.join(suspect['reasons'])}）",
                    "action": "trim",
                })

        return confirmed, false_positives

    @staticmethod
    def _build_result(
        confirmed: List[Dict], false_positives: List[int], total: int,
    ) -> Dict[str, Any]:
        penalty = min(len(confirmed) * 15, 60)
        score = max(100 - penalty, 0)

        return {
            "status": _determine_status(score),
            "score": score,
            "description": f"共 {total} 个镜头，确认 {len(confirmed)} 个废片，"
                           f"{len(false_positives)} 个误判",
            "confirmed_waste_clips": confirmed,
            "false_positives": false_positives,
        }

    @staticmethod
    def _empty_result(reason: str) -> Dict[str, Any]:
        return {
            "status": "pass", "score": 100,
            "description": reason,
            "confirmed_waste_clips": [], "false_positives": [],
        }

    @staticmethod
    def _degraded_result(error: str) -> Dict[str, Any]:
        return {
            "status": "warning", "score": 50,
            "description": f"废片识别降级: {error}",
            "confirmed_waste_clips": [], "false_positives": [],
            "details": {"error": error},
        }


# ---------------------------------------------------------------------------
# MultiDimensionAnalyzer - 多维度协调器
# ---------------------------------------------------------------------------

class MultiDimensionAnalyzer:
    """多维度分析器 - 协调 5 个维度的评估"""

    def __init__(self, llm_timeout: int = 30, profile: VideoTypeProfile | None = None):
        self.profile = profile or get_video_type_profile()
        self.consistency_checker = ConsistencyChecker(llm_timeout=llm_timeout, profile=self.profile)
        self.coherence_checker = CoherenceChecker(llm_timeout=llm_timeout, profile=self.profile)
        self.duplicate_detector = DuplicateDetector(llm_timeout=llm_timeout, profile=self.profile)
        self.rhythm_analyzer = RhythmAnalyzer(llm_timeout=llm_timeout, profile=self.profile)
        self.waste_detector = WasteClipDetector(llm_timeout=llm_timeout, profile=self.profile)

    async def analyze_all(
        self,
        keyframe_paths: List[str],
        shots: List[tuple],
        video_path: str,
    ) -> Dict[str, Any]:
        """
        并行执行所有维度的分析。

        Returns:
            {
                "consistency": {...},
                "coherence": {...},
                "duplicate": {...},
                "rhythm": {...},
                "waste": {...}
            }
        """
        analyzer_factories = {
            "consistency": lambda: self.consistency_checker.analyze(keyframe_paths=keyframe_paths),
            "coherence": lambda: self.coherence_checker.analyze(keyframe_paths=keyframe_paths, shots=shots),
            "duplicate": lambda: self.duplicate_detector.analyze(keyframe_paths=keyframe_paths),
            "rhythm": lambda: self.rhythm_analyzer.analyze(shots=shots),
            "waste": lambda: self.waste_detector.analyze(
                keyframe_paths=keyframe_paths, shots=shots, video_path=video_path,
            ),
        }
        if self.profile.mode == AnalysisMode.FAST:
            dimension_names = [name for name in analyzer_factories if name in self.profile.focus_dimensions]
        else:
            dimension_names = list(analyzer_factories.keys())

        results = await asyncio.gather(
            *(analyzer_factories[name]() for name in dimension_names),
            return_exceptions=True,
        )

        output: Dict[str, Any] = {}
        for name, res in zip(dimension_names, results):
            if isinstance(res, Exception):
                logger.error(f"维度 '{name}' 分析异常: {res}")
                output[name] = {
                    "status": "error", "score": 0,
                    "description": f"分析异常: {res}",
                }
            else:
                output[name] = res

        return output

    def clear_cache(self):
        """清空所有分析器的缓存"""
        for analyzer in [
            self.consistency_checker,
            self.coherence_checker,
            self.duplicate_detector,
            self.rhythm_analyzer,
            self.waste_detector,
        ]:
            analyzer._cache.clear()
        logger.info("已清空所有维度分析器缓存")
