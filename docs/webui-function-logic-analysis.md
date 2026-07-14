# NarratoAI WebUI 功能与底层逻辑梳理

生成日期：2026-07-01  
分析范围：当前仓库代码，重点覆盖 `webui.py`、`webui/components/*`、`webui/tools/*`、`app/services/*`、`app/config/*`、部署与诊断相关文件。  
结论性质：只读代码分析，不包含业务代码修改；涉及 API Key 的配置只描述字段和链路，不记录密钥值。

## 1. 总体结论

NarratoAI 当前 WebUI 是一个 Streamlit 单页应用，不是传统前后端分离架构，也没有独立 HTTP API controller 层。用户在页面上的操作直接触发 Python 函数，主要通过三类状态连接到底层服务：

- `st.session_state`：保存当前页面选择、上传文件路径、生成脚本、字幕内容、TTS 参数等运行时状态。
- `config.toml` 对应的 `app.config.config` 全局配置字典：保存 LLM、TTS、代理、剪映草稿目录、字幕遮罩、FFmpeg 路径等配置。
- 本地文件目录：视频、字幕、脚本、任务产物都落在 `resource/` 或 `storage/` 下，再由后续流程读取。

主流程分两段：

1. 脚本阶段：选择/上传/生成剪辑脚本，脚本先进入 `st.session_state["video_clip_json"]`，用户需要通过脚本编辑弹窗里的保存逻辑落成 `resource/scripts/*.json`。
2. 生成阶段：点击“生成视频”后读取已保存的脚本 JSON，构造 `VideoClipParams`，后台线程执行 `app.services.task.start_subclip_unified()`，生成最终 MP4。

另有一个并行导出能力：点击“导出剪映草稿”不会生成最终 MP4，也不会预裁剪视频，而是生成 TTS 音频、字幕和剪映草稿时间线，写入用户配置的剪映草稿目录。

## 2. 入口与页面结构

### 2.1 启动入口

本地启动入口：

- `README.md`：推荐 `streamlit run webui.py --server.maxUploadSize=2048`
- `webui.py`：主应用入口，`if __name__ == "__main__": main()`

Docker 启动入口：

- `Dockerfile`：`ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]`，默认 `CMD ["webui"]`
- `docker-entrypoint.sh`：`start_webui()` 最终执行 `streamlit run webui.py --server.address=0.0.0.0 --server.port=8501 --server.maxUploadSize=2048`
- `docker-compose.yml`：挂载 `storage/`、`resource/`、`config.toml`，暴露 `8501:8501`

### 2.2 `webui.py -> main()` 的渲染顺序

`webui.py` 的 `main()` 做这些事：

1. `init_log()` 初始化 Loguru 输出格式。
2. `init_global_state()` 初始化 `video_clip_json`、`video_plot`、`ui_language`。
3. 调用 `app.services.llm.providers.register_all_providers()` 注册 LLM provider。
4. 调用 `ffmpeg_utils.detect_hardware_acceleration()` 检测 FFmpeg 硬件加速。
5. 调用 `utils.init_resources()` 初始化资源目录。
6. 渲染标题与帮助文案。
7. 渲染基础设置面板 `basic_settings.render_basic_settings()`。
8. 三列布局：
   - 左列：`script_settings.render_script_panel()`
   - 中列：`audio_settings.render_audio_panel()`
   - 右列：`video_settings.render_video_panel()`、`subtitle_settings.render_subtitle_panel()`、`system_settings.render_system_panel()`
9. 底部渲染：
   - `render_generate_button()`
   - `render_export_jianying_button()`

主页面没有 Streamlit 多页面路由，也没有主页面级 `st.tabs`；只有字幕遮罩弹窗内有横屏/竖屏 Tab。`webui/components/ffmpeg_diagnostics.py` 有独立诊断页 Tab，但当前没有接入 `webui.py` 主界面。

## 3. 资源目录与状态模型

### 3.1 常用目录函数

来自 `app/utils/utils.py`：

- `root_dir()`：项目根目录。
- `storage_dir(sub_dir="", create=False)`：`storage/` 下的运行产物目录。
- `resource_dir(sub_dir="")`：`resource/` 下的资源目录。
- `video_dir()`：`resource/videos`
- `script_dir()`：`resource/scripts`
- `subtitle_dir()`：`resource/srt`
- `font_dir()`：`resource/fonts`
- `song_dir()`：`resource/songs`
- `task_dir(task_id)`：`storage/tasks/{task_id}`
- `temp_dir(sub_dir="")`：`storage/temp/{sub_dir}`

