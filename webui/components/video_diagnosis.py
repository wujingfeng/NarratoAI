"""
视频诊断 WebUI 组件

提供 AI 视频诊断功能的完整界面,包括:
- 视频上传与参数配置
- 诊断进度实时展示
- 六维评分结果可视化
- 逐镜建议列表
- 智能剪辑执行入口
"""

import asyncio
import html
import json
import os
import threading
import time
import uuid
from typing import Optional

import streamlit as st
from loguru import logger

from app.models import const
from app.services.state import state
from app.services.video_diagnosis.profiles import VIDEO_TYPE_LABELS


# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

_DIAGNOSIS_STEPS = [
    "场景检测",
    "质量评估",
    "逐镜分析",
    "方案生成",
    "报告生成",
]

_DIM_NAMES = {
    "consistency": "一致性",
    "coherence": "连贯度",
    "duplicate": "重复镜",
    "rhythm": "节奏",
    "waste": "废片",
}

_STATUS_COLOR = {
    "pass": "#52c41a",
    "warning": "#faad14",
    "error": "#ff4d4f",
}

_STATUS_ICON = {
    "pass": "✅",
    "warning": "⚠️",
    "error": "❌",
}


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------


def render_video_diagnosis_page():
    """渲染视频诊断主页面"""

    st.title("🎬 AI视频诊断")
    st.markdown("---")

    # 顶部: 视频上传区域
    with st.container():
        st.subheader("📤 上传视频")
        uploaded_files = st.file_uploader(
            "支持上传1-5个视频文件(mp4/mov/avi)",
            type=["mp4", "mov", "avi"],
            accept_multiple_files=True,
        )

        subtitle_file = st.file_uploader(
            "可选: 上传字幕文件(srt格式)",
            type=["srt"],
            key="diagnosis_subtitle",
        )

        col1, col2, col3 = st.columns(3)
        with col1:
            diagnosis_mode = st.selectbox(
                "诊断模式",
                ["标准分析 (推荐)", "快速模式", "深度分析"],
                index=0,
                key="diagnosis_mode",
            )

        with col2:
            video_type_label = st.selectbox(
                "视频类型",
                list(VIDEO_TYPE_LABELS.keys()),
                index=list(VIDEO_TYPE_LABELS.keys()).index("通用"),
                key="diagnosis_video_type",
            )

        with col3:
            editing_mode = st.selectbox(
                "剪辑模式",
                ["保守模式 (仅删除废片)", "激进模式 (积极裁剪)"],
                index=0,
                key="diagnosis_editing_mode",
            )

        start_button = st.button(
            "🚀 开始诊断",
            type="primary",
            use_container_width=True,
            key="start_diagnosis_btn",
        )

    # 检查已有任务的完成/失败状态（处理页面刷新场景）
    _existing_task_id = st.session_state.get("current_task_id")
    if _existing_task_id:
        _task_info = state.get_task(_existing_task_id)
        if _task_info:
            _task_state = _task_info.get("state")
            if _task_state == const.TASK_STATE_COMPLETE:
                st.session_state["diagnosis_in_progress"] = False
                _result_path = _task_info.get("result_path", "")
                if _result_path and os.path.exists(_result_path):
                    with open(_result_path, "r", encoding="utf-8") as _f:
                        _result_data = json.load(_f)
                    _result_data["pdf_path"] = _task_info.get("pdf_path", "")
                    st.session_state["diagnosis_result"] = _result_data
                st.session_state.pop("current_task_id", None)
                st.rerun()
            elif _task_state == const.TASK_STATE_FAILED:
                st.session_state["diagnosis_in_progress"] = False
                st.session_state["diagnosis_error_msg"] = _task_info.get(
                    "message", "诊断失败"
                )
                st.session_state.pop("current_task_id", None)
                st.rerun()

    # 处理"开始诊断"按钮点击
    if start_button:
        if not uploaded_files:
            st.error("请先上传至少一个视频文件")
            return
        _start_diagnosis(uploaded_files, subtitle_file, diagnosis_mode, editing_mode, video_type_label)
        return

    # 中部: 进度显示(诊断过程中)
    if st.session_state.get("diagnosis_in_progress"):
        _show_progress_ui()
        return

    # 错误信息展示
    if st.session_state.get("diagnosis_error_msg"):
        st.error(f"❌ {st.session_state['diagnosis_error_msg']}")
        if st.button("🔄 重新开始", key="restart_after_error_btn"):
            _clear_diagnosis_result()
            st.rerun()
        return

    # 下部: 诊断结果展示(诊断完成后)
    if st.session_state.get("diagnosis_result"):
        _show_results_ui(st.session_state["diagnosis_result"])


# ---------------------------------------------------------------------------
# 进度 UI
# ---------------------------------------------------------------------------


