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
- **Commit：** `557e96c feat: scaffold core api service`。
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
- **最终独立复审 R3：** PASS；Commit 固定为 `557e96c`，需求符合性与代码质量均通过，无遗留 Critical/Important 问题。

## Task 5：实现 Core Task、Attempt、租约与 Callback Outbox

- **状态：** 完成
- **Commit：** `6990308 feat: add durable core task runtime`。
- **TDD RED：**
  - 先新增状态机、租约、Outbox 和 ProcessRunner 四组测试；生产模块尚不存在时，`.venv/bin/python -c 'import core_api.tasks.models'` 真实失败于 `ModuleNotFoundError: No module named 'core_api.tasks'`，确认目标能力缺失而非断言误写。
  - 首次启动指定 pytest RED 命令时，macOS 本机对新 Python 进程的标准库/pytest 动态模块导入异常缓慢；`-X importtime` 证据显示 `_csv`、`random` 等单次导入耗时数十秒。中断堆栈仅位于 pytest 导入阶段，因此不把该次环境启动失败计作行为 RED；模块缓存热身后同一 venv 的测试稳定运行。
  - 增量行为 RED：retryable 失败错误被 `LEASE_EXPIRED` 覆盖（`1 failed`）；运行中状态未写 Outbox且 heartbeat 回调异常未回收子进程（`2 failed`）；重启接受零租约时长且 Runner 会拆分命令字符串（`2 failed`）。各项均先观察期望失败，再做最小修复。
- **最小实现：**
  - 新增 `core_tasks`、`core_task_attempts`、`callback_outbox` SQLAlchemy 模型及 `0002_core_tasks` 迁移；任务使用 `ctask_` 时间有序 ULID 风格 ID，attempt/Outbox 均使用带前缀 ID，输入快照和请求摘要持久化，幂等作用域固定为“调用方 + 路径 + Key”。
  - `TaskService` 使用显式事务和 PostgreSQL `FOR UPDATE` 领取：仅 `queued/retry_wait` 可创建 current attempt；高熵 token、单调 lease version、heartbeat 到期时间、current attempt、token/version/status 六重守卫共同阻止重复领取与迟到覆盖。
  - 迟到结果只保存摘要和 digest 后提交审计，再抛 `STALE_LEASE`；旧 attempt 不改变新 attempt、任务结果或终态。状态迁移单调增加 `state_version`，`succeeded/failed` 不可逆且不存在 cancel。
  - 默认 `max_retries=3` 明确定义为“初次执行 + 最多 3 次自动重试”，总计最多 4 个 attempt；临时错误保留规范化错误并重启，确定性错误直接终止，耗尽后进入 `failed`。
  - 每个 running/retry_wait/终态状态版本写入事务 Outbox；数据库同时以 `event_id` 和 `(core_task_id, state_version)` 唯一约束去重，Celery 任务只负责唤醒且禁用 Result Backend 事实语义。
  - `ProcessRunner` 仅执行参数列表，使用 `subprocess.Popen(..., shell=False, start_new_session=True)`；周期 heartbeat，超时先 TERM 进程组再 KILL，heartbeat 异常同样回收；stdout/stderr 分别按字节上限持续 drain 并返回截断标记。
- **GREEN 验证：**
  - `.venv/bin/alembic upgrade head && .venv/bin/alembic check`：PASS，升级至 `0002_core_tasks` 且 `No new upgrade operations detected.`。
  - `.venv/bin/pytest tests/unit/test_task_state_machine.py tests/unit/test_leases.py tests/unit/test_callback_outbox.py tests/unit/test_process_runner.py -q`：`22 passed, 1 warning in 0.63s`。
  - `.venv/bin/pytest tests/unit/test_health.py tests/unit/test_http_contract.py -q`：`43 passed, 1 warning in 0.54s`。
  - `.venv/bin/python -m compileall core_api migrations`：PASS。
  - Fresh SQLite `/private/tmp/narrato_core_api_task5_fresh_20260716.db` 从空库执行 upgrade/check，核验 `alembic_version/core_tasks/core_task_attempts/callback_outbox` 四表、三组唯一约束和全部指定索引：PASS。
  - PostgreSQL offline migration SQL：成功生成三表、外键、唯一约束和索引，证明迁移可由 PostgreSQL 方言编译。
- **关键决策：**
  - 统一采用“初次 + 3 次自动重试”语义，与设计文档“最多重试 3 次”一致；`current_attempt_no` 从 1 开始，`lease_version` 随新 attempt 单调增加，heartbeat 不改变版本。
  - `expire_and_restart()` 是调度器确认旧 attempt 已失效后的原子操作；本 Task 不实现 Task 6+ 的原子能力路由、供应商适配或实际 Worker 执行。
  - Callback Outbox 是 PostgreSQL 事实记录；Celery 只携带 task ID 作为唤醒信号，未读取或保存最终结果。
- **计划偏差：**
  - Implementation Plan 只明确终态 Outbox 示例，设计基线要求“状态变化和终态”回调；按设计基线扩展为 running、retry_wait 和终态均按状态版本写 Outbox，并记录双唯一约束。
  - 本机没有可直接使用的真实 PostgreSQL 凭据；按 Task brief 使用 SQLite 做迁移/模型验证，并额外生成 PostgreSQL offline SQL，不把生产数据库连接作为本 Task 强制条件。
- **自审结论：** 状态迁移表、current/version/token/expiry 守卫、迟到审计事务、Outbox 双去重、无 cancel、中文 Docstring、PostgreSQL 方言迁移、`git diff --check` 均通过。
- **剩余风险：**
  - 当前并发领取单元测试在 SQLite 验证重复调用，生产原子性依赖 PostgreSQL 行锁与 `(core_task_id, attempt_no)` 唯一约束；真实 PostgreSQL 竞争集成测试留待 Gate A/Task 20 环境验证。
  - 唯一告警仍为 Task 4 已记录的 FastAPI/Starlette TestClient 上游弃用告警；不影响 Task 运行时行为。
