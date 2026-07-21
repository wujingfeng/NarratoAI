#!/usr/bin/env python
# -*- coding: UTF-8 -*-

'''
@Project: NarratoAI
@File   : 短剧解说脚本生成
@Author : 小林同学
@Date   : 2025/5/10 下午10:26 
'''
import os
import json
import time
import traceback
import html
import streamlit as st
from loguru import logger

from app.config import config
from app.services.SDE.short_drama_explanation import (
    analyze_subtitle,
    generate_narration_copy as generate_narration_copy_legacy,
    match_narration_copy_to_script as match_narration_copy_to_script_legacy,
)
from app.services.short_drama_narration_service import (
    ShortDramaAnalysisRequest,
    ShortDramaNarrationError,
    build_combined_subtitle_content as _service_build_combined_subtitle_content,
    build_narration_char_range as _service_build_narration_char_range,
    build_narration_char_range_for_video_paths as _service_build_narration_char_range_for_video_paths,
    build_short_drama_script,
    normalize_paths as _service_normalize_paths,
    parse_and_fix_json as _service_parse_and_fix_json,
)
from app.services.tavily_search import TavilySearchError, format_search_context, search_story_context
# 导入新的LLM服务模块 - 确保提供商被注册
import app.services.llm  # 这会触发提供商注册
from app.services.llm.migration_adapter import SubtitleAnalyzerAdapter


PUBLIC_SCRIPT_FIELDS = ["_id", "video_id", "video_name", "timestamp", "picture", "narration", "OST"]
SHORT_DRAMA_PROMPT_CATEGORY = "short_drama_narration"
FILM_TV_PROMPT_CATEGORY = "film_tv_narration"
SHORT_DRAMA_SEARCH_KEYWORDS = "短剧 剧情 介绍 人物 结局"
FILM_TV_SEARCH_KEYWORDS = "影视 剧情 介绍 人物 结局 电影 电视剧"

# 保留 WebUI 既有 helper 名称，具体实现由纯 Python 服务提供。
_normalize_paths = _service_normalize_paths
build_narration_char_range = _service_build_narration_char_range
build_narration_char_range_for_video_paths = _service_build_narration_char_range_for_video_paths
_build_combined_subtitle_content = _service_build_combined_subtitle_content


def _format_progress_status(progress, message: str = "", tr=lambda key: key):
    message = str(message or "").strip()
    if message:
        return message
    return f"{tr('Progress')}: {progress}%"


parse_and_fix_json = _service_parse_and_fix_json


def _script_error_message_key(error: ShortDramaNarrationError) -> str:
    """将纯服务失败原因映射为 WebUI 既有提示文案。"""

    if error.reason == "missing_items":
        return "Generated narration missing items field"
    return "Generated narration JSON parse failed"


def _get_tavily_api_key() -> str:
    return (
        st.session_state.get("tavily_api_key")
        or config.app.get("tavily_api_key")
        or ""
    ).strip()


def _build_tavily_context(
    title: str,
    tr=lambda key: key,
    search_keywords: str = SHORT_DRAMA_SEARCH_KEYWORDS,
    empty_title_message_key: str = "Please enter short drama name before web search",
) -> str | None:
    title = str(title or "").strip()
    if not title:
        st.error(tr(empty_title_message_key))
        return None

    api_key = _get_tavily_api_key()
    if not api_key:
        st.error(tr("Please configure Tavily API Key in Basic Settings"))
        return None

    try:
        search_data = search_story_context(
            title,
            api_key,
            search_keywords=search_keywords,
            empty_name_message=tr(empty_title_message_key),
            search_depth=config.app.get("tavily_search_depth", "basic"),
            max_results=config.app.get("tavily_max_results", 5),
        )
        return format_search_context(search_data)
    except TavilySearchError as e:
        logger.error(f"Tavily 短剧检索失败: {str(e)}")
        st.error(f"{tr('Tavily search failed')}: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Tavily 短剧检索异常: {traceback.format_exc()}")
        st.error(f"{tr('Tavily search failed')}: {str(e)}")
        return None