### 3.2 关键 session_state 字段

脚本/视频：

- `video_clip_json_path`：脚本模式或脚本 JSON 文件路径。特殊值包括 `film_summary`、`summary`、`auto`、`short`。
- `video_clip_json`：当前生成/加载/编辑中的脚本 JSON 数据。
- `video_origin_path`：第一个原视频路径。
- `video_origin_paths`：多视频路径列表。
- `video_theme`：影视/短剧名称或视频主题。
- `custom_prompt`：纪录片/画面解说自定义提示词。

字幕：

- `subtitle_path`：第一个字幕文件路径。
- `subtitle_paths`：多字幕文件路径。
- `subtitle_content`：合并后的字幕文本。
- `subtitle_contents`：每个字幕文件的文本映射。
- `subtitle_file_processed`：上传/转写处理标记。

音频：

- `tts_engine`：当前 TTS 引擎。
- `voice_rate`、`voice_pitch`、`voice_volume`
- `bgm_source`、`bgm_type`、`bgm_file`、`bgm_name`、`bgm_volume`

字幕样式：

- `subtitle_enabled`
- `subtitle_mask_enabled`
- `subtitle_auto_transcribe_enabled`
- `font_name`、`font_size`、`text_fore_color`
- `subtitle_position`、`custom_position`
- `stroke_color`、`stroke_width`

任务状态：

- `task_id`：剪映导出时保存当前任务 id。
- 生成视频的进度不主要存在 session，而是存在 `app.services.state.state`。

## 4. WebUI 操作到底层实现映射