- **独立审查 R1 修复（amend）：**
  - 租约恢复 RED：有效 3600 秒租约可被立即替换；现 `expire_and_restart()` 在同一行锁事务中验证 `lease_expires_at` 或 heartbeat 阈值，未超时稳定抛 `LEASE_STILL_ACTIVE` 且状态/版本/attempt 不变，租约到期和 heartbeat 边界均有测试。
  - 结果版本 RED：`complete_attempt()` / `fail_attempt()` 省略 `lease_version` 仍成功；现调用方必须显式提供 version，缺失产生签名错误，错误 version 统一拒绝。Implementation Plan 示例省略 version 且立即重启有效租约，与设计“所有结果必须带租约版本、确认超时后恢复”冲突；按 design 唯一需求基线修正测试和接口，不沿用示例的宽松行为。
  - Outbox 碰撞 RED：两个 task 复用 `event_id` 会提交第二个终态但无事件；现只有同一 task/state 逻辑事件幂等，跨 task 或同 task 不同 state 稳定抛 `OUTBOX_EVENT_CONFLICT`，并回滚第二个 task/attempt 的终态与 `state_version`。
  - ProcessRunner RED：0.1 秒超时、0.05 秒宽限时，leader 收到 TERM 退出但忽略 TERM 的后代持 pipe 使调用阻塞约 3.095 秒；现宽限检查整个进程组，期限后无条件 KILL group，并对 reader 做有界收尾。黑盒复测耗时 `0.164s`；stdout/stderr 各 10 MiB 探针 `0.048s` 完成，各仅保留 1024 bytes 且标记截断。
  - 并发幂等 RED：两个独立 Session/WAL 强制同时读到空作用域时，同体和异体 loser 均泄漏 `IntegrityError`（`2 failed`）；现以 savepoint 捕获唯一约束竞争并回读 winner，同 digest 两调用返回同 ID，不同 digest 稳定抛 `IDEMPOTENCY_CONFLICT`，重复执行五轮稳定通过。
  - 事实源约束 RED：task/attempt/outbox 三个状态列均无数据库 CHECK（`2 failed` 中的约束断言）；现模型和 `0002` migration 统一生成命名 CHECK。Fresh SQLite 反射和非法状态写入、PostgreSQL offline DDL 三条 `CONSTRAINT ... CHECK` 断言均通过，Alembic check 无差异。
  - R1 最终 GREEN：Task 5 指定四文件 `31 passed, 1 warning in 0.94s`；并发幂等 `2 passed, 1 warning in 0.06s`；Task 4 回归 `43 passed, 1 warning in 0.41s`；默认/fresh SQLite upgrade/check、PostgreSQL offline DDL、compileall、diff-check 全部通过。
- **独立复审 R2：** PASS；Commit 固定为 `6990308`，需求符合性与代码质量均通过，无遗留 Critical/Important 问题。

## Task 6：实现统一能力目录

- **状态：** 完成
- **Commit：** `feat: add normalized capability catalog`（本 Task 独立提交；精确哈希由 Task 7 回填，避免提交自引用改变哈希）。
- **TDD RED：**
  - 先创建 10 组目录契约、过滤、ID 校验、幂等种子和版本测试；指定命令 `.venv/bin/pytest tests/unit/test_capability_catalog.py -q` 在收集阶段真实失败于 `ModuleNotFoundError: No module named 'core_api.capabilities'`（退出码 `2`），确认能力域尚不存在而非环境或断言错误。
  - 自审发现新增供应商密钥注册表的真实值尚未进入日志 formatter 的已配置密钥集合；先补日志 RED，目标测试得到 `1 failed`，测试密钥明文可在普通日志参数中稳定复现，再做最小脱敏修复。
- **最小实现：**
  - 新增 `core_providers/core_models/core_voices` 模型及 `0003_core_capabilities` 迁移；provider code 全局唯一，模型/音色原始 code 仅在同一 provider 内唯一，公开 `model_`/`voice_` ID 使用时间有序 ULID 风格稳定标识，UTC timestamps 与 JSON 约束字段完整落库。
  - `Settings.provider_secrets` 从私有 TOML `[provider_secrets]` 加载；数据库只保存 `secret_ref`。目录仅纳入 provider 与能力自身均启用、且引用解析为非空字符串的记录；真实密钥值同时加入 JSON 日志 formatter 的脱敏集合。
  - `GET /api/v1/capabilities` 复用固定 Core Bearer dependency 和统一 envelope；Provider/Model/Voice 均经过显式 DTO 映射，业务层看不到 `secret_ref`、settings、原始 provider model/voice code 或真实密钥。
  - 目录按稳定键排序，对完整公开内容做 canonical JSON SHA-256 得到 `catalog_...` 版本；相同可见内容版本稳定、可见内容变化版本变化，密钥值轮换但可调用性不变时版本保持不变。
  - `require_model()` / `require_voice()` 对未知 ID、能力停用、provider 不可调用和语言/格式/采样率/能力类型不匹配统一抛 `CAPABILITY_UNAVAILABLE`，不提供默认供应商回退。
  - `seed_capabilities()` 按 provider code 与 provider 内原始能力 code 幂等 upsert；允许更新所有非密钥配置和 `secret_ref`，默认保留运维当前 `enabled` 状态，仅 `override_enabled=True` 时显式覆盖。
- **GREEN 验证：**
  - `.venv/bin/alembic upgrade head && .venv/bin/alembic check`：PASS，升级至 `0003_core_capabilities` 且 `No new upgrade operations detected.`。
  - `.venv/bin/pytest tests/unit/test_capability_catalog.py -q`：`11 passed, 1 warning in 0.36s`。
  - `.venv/bin/pytest tests/unit/test_task_state_machine.py tests/unit/test_leases.py tests/unit/test_callback_outbox.py tests/unit/test_process_runner.py tests/unit/test_health.py tests/unit/test_http_contract.py -q`：`74 passed, 1 warning in 1.43s`。
  - `.venv/bin/python -m compileall core_api migrations`：PASS。
  - Fresh SQLite 从空库完整执行 `0001 -> 0002 -> 0003` 与 `alembic check`，反射核验 7 张表、模型/音色到 provider 的 FK 及三组 code 唯一约束：PASS。
  - PostgreSQL offline DDL 成功生成三张能力表、两个 FK、三组唯一约束和索引，方言静态验证：PASS。
  - 私有 TOML `[provider_secrets]` 实际解析及 `Settings` repr 不含真实值：PASS。