def _build_plot_analysis_input(
    subtitle_content: str,
    short_name: str = "",
    enable_web_search: bool = False,
    tr=lambda key: key,
    search_keywords: str = SHORT_DRAMA_SEARCH_KEYWORDS,
    empty_title_message_key: str = "Please enter short drama name before web search",
    web_search_context_description: str = "短剧名称、人物关系、剧情背景和公开剧情梗概",
) -> str | None:
    subtitle_content = str(subtitle_content or "").strip()
    if not enable_web_search:
        return subtitle_content

    tavily_context = _build_tavily_context(
        short_name,
        tr,
        search_keywords=search_keywords,
        empty_title_message_key=empty_title_message_key,
    )
    if tavily_context is None:
        return None

    return f"""# 分析补充说明
请先参考 Tavily 联网检索结果理解{web_search_context_description}，再结合原始字幕完成剧情理解。
如果联网检索结果与字幕内容冲突，请以字幕内容为准；时间戳必须只从字幕内容中提取。

{tavily_context}

# 原始字幕
{subtitle_content}"""


def analyze_short_drama_plot(
    subtitle_path,
    temperature,
    tr=lambda key: key,
    subtitle_content=None,
    short_name: str = "",
    enable_web_search: bool = False,
    video_paths=None,
    prompt_category: str = SHORT_DRAMA_PROMPT_CATEGORY,
    search_keywords: str = SHORT_DRAMA_SEARCH_KEYWORDS,
    empty_title_message_key: str = "Please enter short drama name before web search",
    web_search_context_description: str = "短剧名称、人物关系、剧情背景和公开剧情梗概",
):
    """仅执行短剧字幕剧情理解，返回可编辑的剧情分析文本。"""
    subtitle_paths = _normalize_paths(subtitle_path)
    if not subtitle_paths:
        st.error(tr("Please generate or upload subtitles first"))
        return None
    missing_subtitle_paths = [path for path in subtitle_paths if not os.path.exists(path)]
    if missing_subtitle_paths:
        st.error(tr("Subtitle file does not exist"))
        return None

    text_provider = config.app.get('text_llm_provider', 'gemini').lower()
    text_api_key = config.app.get(f'text_{text_provider}_api_key')
    text_model = config.app.get(f'text_{text_provider}_model_name')
    text_base_url = config.app.get(f'text_{text_provider}_base_url')

    subtitle_content = str(subtitle_content or "").strip() or _build_combined_subtitle_content(
        subtitle_paths,
        video_paths,
    )
    if not subtitle_content:
        st.error(tr("Subtitle file is empty or unreadable"))
        return None

    plot_analysis_input = _build_plot_analysis_input(
        subtitle_content,
        short_name=short_name,
        enable_web_search=enable_web_search,
        tr=tr,
        search_keywords=search_keywords,
        empty_title_message_key=empty_title_message_key,
        web_search_context_description=web_search_context_description,
    )
    if plot_analysis_input is None:
        return None

    try:
        logger.info("使用新的LLM服务架构进行字幕分析")
        analyzer = SubtitleAnalyzerAdapter(
            text_api_key,
            text_model,
            text_base_url,
            text_provider,
            prompt_category=prompt_category,
        )
        analysis_result = analyzer.analyze_subtitle(plot_analysis_input)
    except Exception as e:
        logger.warning(f"使用新LLM服务失败，回退到旧实现: {str(e)}")
        analysis_result = analyze_subtitle(
            subtitle_content=plot_analysis_input,
            api_key=text_api_key,
            model=text_model,
            base_url=text_base_url,
            save_result=True,
            temperature=temperature,
            provider=text_provider,
            prompt_category=prompt_category,
        )

    if analysis_result["status"] != "success":
        logger.error(f"分析失败: {analysis_result['message']}")
        st.error(tr("Script generation failed check logs"))
        return None

    return analysis_result["analysis"]