| WebUI 操作 | 前端入口 | 关键状态/参数 | 底层实现 | 产物/副作用 |
|---|---|---|---|---|
| 切换语言 | `basic_settings.render_language_settings()` | `ui_language`、`config.ui["language"]` | `utils.load_locales()` 读取 `webui/i18n/*.json` | 改变翻译文案；不立即强制保存除非其他逻辑触发 `save_config()` |
| 开关代理 | `basic_settings.render_proxy_settings()` | `config.proxy`、环境变量 `HTTP_PROXY`/`HTTPS_PROXY` | 直接写 `os.environ` | 影响后续网络请求 |
| 配置剪映目录 | `basic_settings.render_proxy_settings()` | `config.ui["jianying_draft_path"]` | 文本输入保存到配置字典 | 导出剪映前校验该路径 |
| 配置 Tavily | `basic_settings.render_tavily_search_settings()` | `config.app["tavily_api_key"]` | `config.save_config()` | 影视/短剧剧情理解可启用联网搜索 |
| 配置视觉模型 | `basic_settings.render_vision_llm_settings()` | `vision_openai_*` | `test_openai_compatible_vision_model()` 可测试连接 | 保存后 `UnifiedLLMService.clear_cache()` |
| 配置文案模型 | `basic_settings.render_text_llm_settings()` | `text_openai_*` | `test_openai_compatible_text_model()` 可测试连接 | 保存后清理 LLM cache |
| 选择脚本模式 | `script_settings.render_script_file()` | `video_clip_json_path` | 特殊值驱动后续 UI 分支 | 决定显示影视解说/短剧解说/画面解说/短剧混剪/文件选择 |
| 上传脚本 JSON | `render_script_file()` | `video_clip_json_path` | `json.loads()` 校验后写入 `utils.script_dir()` | `resource/scripts/*.json` |
| 选择已有脚本 | `render_script_file()` | `video_clip_json_path` | 扫描 `utils.script_dir()` | 后续“加载脚本”读取该文件 |
| 上传视频 | `render_video_file()` | `video_origin_paths`、`uploaded_video_signature` | 写入 `utils.video_dir()` | `resource/videos/*` |
| 选择资源视频 | `render_video_file()` | `video_origin_path(s)` | 扫描 `utils.video_dir()` | 后续脚本生成、转写、剪辑读取 |
| 字幕上传 | `render_subtitle_upload()` | `subtitle_path(s)`、`subtitle_content(s)` | `decode_subtitle_bytes()` 后写入 `utils.subtitle_dir()` | `resource/srt/*.srt` |
| Fun-ASR 转字幕 | `render_fun_asr_transcription()` | `config.fun_asr`、`subtitle_path(s)` | `fun_asr_subtitle.create_with_local_fun_asr()` / `create_with_local_firered_asr()` / `create_with_fun_asr()` | `resource/srt/*_fun_asr.srt` 或 `*_firered_asr.srt` |
| 字幕翻译 | `render_fun_asr_transcription()` | 目标语言、字幕路径 | `subtitle_translator.translate_subtitle_file()` | `resource/srt/*_translated_*.srt` |
| 字幕校准 | `render_fun_asr_transcription()` | 字幕路径、文本 LLM 配置 | `subtitle_corrector.correct_subtitle_file()` | `resource/srt/*_corrected.srt` |
| 剧情理解 | `summary_narration_panel()` | 字幕、片名、Tavily 开关 | `analyze_short_drama_plot()` -> `SubtitleAnalyzerAdapter.analyze_subtitle()`，失败回退 SDE 旧实现 | 写入 `{short_drama|film_tv}_plot_analysis` |
| 生成解说文案 | `render_script_buttons()` | 剧情理解、字幕、类型、语言 | `generate_short_drama_narration_copy()` -> `SubtitleAnalyzerAdapter.generate_narration_copy()`，失败回退旧实现 | 写入 `{short_drama|film_tv}_narration_copy` |
| 生成剪辑脚本 | `render_script_buttons()` | 审核后的解说文案、字幕、原片占比 | `generate_script_short_sunmmary()` -> `SubtitleAnalyzerAdapter.match_narration_copy_to_script()`，失败回退旧实现 | 写入 `video_clip_json`，尚未落文件 |
| 画面解说脚本 | `generate_script_docu()` | 视频、主题、自定义 prompt、帧间隔、视觉模型配置 | `DocumentaryFrameAnalysisService.generate_documentary_script()` | 写入 `video_clip_json` |
| 短剧混剪脚本 | `generate_script_short()` | 视频、字幕、片段数、剧情理解 | `app.services.SDP.generate_script_short.generate_script_result()` | 写入 `video_clip_json` |
| 编辑脚本表格 | `render_video_script_editor()` | `video_clip_json` | `st.data_editor()` 编辑，`_script_table_to_json()` 转 JSON | 保存前只在内存里 |
| 保存脚本 | `save_script_with_validation()` | 编辑后的 JSON 字符串 | `check_script.check_format()` 校验，写入 `utils.script_dir()` | `resource/scripts/{timestamp}.json`，更新 `video_clip_json_path` |
| 加载脚本 | `load_script()` | 脚本文件路径 | `utils.clean_model_output()` + `json.loads()` | 写入 `video_clip_json` |
| 选择 TTS 引擎 | `audio_settings.render_tts_settings()` | `config.ui["tts_engine"]`、`tts_engine` | 分发到各 TTS 设置函数 | 后续 `voice.tts()` / `voice.tts_multiple()` 使用 |
| 试听 TTS | `render_voice_preview_new()` | 当前 TTS 配置 | `voice.tts()` 生成临时音频 | `storage/temp/tmp-voice-*.mp3|wav`，播放后尝试删除 |
| 选择/上传 BGM | `render_bgm_settings()` | `bgm_type`、`bgm_file`、`bgm_volume` | 资源目录或上传到 `storage/uploaded_bgms` | 最终合成时 `utils.get_bgm_file()` 读取 |
| 设置视频比例/画质/原声音量 | `video_settings.render_video_config()` | `video_aspect`、`video_quality`、`original_volume` | `get_video_params()` 汇总 | `video_quality` 当前主合成链路中未明显使用 |
| 字幕遮罩设置 | `subtitle_settings.render_subtitle_mask_settings()` | `subtitle_mask_*` | 预览调用 `generate_video._resolve_subtitle_mask_region()` | 最终合成时 `generate_video.apply_subtitle_mask()` 使用 |
| 最终视频自动转录 | `render_auto_transcription_settings()` | `subtitle_auto_transcribe_*` | 生成阶段由 `task._transcribe_final_video()` 执行 | 只有启用且前面未生成字幕时才执行 |
| 字幕字体/位置/描边 | `render_font_settings()`、`render_position_settings()`、`render_style_settings()` | 字幕样式字段 | 最终传入 `generate_video.merge_materials()` | 影响烧录字幕 |
| 清理临时目录 | `system_settings.render_system_panel()` | 无 | `clear_directory()` | 删除 `storage/temp/keyframes`、`storage/temp/clip_video`、`storage/tasks` |
| 保存/测试 FFmpeg | `render_ffmpeg_engine_settings()` | `config.app["ffmpeg_path"]` | `ffmpeg_detector.discover_ffmpeg_engines()` / `validate_ffmpeg_engine()` / `config.apply_ffmpeg_path()` | 改变当前进程 FFmpeg 路径，保存配置 |
| 生成视频 | `webui.render_generate_button()` | 汇总四组参数成 `VideoClipParams` | `task.start_subclip_unified()` | `storage/tasks/{task_id}/combined.mp4` |
| 导出剪映草稿 | `webui.render_export_jianying_button()` | `VideoClipParams` + `draft_name` | `jianying_task.start_export_jianying_draft()` | 剪映草稿目录下的草稿文件和素材 |