- **关键决策：**
  - 目录 `version` 只由公开 DTO 内容计算，不使用 timestamps、`secret_ref` 或 secret 值；密钥从有值变为缺失会因可见 provider/能力集合变化而自然改变版本。
  - 供应商公开摘要固定为 `provider_code/name/capability_types`；模型和音色分别使用设计规定的统一字段集合，不暴露任何适配器私有字段。
  - Core ORM 实体仍保存后续 adapter 所需原始 code，但仅 `CapabilityService` 内部验证返回实体；HTTP 边界只能序列化统一 DTO，本 Task 不实现 Task 7+ 供应商调用。
- **计划偏差：**
  - Implementation Plan 只给出音色 shape 示例；按 design 唯一基线和 Task brief 补齐 Model/Provider DTO、稳定版本、secret registry、严格 ID 约束与幂等 seed 测试。
  - 本机无真实 PostgreSQL 连接凭据；按 Goal 允许范围使用 fresh SQLite 做真实迁移/约束反射，并用 PostgreSQL offline DDL 验证方言兼容性，未把真实数据库连接伪报为通过。
- **自审结论：** DTO 字段与 secret/raw code 边界、稳定排序/version、seed 状态保留、迁移 FK/唯一约束、中文 Docstring、无 Task 7 越界和 `git diff --check` 均通过；日志自审发现的 provider secret 脱敏缺口已按 RED/GREEN 修复。
- **剩余风险：**
  - 当前 JSON 数组内的语言、格式和 capability type 由服务层验证，数据库不对 JSON 元素值建立枚举约束；这是能力扩展字段的预期边界。
  - 唯一告警仍为既有 FastAPI/Starlette TestClient 上游弃用告警；不影响目录协议和验收。
- **独立审查 R1 修复（amend）：**
  - SQLite FK 与孤儿数据 RED：Core engine 新连接的 `PRAGMA foreign_keys` 实际为 `0`；legacy orphan model 的严格 ID 校验继续触发 `AttributeError`。三个专项初始合并结果为 `3 failed`。现为 Core 创建的每个 SQLite DBAPI connection 启用 `PRAGMA foreign_keys=ON`，fresh schema 实际 orphan 写入被 `IntegrityError` 拒绝；对历史损坏数据，catalog 安全过滤，`require_model/require_voice` 统一抛 `CAPABILITY_UNAVAILABLE`。
  - 并发 seed RED：两个独立 Session 经 barrier 同时观察 provider 不存在后，loser 泄漏 `uq_core_providers_code` 的 `IntegrityError`。现 provider/model/voice 三层均在释放初始 SQLite 读事务后，以 savepoint 尝试插入并在唯一键竞争时回读 winner；每层及时提交释放唯一键锁，兼容 PostgreSQL 默认 READ COMMITTED 和 SQLite。
  - 并发验证用 provider/model/voice 三阶段 barrier 强制每层都发生同读空竞争，连续 5 轮两调用均收敛到完全相同的三组稳定 ID，最终各表每轮仅 1 条；并发重复 seed 仍保留运维手动禁用的 provider/model/voice 状态。
  - R1 GREEN：Task 6 `14 passed, 1 warning`；Task 5+4 指定回归 `74 passed, 1 warning`；fresh SQLite `0001 -> 0003` upgrade/check、实际 orphan FK 拒绝、PostgreSQL offline DDL、compileall、中文 Docstring 和 diff-check 全部通过。
- **独立审查 R2 修复（amend）：**
  - 批次原子性 RED：后段 voice `name NOT NULL` 失败后，新 Session 仍读到已提交的 provider/model（provider count 为 `1`）；外层 `with session.begin()` 组合调用则在 seed 内部 commit 后触发 `InvalidRequestError: closed transaction inside context manager`。两项指定测试结果为 `2 failed`。
  - 删除 seed 内全部 commit/savepoint 事务控制；SQLite 和 PostgreSQL 分别使用方言原生 `INSERT ... ON CONFLICT DO NOTHING` 在唯一键处原子竞争，并于同一调用方事务回读 winner。provider/model/voice 整批现在只由调用方 commit/rollback，约束失败和调用方异常都会全量回滚。
  - 并发 worker 改为两个独立 Session 在 barrier 后各自用外层 `session.begin()` 调用；连续 5 轮每轮均同 ID/单记录，整项额外重复 5 次稳定，无 `IntegrityError`，并发重复 seed 仍保留运维禁用状态。
  - R2 GREEN：Task 6 `16 passed, 1 warning`；新增后段约束失败全回滚和外层事务组合/调用方回滚均 PASS；Task 5+4 指定回归 `74 passed, 1 warning`；fresh SQLite、PostgreSQL offline DDL、compileall、中文 Docstring 和 diff-check 全部通过。
- **最终独立复审 R3：** PASS；Commit 固定为 `ae608fb`，需求符合性与代码质量均通过，无遗留 Critical/Important 问题。

## Task 7：实现 OSS、媒体探测和 ASR 原子任务

- **状态：** 完成；独立复审 R5 通过。
- **Commit：** `6e9fca1 feat: expose media probe and asr tasks`。
- **TDD RED：**
  - 先创建对象键/CDN URL/workspace、视频/SRT 限制以及 media/asr API/handler 集成测试；指定 unit 命令真实失败于 `ModuleNotFoundError: core_api.infrastructure` 与 `ModuleNotFoundError: core_api.adapters`（2 个 collection errors），证明目标能力缺失。
  - 安全复核补充 double-encoded traversal 与本地路径 POST 测试，真实得到 `2 failed`：`%252e%252e` 未拒绝、`/private/tmp/local.mp4` 被错误接受为 `202`；随后最小修复多轮 decode 检查与 API allowlist 校验，专项 `12 passed`。
  - 幂等复核补充仅改变 `caller_task_id` 的异体请求，真实观察到错误返回 `202`；现将公开请求中的 caller task ID 一并纳入 canonical digest，专项及 Task 5 幂等/状态机回归 `14 passed`。
  - 生产配置复核新增 OSS endpoint/CDN base 非 HTTPS 用例，真实得到 `2 failed`；现 `Oss2Client` 构造时强制完整 HTTPS、无 userinfo/query/fragment 且 bucket/凭据非空，专项 `2 passed`。