def generate_short_drama_narration_copy(
    subtitle_path,
    video_theme,
    temperature,
    tr=lambda key: key,
    plot_analysis=None,
    subtitle_content=None,
    enable_web_search: bool = False,
    video_paths=None,
    narration_language: str = "简体中文（中国）",
    drama_genre: str = "逆袭/复仇",
    original_sound_ratio: int = 30,
    prompt_category: str = SHORT_DRAMA_PROMPT_CATEGORY,
    search_keywords: str = SHORT_DRAMA_SEARCH_KEYWORDS,
    empty_title_message_key: str = "Please enter short drama name before web search",
    web_search_context_description: str = "短剧名称、人物关系、剧情背景和公开剧情梗概",
):
    """生成可由用户审核修改的短剧解说正文，不绑定时间戳。"""
    subtitle_paths = _normalize_paths(subtitle_path)
    if not subtitle_paths:
        st.error(tr("Please generate or upload subtitles first"))
        return None
    missing_subtitle_paths = [path for path in subtitle_paths if not os.path.exists(path)]
    if missing_subtitle_paths:
        st.error(tr("Subtitle file does not exist"))
        return None

    selected_video_paths = _normalize_paths(video_paths)
    subtitle_content = str(subtitle_content or "").strip() or _build_combined_subtitle_content(
        subtitle_paths,
        selected_video_paths,
    )
    if not subtitle_content:
        st.error(tr("Subtitle file is empty or unreadable"))
        return None

    narration_char_range = build_narration_char_range_for_video_paths(
        selected_video_paths,
        prompt_category=prompt_category,
        original_sound_ratio=original_sound_ratio,
    )
    if narration_char_range:
        logger.info(f"动态解说文案字数范围: {narration_char_range}")

    analysis_text = str(plot_analysis or "").strip()
    if not analysis_text:
        analysis_text = analyze_short_drama_plot(
            subtitle_paths,
            temperature,
            tr,
            subtitle_content=subtitle_content,
            short_name=video_theme,
            enable_web_search=enable_web_search,
            video_paths=selected_video_paths,
            prompt_category=prompt_category,
            search_keywords=search_keywords,
            empty_title_message_key=empty_title_message_key,
            web_search_context_description=web_search_context_description,
        )
        if not analysis_text:
            return None

    text_provider = config.app.get('text_llm_provider', 'gemini').lower()
    text_api_key = config.app.get(f'text_{text_provider}_api_key')
    text_model = config.app.get(f'text_{text_provider}_model_name')
    text_base_url = config.app.get(f'text_{text_provider}_base_url')

    try:
        logger.info("使用新的LLM服务架构生成可审核解说文案")
        analyzer = SubtitleAnalyzerAdapter(
            text_api_key,
            text_model,
            text_base_url,
            text_provider,
            prompt_category=prompt_category,
        )
        narration_result = analyzer.generate_narration_copy(
            short_name=video_theme,
            plot_analysis=analysis_text,
            subtitle_content=subtitle_content,
            temperature=temperature,
            narration_language=narration_language,
            drama_genre=drama_genre,
            narration_char_range=narration_char_range,
        )
    except Exception as e:
        logger.warning(f"使用新LLM服务生成文案失败，回退到旧实现: {str(e)}")
        narration_result = generate_narration_copy_legacy(
            short_name=video_theme,
            plot_analysis=analysis_text,
            subtitle_content=subtitle_content,
            api_key=text_api_key,
            model=text_model,
            base_url=text_base_url,
            temperature=temperature,
            provider=text_provider,
            narration_language=narration_language,
            drama_genre=drama_genre,
            narration_char_range=narration_char_range,
            prompt_category=prompt_category,
        )

    if narration_result.get("status") != "success":
        logger.error(f"解说文案正文生成失败: {narration_result.get('message')}")
        st.error(tr("Script generation failed check logs"))
        return None

    narration_copy = str(narration_result.get("narration_copy", "")).strip()
    if not narration_copy:
        logger.error("模型返回空解说文案正文")
        st.error(tr("Generated narration copy is empty"))
        return None

    return {
        "narration_copy": narration_copy,
        "plot_analysis": analysis_text,
        "subtitle_content": subtitle_content,
    }