## 5. 脚本类型与生成原理

### 5.1 脚本 JSON 标准结构

核心脚本字段由 `SCRIPT_TABLE_BASE_COLUMNS` 和格式校验约束：

```json
[
  {
    "_id": 1,
    "video_id": 1,
    "video_name": "1.mp4",
    "timestamp": "00:00:00,600-00:00:07,559",
    "picture": "画面描述",
    "narration": "解说文案或播放原片标记",
    "OST": 0
  }
]
```

关键字段语义：

- `_id`：片段序号，也是 TTS、字幕、裁剪结果匹配的重要 key。
- `video_id` / `video_name`：多视频场景下定位素材来源；`clip_video._resolve_script_video_path()` 会优先按显式路径、`video_id`、文件名匹配。
- `timestamp`：原视频时间范围。
- `picture`：画面说明，主要来自 LLM。
- `narration`：TTS 解说内容；`OST=1` 时常见为“播放原片X”。
- `OST`：决定裁剪和音频处理策略。

### 5.2 OST 策略

`app.services.task.start_subclip_unified()` 和 `clip_video.clip_video_unified()` 基于 `OST` 分支：

- `OST=0`：纯解说。为该片段生成 TTS，按 TTS 时长动态裁剪视频，最终不保留原声。
- `OST=1`：纯原声。不会生成 TTS，严格按脚本 `timestamp` 裁剪，保留原视频声音。
- `OST=2`：解说加原声。生成 TTS，按 TTS 时长动态裁剪，同时保留原声。

### 5.3 影视解说 / 短剧解说

WebUI 模式：

- `Film TV Narration`：`video_clip_json_path = "film_summary"`
- `Short Drama Summary`：`video_clip_json_path = "summary"`

两者共用 `webui/tools/generate_short_summary.py` 主流程，区别在 prompt category：

- 影视解说：`film_tv_narration`
- 短剧解说：`short_drama_narration`

流程：

1. 用户上传/转写字幕。
2. 可选启用 Tavily 联网搜索，补充剧情背景。
3. 点击“剧情理解”：`analyze_short_drama_plot()` 调用 `SubtitleAnalyzerAdapter.analyze_subtitle()`，失败时回退 `SDE.short_drama_explanation.analyze_subtitle()`。
4. 点击“生成解说文案”：`generate_short_drama_narration_copy()` 基于剧情理解和字幕生成一段可人工审核的解说正文。
5. 用户可在文本框中编辑文案。
6. 点击“生成剪辑脚本”：`generate_script_short_sunmmary()` 将审核后的文案匹配到字幕时间轴，输出可剪辑 JSON。

重要原则：这类模式不是“一键直接生成最终视频”。它先生成 `video_clip_json`，用户还需要在脚本编辑弹窗里保存成 JSON 文件，底部“生成视频”才会读取该 JSON 文件。

### 5.4 画面解说 / 纪录片脚本

WebUI 模式：

- `Auto Generate`：`video_clip_json_path = "auto"`

入口：

- `webui/tools/generate_script_docu.py::generate_script_docu()`
- `app/services/documentary/frame_analysis_service.py::DocumentaryFrameAnalysisService.generate_documentary_script()`

流程：

1. 根据视频和帧间隔抽取关键帧。
2. 使用视觉 LLM 批量分析画面。
3. 保存 frame analysis JSON。
4. 将分析结果转成 markdown。
5. 使用文本 LLM 生成 `items`。
6. 最终补齐 `OST=2` 等剪辑字段。