- **最小实现：**
  - Core object key 固定为 `narrato/coreApi/YYYY/MM/DD/<32 lowercase md5>.<ext>`；seed 包含 task/attempt/artifact ID/随机 nonce，扩展名只取白名单，不读取大文件计算 MD5。
  - `CdnUrlPolicy` 仅允许配置中精确 Host 的 HTTPS `/narrato/api/` URL，拒绝 userinfo、fragment、非 443 端口、IP literal、反斜杠、单/双重 encoded traversal；下载器逐跳复核 redirect，使用连接/读取/总时限、Content-Length 与流式字节双限制，超限删除部分文件。
  - `CoreTaskWorkspace` 原子创建 `<work_root>/<ctask>/<attempt>/input|temp|output`，校验 task/attempt 与 resolve 边界，同 attempt 已存在时拒绝脏复用；`ArtifactStore` 只上传当前 output 内非 symlink 白名单文件并返回不含本地路径的统一 DTO。
  - 视频 `.mp4/.mov/.avi` 通过既有 `app.services.media_probe.probe_media` 验证真实容器、视频流、编码、尺寸、正时长和 `<=600.0s`；SRT 限制 5 MiB，验证编码、连续 cue、非空文本及非负/递增/不重叠时间轴，不上传输入副本。
  - ASR adapter 显式下载已验证 CDN 媒体到 attempt input，通过注入 factory 调用既有 `create_with_local_fun_asr`，输出固定 attempt `output/subtitle.srt`；Fake ASR 为默认测试路径，空/损坏 SRT 确定性失败，合法产物上传并在合法租约完成事务中登记 `core_artifacts`。
  - 新增 `POST /api/v1/media-probe/tasks`、`POST /api/v1/asr/tasks` 与 `GET /api/v1/tasks/{core_task_id}`；固定 Bearer、必需幂等 Key、202/409/404 统一 envelope，同 key 同体不重复 dispatch。Celery 只携带 task ID，handler 使用 Task 5 attempt/lease/heartbeat/终态/Outbox；迟到 attempt 不登记 artifact。
- **GREEN 验证：**
  - Task 7 指定 unit+integration：`54 passed, 1 warning`；其中 ASR integration `6 passed, 1 warning`。
  - Core 全 unit：`134 passed, 1 warning`；全部 Task 7 integration：`12 passed, 1 warning`。
  - 默认与 fresh SQLite `0001 -> 0004` upgrade/check：PASS；fresh schema 含 `core_artifacts` 指定列/外键/唯一约束；PostgreSQL offline DDL：PASS。
  - `.venv/bin/python -m compileall core_api migrations`、`git diff --check`、`pip check`：PASS；`oss2 2.19.1` 与 `httpx 0.28.1` 可实际导入。
  - 原项目回归：固定 Python 3.11 三文件命令 `40 passed, 2 warnings`。
- **关键决策与计划偏差：**
  - Implementation Plan 未列出 Artifact migration，但 design 第 15.2 节明确 `core_artifacts` 是 Core 事实表；按 design 唯一基线新增 `0004_core_artifacts`，并确保产物登记与合法 attempt 终态同一提交。
  - HTTP/OSS 使用生产 Adapter，测试只用 `httpx.MockTransport`、Fake downloader/Fake OSS/Fake ASR 和本地 FFmpeg 小视频，不连接真实 OSS、ASR 或 Broker。
- **剩余风险：**
  - 真实 OSS/真实 ASR Smoke Test 按 Goal 明确为可选且本环境无凭据，未执行；OSS2 SDK 安装和静态导入已验证。
  - 唯一 Core 告警仍为既有 FastAPI/Starlette TestClient 上游弃用告警；原项目 2 条告警为既有 Pydantic/Python audioop 弃用。
- **独立审查 R1 修复（amend）：**
  - C1 多层 URL 编码 RED：1～8 层 dot/slash/backslash/percent 攻击共 `25 failed`，并补充 deeply encoded redirect 与 IDNA canonicalization RED；现逐层检查 percent escape，任意层编码的 `% . / \\` 立即拒绝，最多 12 层且不收敛/残留 `%` 拒绝，实际请求只使用验证后的 canonical path/IDNA host。专项 `35 passed`。
  - C2 可靠 dispatch RED：首次 Broker 失败原返回 500，幂等重放不再投递；现创建任务与 `core_dispatch_outbox` 同事务，API 首次/同体重放都会尝试 pending 事件，失败只记稳定 `DISPATCH_FAILED` 并返回 202，Beat/scanner 到期重放，发送后崩溃最多重复 wake，成功后原子标 sent。
  - C3 自动重试 RED：临时失败会留下无人执行的 replacement RUNNING；现旧 attempt 标记 failed、task 进入 retry_wait，指数退避+jitter 的 available_at 与 dispatch outbox 同事务，到期 wake 后才领取新 attempt。首次临时失败第二次成功、重复 wake、以及初次+3 次耗尽均通过。
  - I1 Artifact TOCTOU RED：output 目录替换 symlink、文件检查后替换会越界/按路径重开；现 workspace 以固定 base/root 检查所有祖先，并用 dirfd 逐层 `O_DIRECTORY|O_NOFOLLOW`，Artifact 以 output dirfd + `O_NOFOLLOW` 打开、`fstat` regular file，并在同一已打开 stream 上摘要和 OSS 上传。目录/file symlink 与 replace-after-open 攻击均通过。
  - I2 heartbeat/fencing RED：长任务无周期 heartbeat、ASR 不接受 lease guard；现生产 Worker 用独立短 Session heartbeat pump，副作用/完成前同步 fencing，主 Session 查询使用 `populate_existing` 获取最新租约。真实 SQLite 双 Session 超过原 lease 的慢任务仍成功；stale guard 在 OSS 前阻断上传。
  - I3 公共 DTO RED：空白 Idempotency-Key 与未知字段均被 202 接受；现 key trim 后非空/无控制字符/最长 255，media/asr DTO `extra=forbid`，均稳定 422。
  - I4 readiness RED：HTTP OSS/CDN、空 allowlist、相对 work root 与 OSS timeout 未被验证；现 ready 校验 HTTPS OSS/CDN、精确非 IP allowlist、绝对且可写 workspace，并以 timeout/offload 执行可注入最小 OSS bucket probe；失败统一安全 503。
  - I5 数据库约束 RED：不存在 attempt 与负/零 size Artifact 可提交；现 `core_artifacts` 增加 `(core_task_id, attempt_no)` 复合 FK、attempt/size 正数 CHECK，`0004` 同时建立 dispatch outbox。Fresh SQLite 实际非法 insert 均被 `IntegrityError` 拒绝，PostgreSQL offline DDL 可见全部约束。
  - R1 GREEN：Task 7 四文件 `101 passed, 1 warning`；Core unit `172 passed, 1 warning`；Core integration `24 passed, 1 warning`；Task 5/6 专项 `49 passed, 1 warning`；默认/fresh Alembic upgrade/check、fresh SQLite 非法约束探针、PostgreSQL offline DDL、compileall、pip check、diff-check、OpenAPI/secret/path/Docstring 扫描全部 PASS；原项目回归 `40 passed, 2 warnings`。