def _show_progress_ui():
    """显示诊断进度（从全局 state 读取）"""
    task_id = st.session_state.get("current_task_id")
    task_info = state.get_task(task_id) if task_id else None

    if not task_info:
        st.warning("无法获取任务进度")
        time.sleep(2)
        st.rerun()
        return

    task_state = task_info.get("state", const.TASK_STATE_PROCESSING)

    # 任务完成 → 加载结果
    if task_state == const.TASK_STATE_COMPLETE:
        st.session_state["diagnosis_in_progress"] = False
        result_path = task_info.get("result_path", "")
        if result_path and os.path.exists(result_path):
            with open(result_path, "r", encoding="utf-8") as f:
                result_data = json.load(f)
            result_data["pdf_path"] = task_info.get("pdf_path", "")
            st.session_state["diagnosis_result"] = result_data
        st.session_state.pop("current_task_id", None)
        st.rerun()
        return

    # 任务失败 → 展示错误
    if task_state == const.TASK_STATE_FAILED:
        st.session_state["diagnosis_in_progress"] = False
        st.session_state["diagnosis_error_msg"] = task_info.get("message", "诊断失败")
        st.session_state.pop("current_task_id", None)
        st.rerun()
        return

    # 正常进度展示
    progress = task_info.get("progress", 0)
    message = task_info.get("message", "处理中...")

    st.subheader("⏳ 诊断进行中...")

    st.progress(progress / 100.0)
    st.write(f"**当前步骤:** {message}")

    # 步骤指示器
    current_step_idx = min(progress // 20, len(_DIAGNOSIS_STEPS) - 1)

    cols = st.columns(len(_DIAGNOSIS_STEPS))
    for i, step in enumerate(_DIAGNOSIS_STEPS):
        with cols[i]:
            if i < current_step_idx:
                st.success(f"✓ {step}")
            elif i == current_step_idx:
                st.info(f"● {step}")
            else:
                st.write(f"○ {step}")

    # 自动刷新(每2秒)
    time.sleep(2)
    st.rerun()


# ---------------------------------------------------------------------------
# 结果 UI
# ---------------------------------------------------------------------------


def _show_results_ui(result: dict):
    """展示诊断结果"""

    # 顶部概览卡片
    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("总体评级", result.get("overall_grade", "B"))

    with col2:
        st.metric("镜头总数", result.get("total_shots", 0))

    with col3:
        duration = result.get("video_duration", 0)
        st.metric("视频时长", f"{duration:.0f}秒")

    st.markdown("---")

    # 六维评分卡片
    st.subheader("📊 六维评分")

    dimension_scores = result.get("dimension_scores", [])

    if dimension_scores:
        cols = st.columns(min(len(dimension_scores), 5))
        for i, score in enumerate(dimension_scores):
            with cols[i % len(cols)]:
                status = score.get("status", "warning")
                color = _STATUS_COLOR.get(status, "#faad14")
                icon = _STATUS_ICON.get(status, "❓")
                dim_label = _DIM_NAMES.get(score.get("dimension"), score.get("dimension"))
                desc = score.get("reason") or score.get("description", "")
                desc_preview = f"{desc[:30]}..." if len(desc) > 30 else desc
                safe_dim_label = html.escape(str(dim_label))
                safe_desc_preview = html.escape(str(desc_preview))

                st.markdown(
                    f"""
                    <div style="padding: 15px; border-radius: 10px; background-color: #1e1e1e; border: 2px solid {color};">
                        <h4>{icon} {safe_dim_label}</h4>
                        <p style="font-size: 24px; font-weight: bold; color: {color};">{score.get('score', 0):.0f}分</p>
                        <p style="font-size: 12px; color: #999;">{safe_desc_preview}</p>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

        st.markdown("#### 评分原因与改进建议")
        for score in dimension_scores:
            dim_label = _DIM_NAMES.get(score.get("dimension"), score.get("dimension"))
            confidence = score.get("confidence", 0)
            try:
                confidence_text = f"{float(confidence):.0%}"
            except (TypeError, ValueError):
                confidence_text = "未知"

            with st.expander(
                f"{dim_label} | {score.get('score', 0):.0f}分 | 置信度 {confidence_text}",
                expanded=False,
            ):
                reason = score.get("reason") or score.get("description") or "暂无原因"
                st.write(f"**评分原因:** {reason}")

                evidence = score.get("evidence", [])
                if evidence:
                    st.write("**主要依据:**")
                    for item in evidence[:8]:
                        st.write(f"- {item}")

                suggestions = score.get("suggestions", [])
                if suggestions:
                    st.write("**改进建议:**")
                    for item in suggestions[:6]:
                        st.info(item)
    else:
        st.info("暂无维度评分数据")

    st.markdown("---")

    # 整体评价
    st.subheader("💡 整体评价")
    st.write(result.get("summary", "暂无总结"))

    st.markdown("---")

    # 逐镜建议列表
    st.subheader("🎞️ 逐镜建议")

    shot_details = result.get("shot_details", [])

    for shot in shot_details[:20]:
        status = shot.get("quality_status", "pass")
        status_text = {"pass": "通过", "warning": "注意", "error": "警告"}.get(status, "未知")

        with st.expander(
            f"镜头 #{shot.get('shot_id')} | 时长: {shot.get('duration', 0):.1f}s | 状态: {status_text}",
            expanded=False,
        ):
            col1, col2 = st.columns([1, 3])

            with col1:
                keyframe_path = shot.get("keyframe_path", "")
                if keyframe_path and os.path.exists(keyframe_path):
                    st.image(keyframe_path, width=200)

            with col2:
                st.write(f"**内容描述:** {shot.get('content_description', '无')}")

                issues = shot.get("issues", [])
                if issues:
                    st.warning(f"**问题:** {', '.join(issues)}")

                suggestions = shot.get("suggestions", [])
                if suggestions:
                    st.info(f"**建议:** {suggestions[0]}")

    if len(shot_details) > 20:
        st.write(f"*...还有 {len(shot_details) - 20} 个镜头未显示*")

    st.markdown("---")

    # 底部操作按钮
    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("🔄 再测一次", use_container_width=True, key="retry_diagnosis_btn"):
            _clear_diagnosis_result()
            st.rerun()

    with col2:
        pdf_path = result.get("pdf_path", "")
        if pdf_path and os.path.exists(pdf_path):
            with open(pdf_path, "rb") as f:
                st.download_button(
                    label="📄 导出PDF",
                    data=f,
                    file_name="video_diagnosis_report.pdf",
                    mime="application/pdf",
                    use_container_width=True,
                    key="download_pdf_btn",
                )

    with col3:
        if st.button(
            "✂️ 一键智能剪辑",
            type="primary",
            use_container_width=True,
            key="smart_editing_btn",
        ):
            _execute_smart_editing(result)


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------


def _clear_diagnosis_result():
    """清除诊断结果"""
    for key in ("diagnosis_result", "diagnosis_in_progress", "diagnosis_error_msg", "current_task_id"):
        st.session_state.pop(key, None)


def _start_diagnosis(
    uploaded_files: list,
    subtitle_file: Optional[object],
    mode: str,
    editing_mode: str,
    video_type_label: str,
):
    """启动诊断任务(后台线程)"""

    task_id = str(uuid.uuid4())
    st.session_state["current_task_id"] = task_id
    st.session_state["diagnosis_in_progress"] = True
    # 在全局 state 中初始化任务（供后端 service 和前端轮询共用）
    state.update_task(task_id, state=const.TASK_STATE_PROCESSING, progress=0, message="初始化...")

    # 保存上传的视频到临时目录
    temp_dir = f"storage/temp/diagnosis/{task_id}"
    os.makedirs(temp_dir, exist_ok=True)

    saved_video_paths = []
    for uploaded_file in uploaded_files:
        save_path = os.path.join(temp_dir, uploaded_file.name)
        with open(save_path, "wb") as f:
            f.write(uploaded_file.read())
        saved_video_paths.append(save_path)

    # 保存字幕文件(如果有)
    saved_subtitle_path = None
    if subtitle_file:
        saved_subtitle_path = os.path.join(temp_dir, subtitle_file.name)
        with open(saved_subtitle_path, "wb") as f:
            f.write(subtitle_file.read())

    def _run_diagnosis():
        """在线程中运行异步诊断任务

        注意: 不再直接写 st.session_state（非线程安全）。
        所有进度和结果通过全局 state 对象传递，前端轮询读取。
        """
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            from app.services.video_diagnosis.service import VideoDiagnosisService

            service = VideoDiagnosisService()

            loop.run_until_complete(
                service.diagnose(
                    video_path=saved_video_paths[0],
                    task_id=task_id,
                    subtitle_path=saved_subtitle_path,
                    mode=_resolve_analysis_mode(mode),
                    editing_mode="aggressive" if "激进" in editing_mode else "conservative",
                    video_type=VIDEO_TYPE_LABELS.get(video_type_label, "general"),
                )
            )
            # 成功时 service 已通过 state.update_task 写入 COMPLETE + result_path
        except Exception as e:
            logger.error(f"诊断失败: {e}")
            # 失败时 service 已写入 FAILED，这里做兜底确保状态一致
            current = state.get_task(task_id)
            if current and current.get("state") != const.TASK_STATE_FAILED:
                state.update_task(
                    task_id,
                    state=const.TASK_STATE_FAILED,
                    progress=0,
                    message=f"诊断失败: {e}",
                )
        finally:
            loop.close()

    thread = threading.Thread(target=_run_diagnosis, daemon=True)
    thread.start()

    st.rerun()


def _resolve_analysis_mode(label: str) -> str:
    if "快速" in label:
        return "fast"
    if "深度" in label:
        return "deep"
    return "standard"


def _execute_smart_editing(result: dict):
    """执行智能剪辑"""
    task_id = result.get("task_id")
    editing_plan = result.get("editing_plan")

    if not editing_plan:
        st.warning("暂无剪辑方案")
        return

    st.info("正在执行智能剪辑...")
    # TODO: 将 editing_plan 转换为 VideoClipParams 并调用 task.start_subclip_unified
    logger.info(f"智能剪辑任务(task_id={task_id}), editing_plan={editing_plan}")