注意点：

- `documentary.frame_analysis` prompt 已注册，但核心视觉分析 prompt 当前主要使用服务内置模板。
- explorer 发现 `skip_seconds` / `threshold` 参数会警告但不真正生效。

### 5.5 短剧混剪

WebUI 模式：

- `Short Generate`：`video_clip_json_path = "short"`

入口：

- `webui/tools/generate_script_short.py::generate_script_short()`
- `app/services/SDP/generate_script_short.py::generate_script_result()`

能力：

- 必须有视频和字幕。
- 基于字幕和剧情分析选取原片片段。
- 不生成解说正文。
- 输出通常是 `OST=1`，`narration` 为“播放原片{id}”。

这条链路会读取部分 `vision_*` 配置，但实际生成主要使用文本 LLM，视觉配置读取更像遗留代码。

## 6. LLM 与 Prompt 架构

### 6.1 新 LLM 架构

主架构：

- `app/services/llm/manager.py::LLMServiceManager`
- `app/services/llm/unified_service.py::UnifiedLLMService`
- `app/services/llm/providers/__init__.py::register_all_providers()`

`webui.py` 启动时显式注册 provider。

当前注册范围：

- 文本 provider：`openai`
- 视觉 provider：`openai`、`twelvelabs`

这里的 `openai` 实际是 OpenAI-compatible 统一入口，主要读取：

- `config.app["text_openai_api_key"]`
- `config.app["text_openai_model_name"]`
- `config.app["text_openai_base_url"]`
- `config.app["vision_openai_api_key"]`
- `config.app["vision_openai_model_name"]`
- `config.app["vision_openai_base_url"]`

### 6.2 旧 LLM 接口

`app/services/llm.py` 仍保留旧接口，支持 moonshot、ollama、azure、gemini、qwen、cloudflare、deepseek、ernie 等分支。它不是当前 `LLMServiceManager` 注册体系的一部分，但一些旧实现或回退路径仍可能引用它。

风险点：

- 新旧 provider 支持面不一致。
- 配置命名存在新旧混用。
- 纪录片文本生成适配器的函数签名接收显式 `api_key/base_url/model`，但实际调用 `UnifiedLLMService.generate_text()` 时不一定传入这些显式值，运行上更依赖全局文本 LLM 配置。

### 6.3 Prompt 注册

`app/services/prompts/__init__.py` 会注册：

- `documentary`
- `short_drama_editing`
- `short_drama_narration`
- `film_tv_narration`

主要阶段：

- 纪录片：`narration_generation`
- 短剧混剪：`short_drama_editing.subtitle_analysis` -> `script_generation`
- 短剧/影视解说：`plot_analysis` -> `narration_copy` -> `script_matching`
- 另有 `script_repair`、`segment_planning` 等修复或自动生成辅助 prompt。

## 7. TTS 与音频逻辑

### 7.1 WebUI TTS 设置

入口：`webui/components/audio_settings.py::render_tts_settings()`

当前下拉暴露的 TTS 引擎：

- `indextts`：IndexTTS-1.5，本地/外部 API。
- `indextts2`：IndexTTS-2，本地/外部 API。
- `omnivoice`：OmniVoice，本地/外部 API。
- `edge_tts`：Edge TTS。
- `qwen3_tts`：通义 Qwen3 TTS。
- `tencent_tts`：腾讯云 TTS。
- `doubaotts`：豆包语音。
- `azure_speech`：Azure Speech Services。

代码里存在 `soulvoice` 分支，但当前 `get_tts_engine_options()` 没暴露 `soulvoice`，并且 `render_soulvoice_engine_settings()` 未定义；如果未来重新加入选项，会触发 NameError 风险。

### 7.2 TTS 执行

最终视频和剪映草稿都使用：

- `app/services/voice.py::tts_multiple()`

单段试听使用：

- `app/services/voice.py::tts()`

`tts_multiple()` 只处理 `OST in [0, 2]` 的脚本片段，并为每段生成：

- 音频文件：`storage/tasks/{task_id}/audio_*.mp3|wav`
- 可选 TTS 字幕：`storage/tasks/{task_id}/subtitle_*.srt`
- 时长信息：后续用于裁剪和音频合并。

### 7.3 BGM

WebUI：

- `render_bgm_settings()`

来源：