- **独立审查 R2 修复（amend）：**
  - C1 恢复闭环 RED：Broker 已接收但 Worker 未领取的 queued 事件没有重新布防，租约恢复仍直接预建无人执行 RUNNING attempt。现 Celery wake 启用 `acks_late`、`reject_on_worker_lost` 和单预取；新增生产 Beat recovery scanner，同次扫描将长期未领取 sent 事件重置 pending 并发布，将 lease/heartbeat 过期 attempt 标记 expired，task 只进入 retry_wait 并事务写入 dispatch，到期后才由 fenced wake 领取。重复扫描、成功终态跳过及生产 scanner 一次 rearm+dispatch 均有组合测试。
  - C2 fencing/backoff RED：旧 wake、future wake 和 API `force=True` 可绕过状态版本或退避。现每条 Broker 消息携带 `task_id/expected_state_version/not_before/dispatch_id`；publisher 所有入口只发送 due pending，handler 以条件 UPDATE 原子校验版本、状态和到期时间，stale/duplicate/future 均忽略且不增加 attempt。
  - I1 并发领取 RED：SQLite/PostgreSQL 行锁语义差异可能让 loser 命中 attempt 唯一约束。现状态领取使用 `status + state_version` 条件 UPDATE，唯一约束异常仅作为最后防线回滚并返回 ignored；真实文件 SQLite 两独立 Session/barrier 得到 1 claimed + 1 ignored、仅 1 running attempt。
  - I2 首次响应 RED：任务转 running 后相同幂等 POST 返回当前状态而非首次 202 数据。现 `core_tasks.initial_response` 持久化 `{core_task_id,status:queued}`，所有同体重放返回首次快照，异体仍 409 且 future dispatch 不被强制发送。
  - I3 OSS timeout RED：ready 外层 `wait_for` 未向 oss2 transport 下传 timeout，重复超时持续占用全局 executor。现 `Oss2Client` 将 `(connect_timeout, read_timeout)` 传给 `oss2.Bucket`；ready 使用专用 `max_workers=2` executor，20 个重复超时探针最大底层并发为 2，取消的排队 future 不污染全局线程池。
  - Task 5 计划偏差：旧 plan/test 示例在确认 lease 过期后立即创建 replacement RUNNING attempt；design 第 11 节和数据库扫描恢复要求新 attempt 由调度 wake 领取。按 design 唯一基线将 `expire_and_restart` 改为 `expired -> retry_wait + durable dispatch`，不预建 attempt，并同步修订 Task 5 状态机、租约和 callback 测试。
  - R2 RED：新增 bounded OSS probe 初始 collection error；恢复/fencing/并发/旧 Task5 组合首次运行 `28 failed, 22 passed`，均为真实旧行为或最小实现缺口。
  - R2 GREEN：Task 7+恢复指定文件 `109 passed, 1 warning`；Core unit `175 passed, 1 warning`；Core integration `31 passed, 1 warning`；Task 5/6 专项 `49 passed, 1 warning`；默认/fresh SQLite、PostgreSQL offline DDL（含 `initial_response`/Artifact FK/dispatch outbox）、compileall、pip check、diff-check 全部 PASS；原项目回归 `40 passed, 2 warnings`。
- **独立审查 R3 修复（amend）：**
  - I1 既有数据升级 RED：从 0003 插入 queued/retry_wait/running 后升级 0004，前两者无 dispatch 且三者首次响应为空。现 0004 同次回填全部 `initial_response`，为 queued/retry_wait 按当前 `state_version` 和 `updated_at` 建 pending dispatch；running 不误投，由 expired scanner 恢复。真实 0003→0004 SQLite 数据迁移、publisher 与 running lease recovery 全部通过，PostgreSQL offline SQL 使用 `json_build_object` 与兼容 `INSERT ... SELECT`。
  - I2 readiness 容量 RED：旧 `run_in_executor` 在 102 个短 timeout 下仍可无界排队。现应用私有 `BoundedReadinessExecutor(max_workers=2)` 在 submit 前非阻塞占槽，槽仅在线程实际完成后释放；102 并发只提交 2 个、active≤2，其余快速安全失败。实际 checker 同时下传 settings 的 connect/read/readiness timeout；FastAPI lifespan 关闭 executor，关闭后提交稳定拒绝。
  - I3 scanner 公平 RED：旧顺序先处理 stale sent，101 条即可耗尽 limit 并饿死 expired running；固定 60 秒 visibility 还会重复放大。现优先 expired running、其次 retry_wait、最后 queued，查询使用 `FOR UPDATE SKIP LOCKED`；sent visibility 按 `attempt_count` 指数增长并封顶。101 stale + 1 expired/limit100 中 running 必先恢复；第二次发送后 599 秒不重 arm、600 秒仅一次；publisher 同样优先 due retry_wait。
  - R3 RED：新增 shutdown 测试最初缺少 import，公平/visibility scanner 尚未接入，既有数据 publisher 尚未到期，共 `4 failed, 19 passed`；修正后专项 `23 passed`，再补 due retry 优先测试通过。
  - R3 GREEN：Task 7+恢复+迁移指定文件 `113 passed`；Core unit `176 passed`；Core integration `35 passed`；Task 5/6 专项重跑 `49 passed`；0003→0004 真实数据迁移、fresh SQLite、PostgreSQL offline SQL、compileall、pip check、diff-check 与原项目 `40 passed` 全部通过。
