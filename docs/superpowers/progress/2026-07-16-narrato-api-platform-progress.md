# NarratoAI 多用户 API 平台实施进度

> 更新日期：2026-07-16
> 实施分支：`codex/narrato-api-platform`
> 独立 worktree：`/private/tmp/NarratoAI-narrato-api-platform`

## Task 1：建立实施工作区与验证基线

- **状态：** 完成
- **Commit：** 无；Implementation Plan 明确 Task 1 不创建提交。
- **工作区验证：**
  - `git rev-parse --show-toplevel` 返回 `/private/tmp/NarratoAI-narrato-api-platform`。
  - `git branch --show-current` 返回 `codex/narrato-api-platform`。
  - 当前 HEAD 为 `fcd55933fb109b457012c1fbef2efe5d955e1940`。
  - `.git` 指向主仓库的独立 worktree 元数据目录 `.git/worktrees/NarratoAI-narrato-api-platform`；`git worktree list --porcelain` 同时列出原 checkout 与本 worktree，路径和分支互不相同。
  - 原 checkout `/Users/wujingfeng/project/ai/codex/NarratoAI` 保持在 `wjf/v0.01`，本任务仅执行只读状态检查，未写入其文件；原 checkout 在任务开始前已有大量用户未提交改动，均未触碰。
- **运行时版本：**
  - `python3.12 --version`：`Python 3.12.2`
  - `node --version`：`v20.9.0`
  - `npm --version`：`10.5.0`
  - `ffmpeg -version | head -1`：`ffmpeg version 8.1 Copyright (c) 2000-2026 the FFmpeg developers`
- **验证命令与结果：**
  - 严格执行计划 Task 1 指定的 Python 3.11 回归命令：

    ```bash
    PYTHONDONTWRITEBYTECODE=1 /opt/homebrew/bin/python3.11 -m pytest -p no:cacheprovider -q \
      app/services/test_short_drama_narration_validation_unittest.py \
      app/services/llm/test_subtitle_adapter_pipeline_unittest.py \
      app/services/test_multi_video_script_sources_unittest.py \
      app/services/test_task_subtitle_resolution_unittest.py \
      app/services/test_script_subtitle_unittest.py \
      app/services/test_fun_asr_subtitle_unittest.py \
      app/services/test_merger_video_concat_unittest.py \
      app/services/test_jianying_task_unittest.py \
      webui/tools/test_generate_short_summary_unittest.py
    ```

    结果：`86 passed, 4 warnings in 21.55s`，退出码 `0`。
- **关键决策：**
  - Task 1 只建立隔离与基线证据，不修改业务代码，不安装依赖，不创建提交。
  - 后续新服务使用 Python 3.12；本次旧能力基线按计划继续使用固定的 `/opt/homebrew/bin/python3.11`。
- **计划偏差：**
  - 初次检查时 worktree 内尚无 `AGENTS.md`，因此先按任务上下文注入的同一项目约束执行；Task 1 最终自检前已由主 Agent 从原 checkout 只读复制到 worktree 根目录，并已从 worktree 路径实际读取确认。文件内容与本 Task 已执行的约束一致，缺失已补齐，无待处理偏差。
- **剩余风险：**
  - 回归测试存在 4 条非阻塞弃用告警：`pytest-asyncio` 默认 fixture loop scope 未配置、Pydantic v2 class-based config / `json_encoders` 弃用、Python `audioop` 将在 3.13 移除。
  - 设计、计划、编辑器约束和 `docs/web/docs/Oss.php` 当前在 worktree 中仍为未跟踪文件；后续按其所属 Task 纳入提交，Task 1 不擅自提交。

## Task 2：提取纯 Python 短剧服务与媒体探测

- **状态：** 完成
- **Commit：** `721756e refactor: isolate short drama core services`。
- **TDD RED：**
  - 初次执行 `python3.12 -m pytest tests/test_media_probe.py tests/test_short_drama_narration_service.py -q` 时，系统 Python 3.12 缺少 `pytest`，返回 `No module named pytest`；该结果仅属于环境失败，不计作行为 RED。
  - 在 `/private/tmp/narrato-api-platform-py312` 创建隔离 Python 3.12 虚拟环境；普通网络安装首次受 DNS/沙箱限制失败，经授权重试后安装依赖成功。
  - 激活隔离环境后重新执行同一 RED 命令，真实失败于 `ModuleNotFoundError: No module named 'app.services.media_probe'`，确认测试因目标模块尚不存在而失败（退出码 `2`）。