- 资源目录：当前 BGM 资源目录在代码中硬编码为 `/Users/viccy/Downloads/tts-mp3-clone/bgms-safe`
- 上传文件：写入 `storage/uploaded_bgms`
- 无 BGM：`bgm_type = ""`

最终合成时：

- `task.start_subclip_unified()` 调 `utils.get_bgm_file(bgm_type, bgm_file)` 获取 BGM 文件。

硬编码资源目录会影响部署可移植性。

## 8. 生成最终视频的底层流程

入口：

- `webui.py::render_generate_button()`
- `app/services/task.py::start_subclip_unified()`

### 8.1 WebUI 参数汇总

点击“Generate Video”后：

1. `config.save_config()`
2. 校验 `video_clip_json_path` 不为空。
3. 校验 `video_origin_path` 不为空。
4. 读取四组参数：
   - `script_settings.get_script_params()`
   - `video_settings.get_video_params()`
   - `audio_settings.get_audio_params()`
   - `subtitle_settings.get_subtitle_params()`
5. 合并成 `VideoClipParams(**all_params)`。
6. 创建 `task_id = uuid.uuid4()`。
7. 弹窗内开线程执行 `task.start_subclip_unified(task_id, params)`。
8. 主线程轮询 `app.services.state.state.get_task(task_id)`，更新进度条和状态文案。

### 8.2 任务状态

状态实现：

- `app/services/state.py`

默认使用 `MemoryState`。如果 `config.app["enable_redis"]` 为真，会使用 `RedisState`。

状态码：

- `const.TASK_STATE_FAILED = -1`
- `const.TASK_STATE_COMPLETE = 1`
- `const.TASK_STATE_PROCESSING = 4`

### 8.3 生成阶段

`start_subclip_unified()` 的阶段：

1. 加载脚本 JSON。
2. 为 `OST=0/2` 生成 TTS。
3. 统一裁剪视频。
4. 更新脚本时间戳和产物路径。
5. 合并音频和字幕。
6. 合并视频片段。
7. 合成最终视频。
8. 可选：最终视频自动转录并压入字幕。
9. 更新任务完成状态，返回 `videos`、`combined_videos`、可选 `subtitles`。

### 8.4 关键服务函数

| 阶段 | 函数 | 作用 |
|---|---|---|
| 读取脚本 | `json.load(params.video_clip_json_path)` | 读取剪辑 JSON |
| TTS | `voice.tts_multiple()` | 为 `OST=0/2` 生成配音和字幕 |
| 统一裁剪 | `clip_video.clip_video_unified()` | 按 OST 策略裁剪原视频 |
| 更新脚本 | `update_script.update_script_timestamps()` | 写回 `video/audio/subtitle/duration/editedTimeRange` |
| 合并音频 | `audio_merger.merge_audio_files()` | 生成整条配音轨 |
| 程序化字幕 | `script_subtitle.create_script_subtitle_file()` | 优先根据最终时间线生成字幕 |
| 回退字幕 | `subtitle_merger.merge_subtitle_files()` | 程序化字幕失败时合并 TTS 字幕 |
| 合并片段 | `merger_video.combine_clip_videos()` | 将裁剪片段合成 `merger.mp4` |
| 最终合成 | `generate_video.merge_materials()` | 合成视频、配音、BGM、字幕 |
| 自动转录 | `task._transcribe_final_video()` | 使用 FunASR/FireRed/百炼转写最终视频 |
| 压自动字幕 | `task._merge_auto_transcribed_subtitles()` | 将自动转录字幕烧录进最终视频 |

### 8.5 文件产物

以 `task_id` 为单位：

- TTS 音频：`storage/tasks/{task_id}/audio_*.mp3|wav`
- TTS 字幕：`storage/tasks/{task_id}/subtitle_*.srt`
- 合并音频：`storage/tasks/{task_id}/merger_audio.mp3`
- 程序化字幕：`storage/tasks/{task_id}/script_subtitles.srt`
- 视频片段合并：`storage/tasks/{task_id}/merger.mp4`
- 最终视频：`storage/tasks/{task_id}/combined.mp4`
- 自动转录中间视频：`storage/tasks/{task_id}/combined_without_auto_subtitles.mp4`
- 自动转录字幕：`storage/tasks/{task_id}/auto_transcribed_final.srt`

统一裁剪片段在：

- `storage/temp/clip_video_unified/{hash}/ost{0|1|2}_{id}_vid_{start}@{end}.mp4`