def generate_script_short_sunmmary(
    params,
    subtitle_path,
    video_theme,
    temperature,
    tr=lambda key: key,
    plot_analysis=None,
    subtitle_content=None,
    enable_web_search: bool = False,
    video_paths=None,
    narration_language: str = "简体中文（中国）",
    narration_copy: str = "",
    drama_genre: str = "逆袭/复仇",
    original_sound_ratio: int = 30,
    prompt_category: str = SHORT_DRAMA_PROMPT_CATEGORY,
    search_keywords: str = SHORT_DRAMA_SEARCH_KEYWORDS,
    empty_title_message_key: str = "Please enter short drama name before web search",
    web_search_context_description: str = "短剧名称、人物关系、剧情背景和公开剧情梗概",
):
    """
    生成 短剧解说 视频脚本
    要求: 提供高质量短剧字幕
    适合场景: 短剧
    """
    progress_bar = st.empty()
    status_text = st.empty()
    stream_text = st.empty()
    stream_state = {
        "reasoning": "",
        "content": "",
        "last_update": 0.0,
    }

    def update_progress(progress: float, message: str = ""):
        progress_bar.progress(progress)
        status_text.text(_format_progress_status(progress, message, tr))

    def update_waiting(message: str = ""):
        progress_bar.empty()
        if message:
            status_text.text(message)
        else:
            status_text.empty()

    def update_stream_window(event):
        event = event or {}
        chunk_type = str(event.get("type") or "content")
        chunk_text = str(event.get("text") or "")
        if chunk_type == "done" or not chunk_text:
            return

        bucket = "reasoning" if chunk_type == "reasoning" else "content"
        stream_state[bucket] += chunk_text

        now = time.time()
        if now - stream_state["last_update"] < 0.12:
            return
        stream_state["last_update"] = now

        blocks = []
        if stream_state["reasoning"].strip():
            blocks.append(
                f"{tr('Model reasoning stream')}\n"
                f"{stream_state['reasoning'][-900:]}"
            )
        if stream_state["content"].strip():
            blocks.append(
                f"{tr('Model output preview')}\n"
                f"{stream_state['content'][-900:]}"
            )

        preview = "\n\n".join(blocks)[-1800:]
        escaped_preview = html.escape(preview)
        stream_text.markdown(
            f"""
            <div style="height:150px; overflow:hidden; border:1px solid #e5e7eb;
                        border-radius:8px; padding:10px 12px; background:#f8fafc;
                        color:#334155;">
              <div style="font-size:12px; font-weight:600; color:#64748b; margin-bottom:6px;">
                {html.escape(tr('LLM stream window title'))}
              </div>
              <pre style="white-space:pre-wrap; margin:0; font-size:12px; line-height:1.45;
                          font-family:ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;">{escaped_preview}</pre>
            </div>
            """,
            unsafe_allow_html=True,
        )

    try:
        with st.spinner(tr("Generating script...")):
            selected_video_paths = _normalize_paths(
                video_paths
                or getattr(params, "video_origin_paths", [])
                or getattr(params, "video_origin_path", "")
            )
            if not selected_video_paths:
                st.error(tr("Please select video file first"))
                return
            """
            1. 获取字幕
            """
            update_progress(30, tr("Parsing subtitles..."))
            # 判断字幕文件是否存在
            subtitle_paths = _normalize_paths(subtitle_path)
            missing_subtitle_paths = [path for path in subtitle_paths if not os.path.exists(path)]
            if not subtitle_paths or missing_subtitle_paths:
                st.error(tr("Subtitle file does not exist"))
                return

            """
            2. 分析字幕总结剧情 - 使用新的LLM服务架构
            """
            text_provider = config.app.get('text_llm_provider', 'gemini').lower()
            text_api_key = config.app.get(f'text_{text_provider}_api_key')
            text_model = config.app.get(f'text_{text_provider}_model_name')
            text_base_url = config.app.get(f'text_{text_provider}_base_url')

            # 读取字幕文件内容（无论使用哪种实现都需要）
            subtitle_content = str(subtitle_content or "").strip() or _build_combined_subtitle_content(
                subtitle_paths,
                selected_video_paths,
            )
            if not subtitle_content:
                st.error(tr("Subtitle file is empty or unreadable"))
                return

            narration_copy = str(narration_copy or "").strip()
            if not narration_copy:
                st.error(tr("Please generate and review narration copy first"))
                return

            analyzer = SubtitleAnalyzerAdapter(
                text_api_key,
                text_model,
                text_base_url,
                text_provider,
                prompt_category=prompt_category,
            )
            if plot_analysis and str(plot_analysis).strip():
                logger.info("使用用户编辑后的剧情理解结果匹配剪辑脚本")
                analysis_result = {
                    "status": "success",
                    "analysis": str(plot_analysis).strip(),
                }
            else:
                plot_analysis_input = subtitle_content
                if enable_web_search:
                    update_waiting(tr("Searching short drama with Tavily..."))
                    plot_analysis_input = _build_plot_analysis_input(
                        subtitle_content,
                        short_name=video_theme,
                        enable_web_search=True,
                        tr=tr,
                        search_keywords=search_keywords,
                        empty_title_message_key=empty_title_message_key,
                        web_search_context_description=web_search_context_description,
                    )
                    if plot_analysis_input is None:
                        return
                try:
                    # 优先使用新的LLM服务架构
                    logger.info("使用新的LLM服务架构进行字幕分析")
                    update_waiting(tr("Analyzing subtitles with model..."))
                    analysis_result = analyzer.analyze_subtitle(plot_analysis_input)

                except Exception as e:
                    logger.warning(f"使用新LLM服务失败，回退到旧实现: {str(e)}")
                    # 回退到旧的实现
                    update_waiting(tr("Analyzing subtitles with model..."))
                    analysis_result = analyze_subtitle(
                        subtitle_content=plot_analysis_input,
                        api_key=text_api_key,
                        model=text_model,
                        base_url=text_base_url,
                        save_result=True,
                        temperature=temperature,
                        provider=text_provider,
                        prompt_category=prompt_category,
                    )
            """
            3. 根据用户审核后的文案匹配画面与时间戳
            """
            if analysis_result["status"] == "success":
                logger.info("字幕分析成功！")
                update_waiting()

                try:
                    logger.info("使用新的LLM服务架构将审核文案匹配到字幕画面")
                    update_waiting(tr("Matching narration copy to footage..."))
                    stream_text.info(tr("Waiting for model stream..."))
                    narration_result = analyzer.match_narration_copy_to_script(
                        short_name=video_theme,
                        plot_analysis=analysis_result["analysis"],
                        subtitle_content=subtitle_content,
                        narration_copy=narration_copy,
                        temperature=temperature,
                        narration_language=narration_language,
                        drama_genre=drama_genre,
                        original_sound_ratio=original_sound_ratio,
                        stream_callback=update_stream_window,
                    )
                except Exception as e:
                    logger.warning(f"使用新LLM服务匹配画面失败，回退到旧实现: {str(e)}")
                    stream_text.info(tr("Streaming unavailable fallback waiting..."))
                    narration_result = match_narration_copy_to_script_legacy(
                        short_name=video_theme,
                        plot_analysis=analysis_result["analysis"],
                        subtitle_content=subtitle_content,
                        narration_copy=narration_copy,
                        api_key=text_api_key,
                        model=text_model,
                        base_url=text_base_url,
                        temperature=temperature,
                        provider=text_provider,
                        narration_language=narration_language,
                        drama_genre=drama_genre,
                        original_sound_ratio=original_sound_ratio,
                        prompt_category=prompt_category,
                    )

                if narration_result["status"] == "success":
                    logger.info("\n剪辑脚本匹配成功！")
                    logger.info(narration_result["narration_script"])
                else:
                    logger.info(f"\n剪辑脚本匹配失败: {narration_result['message']}")
                    st.error(tr("Script generation failed check logs"))
                    st.stop()
            else:
                logger.error(f"分析失败: {analysis_result['message']}")
                st.error(tr("Script generation failed check logs"))
                st.stop()

            """
            4. 生成文案
            """
            logger.info("开始准备生成解说文案")

            try:
                narration_items = build_short_drama_script(
                    ShortDramaAnalysisRequest(
                        video_paths=selected_video_paths,
                        narration_result=narration_result,
                    )
                )
            except ShortDramaNarrationError as exc:
                st.error(tr(_script_error_message_key(exc)))
                logger.error(f"短剧脚本归一化失败: {exc}")
                st.stop()
            script = json.dumps(narration_items, ensure_ascii=False, indent=2)

            if script is None:
                st.error(tr("Script generation failed check logs"))
                st.stop()
            logger.success(f"剪辑脚本生成完成")
            if isinstance(script, list):
                st.session_state['video_clip_json'] = script
            elif isinstance(script, str):
                st.session_state['video_clip_json'] = json.loads(script)
            update_progress(90, tr("Preparing output..."))

        time.sleep(0.1)
        progress_bar.progress(100)
        status_text.text(tr("Script generation completed!"))
        st.success(tr("Video script generated successfully"))

    except Exception as err:
        st.error(f"{tr('Generation error')}: {str(err)}")
        logger.exception(f"生成脚本时发生错误\n{traceback.format_exc()}")
    finally:
        time.sleep(2)
        progress_bar.empty()
        status_text.empty()
        stream_text.empty()