- **补充 RED：** 自审发现旧渲染流程会从 `NARRATO_FFMPEG_EXE` 同目录解析 FFprobe，先新增 sibling 兼容测试并观察到期望绝对路径、实际返回 `ffprobe` 的断言失败（`1 failed`），再补最小解析逻辑。
- **最小实现：**
  - 新增 `app/services/media_probe.py`，以冻结、slots 数据类 `MediaInfo` 返回时长、容器、音视频编码、分辨率和流存在性；统一将 FFprobe 执行、返回码、JSON 和无有效时长错误转换为 `MediaProbeError`。
  - 新增不导入 Streamlit 的 `app/services/short_drama_narration_service.py`，迁入路径归一化、多字幕合并、动态字数区间、模型 JSON 修复、多视频来源归一化、公开字段裁剪，并提供 `ShortDramaAnalysisRequest` 与 `build_short_drama_script()`。
  - `webui/tools/generate_short_summary.py` 保留 UI 进度、错误展示和状态适配，原 helper 名称代理到纯服务，最终脚本通过纯服务构建；`app/services/generate_video.py` 改用统一媒体探测并保持既有字典契约。
- **GREEN 验证：**
  - 指定命令：`python3.12 -m pytest -q tests/test_media_probe.py tests/test_short_drama_narration_service.py webui/tools/test_generate_short_summary_unittest.py app/services/test_short_drama_narration_validation_unittest.py`
  - 结果：首次完整回归 `19 passed, 3 warnings in 17.82s`；自审补充 FFmpeg sibling 兼容用例并修复后，最终 `20 passed, 3 warnings in 18.28s`，退出码 `0`。
  - 兼容回归：`PYTHONDONTWRITEBYTECODE=1 /opt/homebrew/bin/python3.11 -m pytest -p no:cacheprovider -q tests/test_media_probe.py tests/test_short_drama_narration_service.py webui/tools/test_generate_short_summary_unittest.py app/services/test_short_drama_narration_validation_unittest.py`
  - 结果：`19 passed, 3 warnings in 18.64s`，退出码 `0`。
- **关键决策：**
  - 纯服务通过请求 DTO 接收分析器或既有模型结果，不读取 Streamlit session、全局 UI 状态或隐式输出目录；本 Task 不提前创建 `coreApi`。
  - 容器名对 FFprobe 的复合 `format_name` 做稳定归一化，MP4 返回 `mp4`；任一已有视频探测失败时沿用旧行为，不生成可能误导的动态字数范围。
- **计划偏差：**
  - Python 3.12 初始环境没有 pytest 和项目依赖；按 Goal 要求创建隔离环境并安装 `requirements.txt` 后完成指定验证，未改动仓库依赖声明。
- **剩余风险：**
  - 仅有 3 条既存 Pydantic v2 弃用告警；无本 Task 新增告警或失败。
  - 真实供应商 LLM 调用不属于本 Task，脚本构建通过 Fake analyzer 覆盖；后续 Core 适配仍需在对应 Task 验证供应商边界。
- **独立审查修复（amend）：**
  - FFprobe schema RED：对字符串 `streams`、非对象 stream、非对象 `format`、不可转换分辨率运行参数化测试，分别观察到 `AttributeError`、错误分类和 `ValueError` 泄漏；现对根节点、stream 数组、format 对象及数值字段统一验证，全部转换为 `MediaProbeError("FFprobe 返回结构无效: ...")`。
  - FFprobe 发现 RED：不存在的显式 `NARRATO_FFPROBE_EXE` 直接返回坏路径，未回退 imageio sibling；现与旧渲染逻辑一致，仅接受存在的显式文件，恢复 `imageio_ffmpeg.get_ffmpeg_exe()` sibling 自动发现，失败后回退 PATH 中的 `ffprobe`。
  - WebUI 语义 RED：合法 JSON 缺少 `items` 时没有专用错误映射，测试观察到 helper 缺失；现纯服务错误携带稳定 `reason`，WebUI 恢复 `Generated narration missing items field`，无效 JSON 继续使用 `Generated narration JSON parse failed`。
  - 针对性 GREEN：`6 passed, 3 warnings in 19.19s`。
  - 最终 Task 2 GREEN：`python3.12 -m pytest -q tests/test_media_probe.py tests/test_short_drama_narration_service.py webui/tools/test_generate_short_summary_unittest.py app/services/test_short_drama_narration_validation_unittest.py`，结果 `26 passed, 3 warnings in 19.84s`。
  - 相关旧回归：Task 1 九文件 Python 3.11 命令，结果 `87 passed, 4 warnings in 18.53s`。
  - `git diff --check` 与四个改动模块 `python3.12 -m py_compile` 均通过。
- **最终独立复审：** PASS；需求符合性与代码质量均通过，无遗留 Critical/Important 问题。

## Task 3：消除共享状态、隐式字幕匹配与共享工作目录