### 8.6 最终合成原理

`generate_video.merge_materials()` 优先走 FFmpeg 快路径，失败时回退 MoviePy。

字幕烧录策略大致是：

1. 优先 `drawtext`
2. 其次 `subtitles` filter
3. 再回退 PNG overlay

字幕遮罩由 `apply_subtitle_mask()` 处理，按横屏/竖屏分别解析遮罩区域，先对原字幕区域做模糊/遮盖，再烧录新字幕。

音量处理：

- `task.start_subclip_unified()` 先获取 `get_recommended_volumes_for_content("mixed")`
- 如果脚本里有 `OST=1` 原声片段，原声音量强制保持 `1.0`
- 否则用户设置优先于默认推荐值

## 9. 导出剪映草稿

入口：

- `webui.py::render_export_jianying_button()`
- `webui.py::_render_jianying_export_dialog()`
- `app/services/jianying_task.py::start_export_jianying_draft()`

### 9.1 WebUI 校验

点击“Export to Jianying Draft”后校验：

1. `video_clip_json_path` 必须存在。
2. `video_origin_path` 必须存在。
3. `config.ui["jianying_draft_path"]` 必须配置。
4. 剪映草稿目录必须存在。
5. 弹窗中草稿名称不能为空。

### 9.2 草稿生成流程

`start_export_jianying_draft()`：

1. 读取脚本 JSON。
2. 为 `OST=0/2` 生成 TTS。
3. `_build_jianying_draft_script()` 直接引用原视频和源时间戳，不预裁剪视频。
4. `_create_jianying_subtitle_file()` 尝试生成字幕。
5. `write_plaintext_jianying_draft()` 写剪映草稿文件。

关键区别：

- 最终视频生成会真实裁剪和合成 MP4。
- 剪映导出不裁剪视频，而是把原视频素材、TTS 音频、字幕、时间线信息写进草稿。

### 9.3 草稿产物

写入目录：

- `{config.ui["jianying_draft_path"]}/{draft_name}`

主要文件：

- `draft_info.json`
- `draft_meta_info.json`
- `template-2.tmp`
- `template.tmp`
- `draft_settings`
- `draft_cover.jpg`
- `attachment_editing.json`
- `timeline_layout.json`
- `assets/video/*`
- `assets/audio/*`

## 10. 系统设置与 FFmpeg

### 10.1 清理按钮

`system_settings.render_system_panel()` 提供：

- Clear frames：删除 `storage/temp/keyframes`
- Clear clip videos：删除 `storage/temp/clip_video`
- Clear tasks：删除 `storage/tasks`

注意：当前统一裁剪产物目录是 `storage/temp/clip_video_unified`，清理按钮只清 `clip_video`，不一定覆盖统一裁剪目录。

### 10.2 FFmpeg 引擎检测

`render_ffmpeg_engine_settings()`：

1. `ffmpeg_detector.discover_ffmpeg_engines()` 搜索可用 FFmpeg：
   - 已配置路径
   - 整合包 runtime
   - Python 环境
   - `IMAGEIO_FFMPEG_EXE`
   - 系统 PATH
   - Homebrew
   - `/usr/bin`
   - `imageio-ffmpeg`
2. 用户可选择或输入自定义路径。
3. 保存后写入 `config.app["ffmpeg_path"]`。
4. 调用 `config.apply_ffmpeg_path()` 设置当前进程环境。
5. 调用 `ffmpeg_utils.reset_hwaccel_detection()` 清理硬件加速缓存。
6. “Test Selected FFmpeg” 调 `ffmpeg_detector.validate_ffmpeg_engine()` 输出详细报告。

启动时 `webui.py` 也会调用 `ffmpeg_utils.detect_hardware_acceleration()`，用于日志和后续编码策略判断。

## 11. 配置读取与持久化

主配置文件：

- `config.toml`

如果不存在：

- `app/config/config.py::load_config()` 会从 `config.example.toml` 构建默认配置并写入。

主要配置段：

- `[app]`：LLM、Tavily、FFmpeg、隐藏配置、超时重试等。
- `[ui]`：语言、TTS 引擎、字体、字幕遮罩、剪映目录等。
- `[proxy]`：代理。
- `[frames]`：关键帧间隔、视觉批大小、视觉并发。
- `[fun_asr]`：字幕转写配置。
- `[azure]`、`[tencent]`、`[tts_qwen]`、`[doubaotts]`、`[soulvoice]`：云 TTS 配置。
- `[indextts]`、`[indextts2]`、`[omnivoice]`：本地/外部语音合成配置。

