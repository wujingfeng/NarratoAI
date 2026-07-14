"""
逐镜分析与智能剪辑方案生成模块

为每个镜头生成详细描述、问题标注和修改建议。
结合VLM关键帧分析与多维质量评估结果，输出 ShotInfo 列表。
并基于逐镜分析结果生成可执行的剪辑方案，输出格式兼容 clip_video.py。
"""

import json
import re
import logging
from typing import List, Dict, Any, Tuple, Literal

from app.models.diagnosis_schema import ShotInfo
from app.services.llm.unified_service import UnifiedLLMService
from app.services.video_diagnosis.profiles import VideoTypeProfile, get_video_type_profile

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------

def load_prompt_template(category: str, name: str) -> str:
    """加载Prompt模板

    Args:
        category: 模板分类目录，如 ``video_diagnosis``
        name: 模板文件名（不含后缀）

    Returns:
        模板文本内容；如果文件不存在则返回空字符串。
    """
    template_path = f"app/services/prompts/{category}/{name}.txt"
    try:
        with open(template_path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        logger.error(f"Prompt模板不存在: {template_path}")
        return ""


def parse_json_from_text(text: str) -> Dict[str, Any]:
    """从文本中提取JSON对象

    尝试多种策略:
    1. 直接解析整个文本
    2. 查找第一个 ``{`` 到最后一个 ``}`` 之间的内容
    3. 查找 `````json ... ````` 代码块

    Returns:
        解析后的字典；所有策略失败时返回空字典。
    """
    if not text:
        return {}

    # 策略1: 直接解析
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 策略2: 提取花括号包裹的内容
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    # 策略3: 提取代码块
    match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # 所有策略失败
    logger.warning(f"无法从文本中解析JSON: {text[:100]}...")
    return {}


# ---------------------------------------------------------------------------
# ShotLevelAnalyzer
# ---------------------------------------------------------------------------

class ShotLevelAnalyzer:
    """逐镜分析器

    为每个镜头生成详细描述、问题标注和修改建议。
    """

    def __init__(self, profile: VideoTypeProfile | None = None):
        self.llm_service = UnifiedLLMService
        self.profile = profile or get_video_type_profile()

    # ------------------------------------------------------------------
    # 公开方法
    # ------------------------------------------------------------------

    async def analyze_all_shots(
        self,
        keyframe_paths: List[str],
        shots: List[Tuple[float, float]],
        quality_results: Dict[str, Any],
    ) -> List[ShotInfo]:
        """分析所有镜头

        Args:
            keyframe_paths: 关键帧路径列表
            shots: 镜头列表 ``[(start, end), ...]``
            quality_results: 质量评估结果（来自 ``MultiDimensionAnalyzer``）

        Returns:
            ``ShotInfo`` 列表，按镜头顺序排列
        """
        # 1. 分批调用VLM获取每帧描述
        shot_descriptions = await self._batch_analyze_frames(keyframe_paths)

        # 2. 为每个镜头生成详细信息
        shot_infos: List[ShotInfo] = []
        for idx, (keyframe_path, (start, end)) in enumerate(
            zip(keyframe_paths, shots), start=1
        ):
            duration = end - start
            description = shot_descriptions.get(idx, "")

            # 从质量评估结果中提取该镜头的问题
            issues = self._extract_issues_for_shot(idx, quality_results)

            # 生成修改建议
            suggestion = await self._generate_suggestion(
                shot_id=idx,
                duration=duration,
                description=description,
                issues=issues,
            )

            # 确定状态
            status = self._determine_status(issues)

            shot_info = ShotInfo(
                shot_id=idx,
                start_time=start,
                end_time=end,
                duration=duration,
                keyframe_path=keyframe_path,
                content_description=description,
                quality_status=status,
                issues=issues,
                suggestions=[suggestion] if suggestion else [],
            )
            shot_infos.append(shot_info)

        return shot_infos

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    async def _batch_analyze_frames(
        self, keyframe_paths: List[str]
    ) -> Dict[int, str]:
        """分批调用VLM分析关键帧

        Returns:
            ``{shot_id: "描述文本", ...}``
        """
        batch_size = 10
        results: Dict[int, str] = {}

        selected = self._select_keyframes_for_description(keyframe_paths)

        for i in range(0, len(selected), batch_size):
            batch = selected[i : i + batch_size]
            batch_paths = [path for _shot_id, path in batch]
            batch_start_id = batch[0][0] if batch else 1

            # 构建prompt
            prompt = load_prompt_template("video_diagnosis", "shot_analysis")
            if not prompt:
                # 模板不存在时使用默认prompt
                prompt = (
                    "请描述以下每个视频关键帧的内容，以JSON数组格式返回，"
                    "每个元素包含 shot_id 和 description 字段。"
                )

            # 调用VLM
            try:
                response_list = await self.llm_service.analyze_images(
                    images=batch_paths,
                    prompt=prompt,
                    provider=None,  # 使用配置中的默认provider
                    batch_size=batch_size,
                )

                # analyze_images 返回 List[str]（每个批次一个字符串）
                for resp_str in response_list:
                    batch_results = self._parse_batch_response(resp_str, batch_start_id)
                    results.update(batch_results)

            except Exception as e:
                logger.warning(f"批次{i // batch_size + 1}分析失败: {e}")
                # 填充默认描述
                for j, _path in enumerate(batch_paths):
                    sid = batch[j][0]
                    results[sid] = f"镜头{sid}的关键帧"

        return results

    def _select_keyframes_for_description(self, keyframe_paths: List[str]) -> List[tuple[int, str]]:
        """按预算选择需要 VLM 描述的关键帧，保持成本可控"""
        max_items = self.profile.budget.max_shot_descriptions
        indexed = [(idx, path) for idx, path in enumerate(keyframe_paths, start=1) if path]
        if len(indexed) <= max_items:
            return indexed
        step = len(indexed) / max_items
        selected = []
        used = set()
        for i in range(max_items):
            pos = min(int(i * step), len(indexed) - 1)
            if pos not in used:
                used.add(pos)
                selected.append(indexed[pos])
        return selected

    def _parse_batch_response(
        self, response: str, batch_start_id: int
    ) -> Dict[int, str]:
        """解析VLM批量分析响应

        尝试将响应解析为JSON数组或JSON对象，提取每个镜头的描述。

        Args:
            response: VLM返回的原始文本
            batch_start_id: 当前批次的起始镜头编号

        Returns:
            ``{shot_id: description}``
        """
        results: Dict[int, str] = {}
        parsed = parse_json_from_text(response)

        if isinstance(parsed, dict):
            # 可能是 {"shots": [...]} 或 {"1": "描述", ...}
            shots_data = parsed.get("shots", parsed.get("frames", None))
            if isinstance(shots_data, list):
                for idx, item in enumerate(shots_data):
                    shot_id = item.get("shot_id", batch_start_id + idx)
                    desc = item.get("description", "")
                    results[int(shot_id)] = desc
            elif isinstance(shots_data, dict):
                for key, val in shots_data.items():
                    try:
                        results[int(key)] = str(val)
                    except (ValueError, TypeError):
                        pass
            else:
                # 直接把key-value当作 shot_id -> description
                for key, val in parsed.items():
                    try:
                        results[int(key)] = str(val)
                    except (ValueError, TypeError):
                        pass

        elif isinstance(parsed, list):
            for idx, item in enumerate(parsed):
                if isinstance(item, dict):
                    shot_id = item.get("shot_id", batch_start_id + idx)
                    desc = item.get("description", "")
                    results[int(shot_id)] = desc
                elif isinstance(item, str):
                    results[batch_start_id + idx] = item

        # 如果解析失败，尝试将整段文本作为单帧描述
        if not results and response.strip():
            results[batch_start_id] = response.strip()

        return results

    def _extract_issues_for_shot(
        self, shot_id: int, quality_results: Dict[str, Any]
    ) -> List[str]:
        """从质量评估结果中提取特定镜头的问题"""
        issues: List[str] = []

        # 从一致性检查中提取
        consistency = quality_results.get("consistency", {})
        if shot_id in consistency.get("inconsistent_shots", []):
            issues.append("色调/构图不一致")

        # 从连贯度检查中提取
        coherence = quality_results.get("coherence", {})
        for transition in coherence.get("problematic_transitions", []):
            if shot_id in transition:
                issues.append("转场突兀")

        # 从重复检测中提取
        duplicate = quality_results.get("duplicate", {})
        for pair in duplicate.get("duplicate_pairs", []):
            if shot_id == pair[0] or shot_id == pair[1]:
                issues.append("重复镜头")

        # 从废片检测中提取
        waste = quality_results.get("waste", {})
        for waste_clip in waste.get("confirmed_waste_clips", []):
            if waste_clip.get("shot_id") == shot_id:
                issues.append(waste_clip.get("reason", "废片"))

        # 从节奏分析中提取
        rhythm = quality_results.get("rhythm", {})
        for range_info in rhythm.get("problematic_ranges", []):
            if len(range_info) >= 3 and range_info[0] <= shot_id <= range_info[1]:
                issues.append(range_info[2])

        return issues

    async def _generate_suggestion(
        self,
        shot_id: int,
        duration: float,
        description: str,
        issues: List[str],
    ) -> str:
        """生成具体的修改建议"""
        if not issues:
            return ""

        prompt = load_prompt_template("video_diagnosis", "shot_analysis")
        if not prompt:
            prompt = (
                "你是一位专业的视频剪辑顾问。请根据以下镜头信息给出修改建议，"
                "以JSON格式返回，包含 suggestion 字段。"
            )

        prompt_filled = prompt.format(
            shot_id=shot_id,
            duration=duration,
            keyframe_description=description,
            known_issues=", ".join(issues),
            video_type_context=self.profile.prompt_context,
        ) if "{shot_id}" in prompt else (
            f"镜头{shot_id}，时长{duration:.1f}秒，"
            f"画面内容：{description}，"
            f"已知问题：{', '.join(issues)}。"
            f"\n请给出修改建议，以JSON格式返回，包含 suggestion 字段。"
        )

        try:
            response = await self.llm_service.generate_text(
                prompt=prompt_filled,
                provider=None,  # 使用配置中的默认provider
                temperature=0.3,
            )

            # 解析JSON响应
            result = parse_json_from_text(response)
            return result.get("suggestion", "")

        except Exception as e:
            logger.warning(f"生成建议失败(镜头{shot_id}): {e}")
            return self._generate_fallback_suggestion(issues, duration)

    def _generate_fallback_suggestion(
        self, issues: List[str], duration: float
    ) -> str:
        """当LLM调用失败时，生成基于规则的兜底建议"""
        suggestions: List[str] = []

        for issue in issues:
            if "废片" in issue or "黑屏" in issue or "无效内容" in issue:
                suggestions.append("建议删除此镜头")
            elif "重复" in issue:
                suggestions.append("建议保留一个最佳片段，删除重复部分")
            elif "转场突兀" in issue:
                suggestions.append("建议添加转场效果（淡入淡出/溶解）")
            elif "节奏偏慢" in issue:
                suggestions.append("建议裁剪镜头首尾，加快节奏")
            elif "不一致" in issue:
                suggestions.append("建议通过调色统一色调")
            elif "模糊" in issue:
                suggestions.append("建议替换为更清晰的镜头")
            else:
                suggestions.append(f"建议针对「{issue}」进行优化")

        return "；".join(suggestions) if suggestions else ""

    def _determine_status(
        self, issues: List[str]
    ) -> Literal["pass", "warning", "error"]:
        """根据问题列表确定状态"""
        if not issues:
            return "pass"

        error_keywords = ["黑屏", "无效内容", "严重模糊"]
        warning_keywords = ["节奏偏慢", "重复", "转场突兀"]

        for issue in issues:
            if any(keyword in issue for keyword in error_keywords):
                return "error"

        for issue in issues:
            if any(keyword in issue for keyword in warning_keywords):
                return "warning"

        return "pass"


# ---------------------------------------------------------------------------
# EditingPlanGenerator - 智能剪辑方案生成器
# ---------------------------------------------------------------------------

class EditingPlanGenerator:
    """智能剪辑方案生成器

    根据逐镜分析结果生成可直接用于 ``clip_video.py`` 裁剪流程的剪辑方案。

    支持两种剪辑模式:
    - **conservative**（保守）: 仅删除明确的废片（error 状态）
    - **aggressive**（激进）: 积极裁剪节奏慢、重复、有警告的镜头
    """

    # ------------------------------------------------------------------
    # 公开方法
    # ------------------------------------------------------------------

    def generate_plan(
        self,
        video_path: str,
        shot_details: List[ShotInfo],
        mode: Literal["conservative", "aggressive"] = "conservative",
    ) -> Dict[str, Any]:
        """生成智能剪辑方案

        Args:
            video_path: 原始视频路径
            shot_details: 逐镜详情列表（来自 ``ShotLevelAnalyzer``）
            mode: 剪辑模式
                - ``conservative``: 仅删除明确的废片
                - ``aggressive``: 积极裁剪节奏慢、重复的镜头

        Returns:
            兼容 ``clip_video.py`` 的方案字典::

                {
                    "video_clips": [
                        {
                            "video_path": "...",
                            "trim_start": 0.3,
                            "trim_end": 5.0,
                            "narration": "",
                            "OST": 0
                        },
                        ...
                    ],
                    "transitions": [
                        {
                            "from_shot": 3,
                            "to_shot": 4,
                            "type": "fade",
                            "duration": 0.4
                        }
                    ],
                    "summary": {
                        "total_shots": 20,
                        "kept_shots": 18,
                        "removed_shots": 2,
                        "original_duration": 120.0,
                        "trimmed_duration": 110.5
                    }
                }
        """
        video_clips: List[Dict[str, Any]] = []
        kept_shot_ids: List[int] = []
        removed_shot_ids: List[int] = []
        original_duration = 0.0
        trimmed_duration = 0.0

        for shot in shot_details:
            original_duration += shot.duration

            if self._should_skip_shot(shot, mode):
                removed_shot_ids.append(shot.shot_id)
                logger.info(
                    f"镜头 {shot.shot_id} 被跳过 "
                    f"(status={shot.quality_status}, issues={shot.issues})"
                )
                continue

            # 计算裁剪区间
            trim_start, trim_end = self._calculate_trim_range(shot, mode)
            clip_duration = trim_end - trim_start

            clip = {
                "video_path": video_path,
                "trim_start": round(trim_start, 3),
                "trim_end": round(trim_end, 3),
                "narration": "",  # 可选: 从字幕或其他来源填充
                "OST": 0,
            }
            video_clips.append(clip)
            kept_shot_ids.append(shot.shot_id)
            trimmed_duration += clip_duration

        # 生成转场建议
        transitions = self._suggest_transitions(shot_details, video_clips)

        # 汇总统计
        summary = {
            "total_shots": len(shot_details),
            "kept_shots": len(kept_shot_ids),
            "removed_shots": len(removed_shot_ids),
            "original_duration": round(original_duration, 3),
            "trimmed_duration": round(trimmed_duration, 3),
            "time_saved": round(original_duration - trimmed_duration, 3),
            "mode": mode,
        }

        logger.info(
            f"剪辑方案生成完成: {summary['kept_shots']}/{summary['total_shots']} 个镜头保留, "
            f"时长 {summary['original_duration']:.1f}s → {summary['trimmed_duration']:.1f}s"
        )

        return {
            "video_clips": video_clips,
            "transitions": transitions,
            "summary": summary,
        }

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _should_skip_shot(self, shot: ShotInfo, mode: str) -> bool:
        """判断是否应该跳过某个镜头

        Args:
            shot: 镜头详情
            mode: 剪辑模式

        Returns:
            ``True`` 表示应跳过该镜头
        """
        # error 状态的镜头始终跳过（黑屏、无效内容等）
        if shot.quality_status == "error":
            return True

        if mode == "aggressive":
            # 激进模式下，跳过有警告的镜头
            if shot.quality_status == "warning":
                return True

        return False

    def _calculate_trim_range(
        self,
        shot: ShotInfo,
        mode: str,
    ) -> Tuple[float, float]:
        """计算裁剪区间

        根据镜头的问题和剪辑模式，计算实际保留的时间范围。

        Args:
            shot: 镜头详情
            mode: 剪辑模式

        Returns:
            ``(trim_start, trim_end)``  单位: 秒
        """
        start = shot.start_time
        end = shot.end_time

        # 如果标记为节奏偏慢，尝试裁剪开头结尾
        if "连续过长 (>10s)" in shot.issues or "节奏偏慢" in shot.issues:
            if mode == "conservative":
                # 保守裁剪: 去掉首尾各 0.5 秒
                start += 0.5
                end -= 0.5
            elif mode == "aggressive":
                # 激进裁剪: 缩短至 3 秒以内
                target_duration = min(3.0, shot.duration * 0.6)
                center = (start + end) / 2
                start = center - target_duration / 2
                end = center + target_duration / 2

        # 如果有转场突兀问题，在激进模式下稍微裁剪首帧
        if "转场突兀" in shot.issues and mode == "aggressive":
            start += 0.3

        # 确保裁剪后的时长至少 0.5 秒
        if end - start < 0.5:
            center = (shot.start_time + shot.end_time) / 2
            start = center - 0.25
            end = center + 0.25

        # 不能超出原始镜头范围
        return max(start, shot.start_time), min(end, shot.end_time)

    def _suggest_transitions(
        self,
        shot_details: List[ShotInfo],
        video_clips: List[Dict],
    ) -> List[Dict[str, Any]]:
        """建议转场效果

        基于连贯度评估结果，在转场突兀的相邻镜头之间添加转场。
        对于没有特殊问题的相邻镜头，默认添加轻微的淡入淡出。

        Args:
            shot_details: 完整的逐镜详情列表
            video_clips: 已筛选后的视频片段列表

        Returns:
            转场建议列表
        """
        transitions: List[Dict[str, Any]] = []

        if len(video_clips) < 2:
            return transitions

        # 构建保留镜头的 shot_id 列表，用于判断相邻关系
        # video_clips[i] 对应保留列表中第 i 个镜头
        # 我们需要从 shot_details 中找到对应的原始 shot_id
        kept_shots = [s for s in shot_details if s.quality_status != "error"]

        for i in range(len(video_clips) - 1):
            # 默认转场: 淡入淡出 0.3 秒
            transition_type = "fade"
            transition_duration = 0.3

            # 检查是否有转场突兀的标记 → 使用更长的溶解转场
            if i < len(kept_shots) - 1:
                current_shot = kept_shots[i]
                next_shot = kept_shots[i + 1]
                if (
                    "转场突兀" in current_shot.issues
                    or "转场突兀" in next_shot.issues
                ):
                    transition_type = "dissolve"
                    transition_duration = 0.5

            transitions.append({
                "from_shot": i + 1,
                "to_shot": i + 2,
                "type": transition_type,
                "duration": transition_duration,
            })

        return transitions