- **状态：** 完成
- **Commit：** 本 Task 独立提交 `fix: isolate media task workspaces`（哈希见提交记录与 Task 报告）。
- **TDD RED：**
  - 指定 RED 命令：`/private/tmp/narrato-api-platform-py312/bin/python -m pytest tests/test_task_workspace_isolation.py tests/test_task_no_cross_task_globals.py -q`。
  - 结果：`5 failed, 2 warnings`；真实失败分别来自 `app.runtime`/`TaskWorkspace` 尚不存在、`start_subclip` 与 `start_subclip_unified` 仍声明 `global merged_audio_path, merged_subtitle_path`、Task/剪映字幕解析仍会扫描共享字幕目录并按 stem/时间选择文件。环境和测试收集正常。
  - 补充素材目录 RED：`tests/test_task_no_cross_task_globals.py` 得到 `2 failed, 3 passed`，证明下载和裁剪在未配置目录时仍传递空目录并回退共享缓存/临时目录。
- **最小实现：**
  - 新增冻结、slots 的 `TaskWorkspace`，严格按 `<base>/<task_id>/<attempt_no>/{temp,output}` 创建目录；同一 attempt 再次创建因 `temp` 已存在而拒绝复用。
  - 两条渲染调用链在函数入口初始化局部音频/字幕产物，删除模块级 `global merged_*` 声明和 `locals()` 回退，失败分支只清空本次调用的局部结果。
  - Task 与剪映字幕解析只接受 `original_subtitle_path(s)` 显式资产，删除扫描共享 `resource/srt`、视频 stem 猜测及按 mtime 选最新字幕的实现。
  - 素材下载与裁剪在默认或无效配置下使用 `utils.task_dir(task_id)`；底层裁剪不再自行回退到进程共享临时目录，缺少显式保存目录时直接拒绝。
- **GREEN 验证：**
  - 指定命令：`/private/tmp/narrato-api-platform-py312/bin/python -m pytest -q tests/test_task_workspace_isolation.py tests/test_task_no_cross_task_globals.py app/services/test_task_subtitle_resolution_unittest.py app/services/test_jianying_task_unittest.py`。
  - 结果：`26 passed, 2 warnings in 1.11s`，退出码 `0`。
  - Gate A 相关旧能力回归：Task 1 九文件 Python 3.12 隔离环境命令，结果 `87 passed, 4 warnings, 4 subtests passed in 24.15s`，退出码 `0`。
- **关键决策：**
  - 现有 Streamlit 入口继续按唯一 `task_id` 使用旧任务目录；未来 Core attempt 必须显式创建并传递 `TaskWorkspace`，本 Task 不提前实现 Core API 或 attempt 调度。
  - 保留显式字幕列表既有去重与顺序语义；仅删除与设计基线冲突的隐式猜测行为。
- **计划偏差：**
  - 设计要求显式字幕资产与实现计划中旧回归测试原有“按视频名自动找字幕”断言冲突；按设计基线将两处旧测试改为验证“不猜测”，并给原片对白测试显式传入字幕路径。
  - 实现计划列出 `app/utils/utils.py`，但本 Task 的最小实现无需修改该通用模块；attempt 目录职责集中在新建的 `TaskWorkspace`，未做无关重构。
- **剩余风险：**
  - 两条非阻塞弃用告警仍来自既有 Pydantic 配置和 Python `audioop`；Task 1 扩展回归另含既有 `json_encoders`/诊断 schema 告警。
  - 旧 Streamlit 任务模型没有 attempt 概念；Core adapter 在后续 Task 接入时必须使用本 Task 的显式工作区，不得退回旧任务目录。
- **独立审查修复（amend）：**
  - 审查发现初版 `TaskWorkspace` 未接入真实素材执行入口，且有效 `material_directory` 仍会让不同任务共享目录；新增并发 RED 后观察到 `clip_videos(..., workspace=...)` 参数不存在、两个任务下载均写向同一配置目录，针对性测试为 `4 failed, 5 passed` 中的两项路径失败。
  - `download_videos()` 与 `clip_videos()` 现接受可选显式 `TaskWorkspace`：Core attempt 写入各自 `workspace.temp_dir/{downloads,clips}`；旧 WebUI 不传工作区时保持兼容，默认走 `task_dir(task_id)`，有效全局素材根目录也强制追加 `task_id` 子目录。
  - 审查同时发现 `material.py` 的模块级 `requested_count` 会在并发请求间串写；静态与并发 RED 分别确认全局仍存在、`request_index` 接口缺失。现由调用方显式传递请求序号，`download_videos()` 使用本次调用的局部枚举选择 Key，不再保存进程级轮询状态。
  - 针对性并发/静态 GREEN：`tests/test_task_no_cross_task_globals.py`，结果 `9 passed, 2 warnings in 1.13s`。
  - 最终 Task 3 GREEN：指定四文件命令结果 `30 passed, 2 warnings in 1.12s`；Task 1 九文件旧回归结果 `87 passed, 4 warnings, 4 subtests passed in 25.58s`。