注意点：

- `config.save_config()` 当前写回多个段，但没有写回 `frames` 段。
- 基础设置里的帧间隔/批大小更多依赖 session 或已有配置读取，持久化能力需要谨慎确认。
- `webui/config/settings.py` 另有一套轻量配置读取逻辑，默认读 `webui/.streamlit/webui.toml`，但不是当前主 WebUI 的核心配置链路。

## 12. 未接入、遗留与风险点

### 12.1 未接入或疑似遗留

- `webui/components/ffmpeg_diagnostics.py` 有完整独立诊断 UI，但没有接入 `webui.py` 主页面。
- `webui/utils/file_utils.py` 的 `open_task_folder()`、`save_uploaded_file()`、`create_zip()` 等基本未被主链路使用。
- `webui/utils/vision_analyzer.py` 当前未被主 WebUI 调用。
- `webui/tools/base.py` 的旧视觉分析 wrapper 当前没有被 `generate_script_docu.py` 使用。
- `basic_settings.render_generation_settings()`、`test_vision_model_connection()`、`test_text_model_connection()` 像旧入口，当前主渲染没有调用。
- `audio_settings.render_azure_v2_settings()`、`render_voice_parameters()`、`render_voice_preview()` 是兼容/旧版函数，当前主链路使用 `render_voice_preview_new()`。
- `app/services/video.py`、`app/services/video_service.py` 更像旧/辅助链路，当前 WebUI 主生成走 `task.start_subclip_unified()`。
- `app/services/material.py` 的 Pexels/Pixabay 素材搜索下载主要属于旧链路，当前 WebUI 主生成没有直接使用。

### 12.2 行为/命名不一致

- `subtitle_settings.is_disabled_subtitle_settings()` 对 `qwen3_tts`、`OmniVoice`、`soulvoice` 只显示“不支持精准字幕”警告，并不会真正禁用字幕设置。
- `video_settings.get_video_params()` 返回 `video_quality`，但主生成参数模型和合成链路里没有明显使用。
- 清理 clip videos 按钮清理 `storage/temp/clip_video`，但统一裁剪输出在 `storage/temp/clip_video_unified`。
- BGM 和 IndexTTS 参考音频资源目录存在本机绝对路径硬编码，部署到其他机器可能没有资源。

### 12.3 配置与 Provider 风险

- 新 LLM 架构的 provider 注册范围较窄，文本只有 `openai`，视觉有 `openai` 和 `twelvelabs`；旧 `llm.py` 支持更多 provider，但不是同一套管理体系。
- 新旧配置字段混用时，容易出现 UI 看似配置了某个 provider，但底层实际读取 OpenAI-compatible 全局配置。
- 纪录片文本生成 adapter 接收显式文本模型参数，但实际调用可能依赖全局 `LLMServiceManager` 配置。

### 12.4 测试覆盖风险

仓库有不少单元测试，覆盖纪录片、LLM adapter、字幕处理、短剧校验、多视频来源、剪映草稿等局部逻辑。但从 WebUI 操作到 LLM 到保存脚本再到最终视频生成的端到端测试不足；真实效果仍依赖外部模型、TTS、ASR、FFmpeg 和本地素材环境。

## 13. 后续开发定位建议

如果要改 WebUI 某个操作，建议按这个顺序追：

1. 先在 `webui.py` 或 `webui/components/*` 找按钮/控件。
2. 看它写入哪些 `st.session_state` 或 `config.*` 字段。
3. 找对应的 `get_*_params()` 是否把字段汇总进 `VideoClipParams`。
4. 再追 `app/services/task.py`、`jianying_task.py` 或 `webui/tools/*` 的真实服务调用。
5. 最后看 `app/services/*` 的文件产物和异常处理。

如果要排查“为什么 UI 配置了但生成没生效”，优先检查：

- 字段是否只写了 `config`，但没有进入 `st.session_state`。
- 字段是否进入了 `VideoClipParams`。
- 服务层是否真的读取该字段。
- `config.save_config()` 是否写回了对应配置段。
- 该功能是否在当前主链路中被调用，还是旧链路/未接入口。