- **独立审查 R4 修复（amend）：**
  - R4 RED：旧 scanner 在 SQL `LIMIT` 后才用 Python 计算指数 visibility，专项首次因新字段尚未接入产生 collection error，接入过程中也证实旧 sent 测试没有可查询 deadline。
  - 新增持久 `recover_after` 与 `(status, recover_after)` 索引；publisher 成功时按投递 `attempt_count` 计算指数 visibility deadline，失败/重 arm 清空 deadline。scanner 现在完全在 SQL 中筛选 `recover_after <= now`、按 deadline 排序后 LIMIT，并保留 `FOR UPDATE SKIP LOCKED`。
  - limit=1、前四条更旧但高 attempt 未到期、第五条低 attempt 已到期时，queued 与 retry_wait 均在本轮准确恢复；不再存在固定候选倍数或 due 行饿死。0004 legacy backfill 为 pending 事件显式写 NULL deadline，SQLite/PG migration 与新索引一致。
  - R4 GREEN：Task 7+恢复+迁移 `115 passed`；Core unit `176 passed`；Core integration `37 passed`；Task 5/6 `49 passed`；fresh/default SQLite、PG offline DDL、compileall、pip check、diff-check 与根项目 `40 passed` 全部通过。


## Task 8：实现剧情分析、文案生成和脚本校验任务

- **状态：** 完成，待独立审查。
- **Commit：** `feat: expose short drama analysis tasks`（本 Task 独立提交；精确哈希由 Task 9 回填，避免提交自引用改变哈希）。
- **Task 7 Gate 回填：** 独立复审 R5 对 `6e9fca1` 的 Spec Compliance 与 Code Quality 均为 PASS，Critical/Important 均为 0；可靠 dispatch 的持久 `recover_after` 公平性缺口已关闭。
- **TDD RED：**
  - 初次执行 `.venv/bin/pytest tests/unit/test_short_drama_adapter.py -q`，真实在收集阶段失败于 `ModuleNotFoundError: No module named 'core_api.adapters.narrato.short_drama'`（1 个 collection error），确认目标 Adapter 尚不存在。
  - 后续先补再修的真实行为 RED 包括：供应商 scene 改变显式 source 首次出现顺序未被拒绝（`1 failed`）；合法 UTF-16 SRT 在纯文本提取处失败（`1 failed`）；未配置 Provider 在领取 attempt 前抛错（`1 failed`）；analysis Artifact source map 与脚本请求不一致仍成功（`1 failed`）；模型语言不匹配仍返回 202（`1 failed`）；新能力 phase 终态仍为 `None`（`1 failed`）。
- **最小实现：**
  - 新增薄 `ShortDramaProvider` Protocol、确定性 `FakeShortDramaProvider` 与注入式 `ShortDramaAdapter`；固定链路为显式字幕剧情分析、文案生成、画面匹配、完整确定性校验、最多一次 repair、再次完整校验。供应商临时错误为 retryable，输入/格式/校验错误为 non-retryable；未配置真实 Provider 在 attempt 内稳定失败，禁止回退 Fake。
  - source 数组是唯一顺序事实，`source_asset_id` 唯一；字幕只来自显式业务 URL 或 Core subtitle Artifact，本 Task 不隐式 ASR。validator 校验非空数组/字段类型/未知 source/首次出现顺序/非负时间/end>start/媒体时长/同源有序/非空 narration，Task2 纯服务统一裁剪公开字段，不保留本地路径或供应商私有字段。
  - 新增 `POST /api/v1/video-analysis/tasks` 与 `POST /api/v1/script-generation/tasks`：固定 Bearer、非空幂等 Key、extra forbid、1～5 sources、安全 CDN URL、稳定模型 ID、能力类型与语言校验；保存 model/catalog/provider 与用户配置不可变快照。相同公开请求在能力后续停用时仍返回首次 202 快照，异体保持 409。
  - handler registry 接入 Task7 state-version/not-before claim、attempt lease、周期 heartbeat、上传前 fencing、retry_wait/backoff 和 recovery；analysis/script 分别记录稳定 phase，重复 wake 不重复执行或登记 Artifact。
  - analysis 成功登记 UTF-8 canonical `analysis` JSON；script 成功登记 `timeline` 与 `editor_draft` JSON。内容包含 schema/model/source mapping，不含 provider raw、secret 或服务器路径；JSON/SRT 均有 5 MiB 上限，analysis Artifact 必须绑定相同 source order。
- **GREEN 验证：**
  - Task 8 指定 unit/integration/Fake E2E：`30 passed, 1 warning`。覆盖 invalid→一次 repair→success、repair 后仍无效、显式 B/A 顺序、duplicate wake、retryable→retry_wait→attempt 2 恢复、Artifact 内容/登记、能力/鉴权/幂等/extra/source 守卫。
  - Core 全 unit + integration：`238 passed, 12 warnings`。
  - `.venv/bin/alembic upgrade head && .venv/bin/alembic check`：PASS，`No new upgrade operations detected.`；`.venv/bin/python -m compileall core_api`：PASS。
  - 原项目指定 Python 3.11 回归：`20 passed, 3 warnings in 15.74s`。
  - `/opt/homebrew/bin/ruff check`（本 Task 修改文件）、公开 Docstring AST 扫描与 `git diff --check`：PASS。
- **关键决策与计划偏差：**
  - Implementation Plan 只列两个路由和一个 Adapter 文件；按 design 的能力停用、幂等首次响应、持久恢复和 Artifact 要求，最小扩展 TaskService 公开请求摘要重放、语言能力校验及 handler phase 更新，不新增表或迁移。
  - 使用 Task7 两类 CDN policy：业务输入限定 `/narrato/api/`，Core 产物限定 `/narrato/coreApi/`；不放宽 SSRF、重定向或路径规则。
  - 默认 Fake Provider 不访问网络；真实供应商 Adapter/Smoke 按 Goal 属可选外部条件，未知 provider 不静默回退并稳定终止 attempt。
