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
- **Commit：** `05c81e2 fix: isolate media task workspaces`。
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
- **最终独立复审：** PASS；需求符合性与代码质量均通过，无遗留 Critical/Important 问题。

## Task 4：创建 coreApi FastAPI 骨架

- **状态：** 完成
- **Commit：** `feat: scaffold core api service`（本 Task 独立提交，哈希见提交记录与 Task 报告）。
- **TDD RED：**
  - 先创建 health、统一 envelope、OpenAPI 方法集合、request ID、ready 503/200 和 Bearer 401 测试，并创建 `coreApi/.venv` Python 3.12 隔离环境。
  - 普通 `pip install -e '.[test]'` 首次受沙箱 DNS 限制失败；按授权流程重试后，依赖从 `coreApi/pyproject.toml` 完整安装成功。
  - 隔离环境中的真实 RED 命令：`.venv/bin/pytest tests/unit/test_health.py tests/unit/test_http_contract.py -q`；结果因 `ModuleNotFoundError: No module named 'core_api'` 失败（退出码 `4`），确认测试运行环境正常且应用骨架尚不存在。
  - 自审补充 OSS 必要配置与日志脱敏测试；观察到 `required_configuration_is_present` 尚不存在的导入失败（退出码 `2`），再补最小实现。
- **最小实现：**
  - 新建独立 FastAPI 项目，`create_app()` 注册 `/api/v1`、请求 ID middleware、统一异常处理和 GET-only health 路由；成功与错误均返回 `code/message/data/request_id`，响应 Header 与 body 使用同一请求 ID。
  - `live` 仅检查进程；`ready` 通过可覆盖 Dependency 检查独立 Core 数据库、Redis，以及服务 Token、回调 Token、OSS 必要配置，失败只返回稳定 `SERVICE_UNAVAILABLE`。
  - 配置基于 Pydantic v2、环境变量和显式 TOML；生产默认/示例使用 PostgreSQL，真实配置不提交；SQLAlchemy 2、Alembic 和 Celery 均采用 Core 独立连接、Redis key 与 queue 前缀。
  - JSON 日志支持 `request_id/core_task_id/attempt_no`，自动屏蔽配置密钥和 Bearer Token；首次迁移仅建立 Alembic 基线，不包含 Task 5+ 业务表。
- **GREEN 验证：**
  - `.venv/bin/alembic upgrade head`：PASS，从空 SQLite 测试库升级至 `0001_core_base`。
  - `.venv/bin/alembic check`：PASS，`No new upgrade operations detected.`。
  - `.venv/bin/pytest tests/unit/test_health.py tests/unit/test_http_contract.py -q`：`10 passed, 1 warning`，退出码 `0`。
  - `.venv/bin/python -m compileall core_api migrations`：PASS。
- **关键决策：**
  - health 路由免鉴权以满足最小运维可用性；固定服务 Bearer Token 仍集中在可复用 FastAPI Dependency，未创建测试专用生产路由。
  - Alembic 配置中的 SQLite URL 只用于本地静态迁移验证并写入 `/private/tmp`；部署必须用 `CORE_API_DATABASE_URL` 覆盖为 PostgreSQL，项目依赖已包含 psycopg 驱动。
  - OSS 在本骨架阶段校验必要配置，具体签名与供应商连接由后续 OSS Adapter 任务实现；ready checker 接口允许集成环境替换为真实检查器。
- **计划偏差：**
  - 实现计划未列出 Alembic 模板和包初始化文件，但 Alembic 运行及测试包导入确实需要，按 Task brief 允许的最小范围补充。
  - 系统 Python 3.12 初始无本 Task 依赖；已按 Goal 要求创建 `coreApi/.venv` 并从独立依赖声明安装，无根环境偶然依赖。
- **剩余风险：**
  - 测试存在 1 条来自当前 FastAPI/Starlette TestClient 组合的上游弃用告警，不影响行为与验收。
  - 真实 PostgreSQL、Redis 和 OSS 连接不属于本 Task 单元验证；本 Task 使用 SQLite 与 Fake readiness，后续数据库/适配器集成 Gate 必须覆盖真实服务。
- **独立审查修复（amend）：**
  - 日志安全 RED：默认 formatter 对 PostgreSQL/Redis URI userinfo、`password/token/secret` 命名值和 nested extra 的测试得到 `2 failed`，明文凭据可稳定复现；现统一按 URI、Bearer、敏感键名、已配置密钥递归脱敏，并保留非敏感结构化 extra。
  - 配置 Dependency RED：应用已持有显式 Settings 时，把 `CORE_API_CONFIG` 指向不存在文件，受保护路由仍因 eager fallback 返回 `500`；现仅在 `app.state.settings` 确实不存在时读取缓存配置，回归返回 `200`。
  - 异步 readiness RED：同步 DB probe 阻塞 `0.2s` 时，事件循环调度与 timeout 断言失败；现用 `asyncio.to_thread()` offload SQLAlchemy 探针，以可配置 `readiness_timeout_seconds` 包裹 DB/Redis，并设置 Redis socket timeout。事件循环探针证明慢 DB 不再阻塞 live 调度，超时统一转换为安全 `503`。
  - Minor 修复：新增 Bearer 缺失/Basic/畸形/正确值、非法 Request ID、405、422、500、默认配置缺失 503 的负向回归；`import core_api` 不再导入 `main` 或初始化 FastAPI/日志配置。
  - 修复后完整 Task 4 测试：`.venv/bin/pytest tests/unit/test_health.py tests/unit/test_http_contract.py -q`，结果 `26 passed, 1 warning`；fresh SQLite `alembic upgrade head`/`alembic check`、compileall、diff-check、OpenAPI/边界/敏感信息扫描均通过。
  - Task 4 继续保持单一 amended commit；精确最终 hash 由下一 Task 在 amend 完成后回填，避免提交自引用导致 hash 再次变化。
- **独立复审 R2 修复（amend）：**
  - structured extra 别名 RED：对 `api_key`、`api-key`、`APIKey`、`access_key_id`、`ACCESS-KEY-ID`、`secret_access_key`、`credential(s)`、`passwd`、`pwd` 的大小写与嵌套 dict/list 参数化验证，原实现得到 `10 failed, 7 passed`，证明 substring 判定覆盖不足。
  - 现统一把 camelCase、大小写、下划线和连字符规范化为词元/紧凑键名，通过凭据词元、敏感后缀和 key namespace 做保守判定；structured extra 与 message `key=value` 共用同一判定，不会误伤 `request_id/project_id`。
  - R2 完整 Task 4 GREEN：`43 passed, 1 warning`；敏感别名探针 `19 passed`，Alembic、compileall、diff-check、OpenAPI/边界扫描继续通过。