- **自审结论：** repair 调用上限、source order、能力校验、首次幂等、JSON schema/size、Artifact fencing/登记、duplicate/recovery、GET/POST/no cancel、中文 Docstring、无 Task9 TTS/render 越界均通过。
- **剩余风险：**
  - 当前真实 LLM Provider 未配置凭据且未执行真实 Smoke；按 Goal 不作为本 Task 阻塞，Fake Provider E2E 已覆盖协议与恢复主链。
  - Core 唯一直接告警为既有 Starlette TestClient 弃用；integration 的 Alembic/sqlite3 告警和原项目 Pydantic 告警均为既有弃用告警。

### Task 8 独立审查修复

- **审查 RED：** 独立复审发现 1 Critical + 3 Important；新增 validator 类型/finite/allowlist 测试首次为 `3 failed, 20 passed`，分别复现数字字符串与 NaN 被接受、私有字段未裁剪。
- **C1 关闭：** 新增 `NarratoShortDramaProvider`，薄适配既有 `SubtitleAnalyzerAdapter` 的分析、正文生成、画面匹配和一次修复；生产 resolver 使用冻结 provider/model/base URL 与配置内 secret，未知 provider 保持 unavailable 且不回退 Fake。无网络注入测试证明 `provider_model_code` 和四段既有能力调用。
- **I1/I2/I3 关闭：** validator 仅接受有限真数并自行生成公开 DTO；analysis Artifact 保存完整安全 source map，script 严格验证必需 metadata/顺序/字幕引用；任务冻结 provider/model/secret_ref/公开 settings/limits/capability/language，Worker 只消费冻结快照，公开 Artifact 仅投影稳定 model/catalog 及 language/config/full source map。
- **复验：** Task 8 指定测试 `38 passed, 1 warning`；Core unit + integration + Task 8 Fake E2E `251 passed, 12 warnings`；原项目短剧回归 `12 passed, 1 warning`；compileall 与 `git diff --check` PASS。
- **剩余风险：** 真实供应商凭据 Smoke 仍为可选外部条件；生产 resolver 已由 Fake transport 无网络契约测试覆盖。

### Task 8 独立审查 R2 修复

- **R2 RED：** Core 独立 venv 首次导入真实 `SubtitleAnalyzerAdapter` 失败于 `ModuleNotFoundError: loguru`；新增真实 Adapter、重试分类和配置应用测试后为 `8 failed, 25 passed`，复现依赖不闭合、异常泄漏、503/中英文超时与限流未重试等缺口。
- **生产装配：** `coreApi/pyproject.toml` 显式声明 `loguru/openai/pillow/requests/toml`；移除 `app.config` 未使用且会引入 Streamlit/媒体栈的 `app.utils` import。resolver 只声明 Fake 与仓库真实注册的 OpenAI-compatible；生产 factory 显式注册 `OpenAICompatibleTextProvider` 并构造真实 `SubtitleAnalyzerAdapter`。Core venv 实际 import/construct 输出 `REAL_ADAPTER_OK`，`pip check` 为 `No broken requirements found`。
- **真实四段契约：** 使用真实 `SubtitleAnalyzerAdapter` 类，仅 monkeypatch `UnifiedLLMService` 网络层，验证 analysis→copy→match invalid→exactly-one repair→validator；兼容真实 `{"items": [...]}` / list 返回并统一 sanitize。
- **字幕继承：** script 请求省略字幕时，从 analysis Artifact source map 继承冻结 subtitle URL/Core Artifact/text，重新按 SRT 协议读取后把真实字幕传给 Provider；最终 timeline/editor Artifact 使用 resolved source map。显式提供的字幕引用仍必须精确一致。
- **配置与限制：** 冻结并应用 `prompt_category`、`original_sound_ratio`（77 用例）、`narration_style`；只持久化并执行 `max_input_chars/max_output_items`，其他 model/provider limit 不进入执行快照，禁止静默接受未使用字段。
- **重试分类：** 遍历 exception cause/context，按 httpx/requests timeout/connection、408/429/5xx 与常见中英文超时/限流文本进入 retry；4xx 参数和 validation 保持 non-retryable，公开错误仍为稳定码。
- **R2 GREEN：** Task 8 指定 `49 passed, 1 warning`；Core 全量 `262 passed, 12 warnings`；根项目回归 `26 passed, 3 warnings`；pip install/check、真实 import/construct、compileall、ruff、diff-check 全部通过。

### Task 8 独立审查 R3 修复

- **R3 RED：** 新增 clean Core 启动、双 Provider 并发隔离、日志内容泄漏及异常文本分类测试，首次为 `5 failed, 37 passed`：任意 cwd 且无 `PYTHONPATH` 时 `No module named app`，factory 不支持 request-local client，legacy 输出完整 prompt，502/503 文本未进入 retry。
- **请求级生产 Provider：** 默认生产路径改为 Core-local、每 attempt 私有 `openai.OpenAI(api_key=<snapshot secret>, base_url=<snapshot base>)`；每次 completion 都显式传冻结 `provider_model_code`，不读取根 config、不注册 `LLMServiceManager`、不使用进程 singleton/cache。保留 `analyzer_factory` 仅作为测试兼容注入，不进入生产 resolver。
- **隔离证据：** 双线程同时运行 model-a/secret-a/base-a 与 model-b/secret-b/base-b，Fake transport 捕获每次真实 outgoing 参数，集合严格为两套冻结三元组且无交叉；四段 analysis/generation/matching/repair 仍走相同 validator 与 exactly-one repair。
- **clean 启动：** 新增 `core_api.legacy_bootstrap`，基于已安装 `core_api` 模块 `__file__` 明确定位单仓库 legacy app，不依赖 cwd 或手工 `PYTHONPATH`。从 `/private/tmp` 用 Core venv 导入 `core_api.main` 与 Celery tasks 输出 `CORE_CLEAN_START_OK`。
- **重试与日志：** cause/message 分类补 500/502/503/504、server/gateway/service unavailable、connection reset 与中文上游不可用；validation/4xx 保持 non-retryable。Core JSON logger 只记录 stage、长度、SHA-256；legacy migration adapter 的完整 prompt 日志改为长度/hash，unique prompt/response/secret 捕获和静态 log-content scan 均无泄漏。
- **R3 GREEN：** Task 8 指定 `57 passed, 1 warning`；Core 全量 `270 passed, 12 warnings`；根项目含 legacy Adapter 回归 `35 passed, 3 warnings`；并发/日志专项 `3 passed`；clean start、pip check、compileall、ruff、diff-check、log scan 全部通过。

### Task 8 独立审查 R4 修复

- **R4 RED：** 新增四阶段 legacy 异常唯一敏感串、四次真实 outgoing body 与完整 timeline schema 断言，首次为 `5 failed, 42 passed, 1 warning`：analysis/generation/matching/repair 均把供应商异常正文带入日志或返回值，冻结 `temperature=0.77` 实际仍发送 `[0.7, 0.7, 0.3, 0.3]`。
- **日志闭环：** `migration_adapter` 四阶段及相邻 async/vision/narration 异常路径统一只记录 `stage/error_type/code`，公开返回固定 `LLM_STAGE_FAILED`；不再记录 `str(e)`、traceback、供应商响应、字幕、prompt 或 secret。专项用四个不同敏感串逐路径验证日志与返回均无原文。
- **生产请求契约：** 请求冻结的 `temperature` 现在贯穿 analysis/generation/matching/repair 四次 outgoing request；matching/repair prompt 均携带严格 `items` JSON 契约、`source_asset_id/start/end/narration` 语义、有限数约束、显式 source order 与每个 source duration。Fake transport 逐请求捕获并断言四次 model、temperature、JSON mode 和完整 source map；未支持的模型配置仍由请求 schema/快照 allowlist 拒绝，不静默接受未执行字段。
- **可安装打包：** wheel 同时打包 `core_api` 与 Worker 必需的 legacy `app` 模块；`fun_asr_subtitle` 去除对 Streamlit-heavy `app.utils` 的顶层依赖。`legacy_bootstrap` 优先使用已安装 `app`，仅在显式 `NARRATO_CORE_ENABLE_MONOREPO_FALLBACK=1` 时允许基于仓库路径的开发 fallback，生产缺包返回明确启动错误。
- **R4 GREEN：** Task 8 指定 `61 passed, 1 warning`；Core 全量 `274 passed, 12 warnings`；根项目相关回归 `52 passed`；`python -m build --wheel --no-isolation` 成功。最终 wheel 安装到全新 `/private/tmp/task8-wheel-venv-final` 后，在仓库外 cwd 且移除 `PYTHONPATH` 可导入 `core_api.main`、Celery tasks、media/ASR legacy 模块，并构造 media/asr/analysis 三 Adapter 的 `AtomicTaskHandler`，输出 `FINAL_WHEEL_SMOKE_OK`；`pip check` 为 `No broken requirements found`。compileall、ruff format/check、diff-check 与静态敏感日志 scan 均通过。
- **剩余风险：** 真实供应商凭据 Smoke 仍为 Goal 明确允许的可选外部条件；wheel 的 FFprobe/FunASR 实际调用仍依赖部署环境提供对应本地进程与二进制，但 import、装配和 Fake Provider 路径已在 clean venv 验证。

### Task 8 独立审查 R5 修复

- **R5 RED：** 真实 `OpenAICompatibleTextProvider -> UnifiedLLMService` 异常链、四阶段 outgoing token 配额与模型上限测试首次为 `3 failed, 46 passed`：Loguru 泄漏 unique response/subtitle/secret，四次请求均缺 `max_tokens`，超过冻结模型限额未拒绝。
- **日志与 token 契约：** 新增统一安全错误元数据，仅记录 `stage/error_type/code/error_length/error_sha256`；Unified、真实 OpenAI-compatible provider、manager 与 migration 全链不记录异常正文或 traceback。`max_tokens` 进入公共 config 与 provider/model 冻结 allowlist，创建任务时超过冻结上限明确返回 422；analysis/generation/matching/repair 四次请求均发送同一冻结 `temperature/max_tokens`，Fake transport 逐 body 验证。
- **Selective wheel：** custom `build_py` 仅发布 `app` 骨架及 Core Worker 真正使用的 `app.services.media_probe`、`app.services.fun_asr_subtitle`；wheel RECORD 不含 test、`app.utils`、voice、generate_video 或无关 legacy LLM/UI 模块，直接依赖 requests/loguru 已在 METADATA 声明。全新 `/private/tmp/task8-r5-venv`、仓库外 cwd、无 `PYTHONPATH` 下用 fake subprocess 运行 media probe、小型 Fake HTTP/字幕 fixture 运行 FunASR、Fake Provider 真实执行 `AtomicTaskHandler` analysis 并登记 Artifact；未发布模块均为 `ModuleNotFoundError`，`pip check` 无 broken requirements。
- **R5 GREEN：** Task 8 指定 `64 passed, 1 warning`；Core 全量 `277 passed, 12 warnings`；根项目相关回归 `53 passed, 1 warning`；selective runtime 输出 `R5_SELECTIVE_RUNTIME_SMOKE_OK`。ruff、compileall、diff-check 和目标日志静态 scan 通过。

### Task 8 独立审查 R6 修复

- **R6 RED：** direct checkout 可构建 selective wheel，但 `python -m build --sdist` 后从解压 release tree 重建的 wheel 完全缺少 `app`，证明外部 sibling `../app` 未进入 sdist，发布链不可重复。
- **可重复发布源：** 将严格四文件 legacy runtime 以受控 `vendor_legacy/app` 源树纳入 Core sdist；direct wheel 与 sdist→wheel 均只发现该源树。自动化同步测试逐字节比较 monorepo source，roundtrip 测试复制 clean source、构建 sdist、解压重建 wheel，并断言 sdist vendor 与 wheel RECORD 都严格等于四文件白名单，无 tests/utils/voice 等漂移。
- **R6 runtime：** direct wheel 和 sdist 重建 wheel 分别安装到全新 venv；仓库外 cwd、无 `PYTHONPATH` 下均实跑 media probe、Fake HTTP/SRT FunASR、AtomicTaskHandler analysis Artifact，以及 invalid→exactly-one repair→valid script，未发布模块保持 `ModuleNotFoundError`，两次输出 `R6_RELEASE_RUNTIME_SMOKE_OK` 且 `pip check` 无 broken requirements。
- **R6 GREEN：** Task 8 指定 `64 passed, 1 warning`；Core 全量（含 2 个发布 roundtrip 测试）`279 passed, 12 warnings`；根项目相关回归 `53 passed, 1 warning`；direct/sdist build、RECORD 白名单、ruff、compileall 与 diff-check 均通过。
