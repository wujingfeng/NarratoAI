# NarratoAI 多用户 API 平台 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立独立的 `narratoApi` 与 `coreApi`，打通多用户短剧解说从登录、OSS 上传、异步分析、人工编辑、一次最终渲染到结果导出的完整链路。

**Architecture:** `narratoApi` 是业务控制面，以 PostgreSQL 持久化项目、积分和版本化 DAG；`coreApi` 是能力执行面，将现有 NarratoAI Python 能力包装为异步原子任务。两者使用独立数据库，经固定 Bearer Token、回调和持续轮询通信，媒体统一通过公开阿里云 OSS/CDN URL 交换。

**Tech Stack:** Python 3.12、FastAPI、Pydantic v2、SQLAlchemy 2、Alembic、PostgreSQL、Redis、Celery、httpx、oss2、pytest、React 19、Vite、File System Access API、Supervisor、Nginx。

## Global Constraints

- 正式架构以 `docs/superpowers/specs/2026-07-16-narrato-api-platform-design.md` 为唯一需求基线。
- 业务项目固定在 `docs/api/narratoApi/`，能力 API 固定在 `coreApi/`；数据库、虚拟环境、配置和进程完全隔离。
- 自有 HTTP API 只允许 `GET`、`POST`；所有耗时能力必须异步，普通查询、保存、费用试算和剪映 Manifest 生成可同步。
- 第一版只实现短剧解说；每项目最多 5 个视频，每个视频最长 10 分钟、最大 300 MiB；SRT 最大 5 MiB。
- 计费固定为 `ceil(total_seconds / 60) * 20`，注册默认赠送 100 点；最终系统失败全额退款。
- 用户不能取消或手动重试；终态失败不可恢复；仅 `completed`、`failed` 项目可删除。
- `waiting_for_edit` 永久等待，不自动失败、不退款；提交最终渲染后立即锁定且只能渲染一次。
- 失败项目不能导出；剪映 ZIP 不入库、不上传，由桌面 Chrome/Edge 根据 Manifest 流式生成。
- 所有公开类、函数、方法、路由使用简洁中文 Docstring，关键状态迁移和幂等分支使用中文行内注释；英文标识符。
- PostgreSQL 是业务事实源；Redis 仅用于 Celery、单点 Token、验证码、限流、缓存和短期锁。
- 第一版不实现管理后台、在线支付、团队租户、节点计费、GPU、Docker、分片上传或私有 CDN。
- 每个 Task 必须先写失败测试，再实现最小功能；任务结束时运行指定测试并独立提交。

---

## Phase 0：执行前隔离与基线

### Task 1: 建立实施工作区与验证基线

**Files:**
- Read: `AGENTS.md`
- Read: `docs/editor-implementation-constraints.md`
- Read: `docs/superpowers/specs/2026-07-16-narrato-api-platform-design.md`
- Read: `requirements.txt`
- Read: `conftest.py`

**Interfaces:**
- Consumes: 当前仓库与已确认架构文档。
- Produces: 隔离 worktree、Python 3.12 虚拟环境策略、可复现的旧项目测试基线。

- [ ] **Step 1: 创建隔离 worktree**

使用 `superpowers:using-git-worktrees`，创建 `codex/narrato-api-platform` 分支；不得在当前包含大量未提交改动的目录直接实施。

- [ ] **Step 2: 记录运行时版本**

Run:

```bash
python3.12 --version
node --version
npm --version
ffmpeg -version | head -1
```

Expected: Python 为 `3.12.x`，Node、npm、FFmpeg 均能输出版本。

- [ ] **Step 3: 执行现有短剧能力回归基线**

Run:

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

Expected: 全部通过；若存在基线失败，先记录精确失败并停止新增功能。

- [ ] **Step 4: Commit**

此 Task 不修改业务文件，不创建提交。

---

## Phase 1：现有 NarratoAI 能力去 UI 化与并发隔离

### Task 2: 提取纯 Python 短剧服务与媒体探测

**Files:**
- Create: `app/services/media_probe.py`
- Create: `app/services/short_drama_narration_service.py`
- Create: `tests/test_media_probe.py`
- Create: `tests/test_short_drama_narration_service.py`
- Modify: `webui/tools/generate_short_summary.py`
- Modify: `app/services/generate_video.py`

**Interfaces:**
- Consumes: `SubtitleAnalyzerAdapter`、现有字幕和短剧校验函数。
- Produces: `probe_media(path: str) -> MediaInfo`、`build_short_drama_script(request: ShortDramaAnalysisRequest) -> list[dict]`。

- [ ] **Step 1: 写媒体探测失败测试**

```python
def test_probe_media_returns_normalized_metadata(sample_mp4):
    info = probe_media(str(sample_mp4))
    assert info.duration_seconds > 0
    assert info.container == "mp4"
    assert info.width > 0 and info.height > 0
    assert info.has_video is True
```

- [ ] **Step 2: 写短剧服务无 Streamlit 依赖测试**

```python
def test_short_drama_service_imports_without_streamlit(monkeypatch):
    monkeypatch.setitem(sys.modules, "streamlit", None)
    module = importlib.import_module("app.services.short_drama_narration_service")
    assert callable(module.build_short_drama_script)
```

- [ ] **Step 3: 运行测试确认失败**

Run: `python3.12 -m pytest tests/test_media_probe.py tests/test_short_drama_narration_service.py -q`

Expected: FAIL，提示目标模块或函数不存在。

- [ ] **Step 4: 实现稳定接口并让 WebUI 改用新服务**

核心类型必须固定为：

```python
@dataclass(frozen=True, slots=True)
class MediaInfo:
    duration_seconds: float
    container: str
    video_codec: str | None
    audio_codec: str | None
    width: int | None
    height: int | None
    has_video: bool
    has_audio: bool

def probe_media(path: str) -> MediaInfo:
    """使用 FFprobe 返回统一媒体元数据，探测失败时抛出 MediaProbeError。"""
```

`webui/tools/generate_short_summary.py` 只保留 Streamlit 展示、状态和进度适配；JSON 修复、多视频来源归一化、字符区间构建迁入新服务。

- [ ] **Step 5: 回归旧能力**

Run:

```bash
python3.12 -m pytest -q \
  tests/test_media_probe.py \
  tests/test_short_drama_narration_service.py \
  webui/tools/test_generate_short_summary_unittest.py \
  app/services/test_short_drama_narration_validation_unittest.py
```

Expected: PASS。

- [ ] **Step 6: Commit**

```bash
git add app/services/media_probe.py app/services/short_drama_narration_service.py \
  tests/test_media_probe.py tests/test_short_drama_narration_service.py \
  webui/tools/generate_short_summary.py app/services/generate_video.py
git commit -m "refactor: isolate short drama core services"
```

### Task 3: 消除共享状态、隐式字幕匹配与共享工作目录

**Files:**
- Create: `app/runtime/__init__.py`
- Create: `app/runtime/task_workspace.py`
- Create: `tests/test_task_workspace_isolation.py`
- Create: `tests/test_task_no_cross_task_globals.py`
- Modify: `app/services/task.py`
- Modify: `app/services/material.py`
- Modify: `app/services/jianying_task.py`
- Modify: `app/utils/utils.py`

**Interfaces:**
- Consumes: `task_id`、`attempt_no`、显式视频/字幕路径。
- Produces: `TaskWorkspace`、无模块级任务产物变量的渲染函数。

- [ ] **Step 1: 写工作区隔离测试**

```python
def test_attempt_workspaces_never_share_paths(tmp_path):
    first = TaskWorkspace.create(tmp_path, "ctask_a", 1)
    second = TaskWorkspace.create(tmp_path, "ctask_a", 2)
    assert first.root != second.root
    assert first.temp_dir.parent == first.root
```

- [ ] **Step 2: 写并发任务产物不串写测试**

```python
def test_render_state_is_local_to_each_invocation():
    source = inspect.getsource(task.start_subclip_unified)
    assert "global merged_audio_path" not in source
    assert "global merged_subtitle_path" not in source
```

- [ ] **Step 3: 运行测试确认失败**

Run: `python3.12 -m pytest tests/test_task_workspace_isolation.py tests/test_task_no_cross_task_globals.py -q`

Expected: FAIL。

- [ ] **Step 4: 实现显式工作区和路径输入**

```python
@dataclass(frozen=True, slots=True)
class TaskWorkspace:
    root: Path
    temp_dir: Path
    output_dir: Path

    @classmethod
    def create(cls, base: Path, task_id: str, attempt_no: int) -> "TaskWorkspace":
        root = base / task_id / str(attempt_no)
        temp_dir, output_dir = root / "temp", root / "output"
        temp_dir.mkdir(parents=True, exist_ok=False)
        output_dir.mkdir(parents=True, exist_ok=True)
        return cls(root=root, temp_dir=temp_dir, output_dir=output_dir)
```

删除按全局目录、文件 stem 和“最新文件”猜测字幕的路径；调用方必须显式传入字幕资产。

- [ ] **Step 5: 运行并发与旧能力回归**

Run:

```bash
python3.12 -m pytest -q \
  tests/test_task_workspace_isolation.py \
  tests/test_task_no_cross_task_globals.py \
  app/services/test_task_subtitle_resolution_unittest.py \
  app/services/test_jianying_task_unittest.py
```

Expected: PASS。

- [ ] **Step 6: Commit**

```bash
git add app/runtime/task_workspace.py tests/test_task_workspace_isolation.py \
  tests/test_task_no_cross_task_globals.py app/services/task.py app/services/material.py \
  app/services/jianying_task.py app/utils/utils.py
git commit -m "fix: isolate media task workspaces"
```

---

## Phase 2：coreApi 基础设施与可靠任务内核

### Task 4: 创建 coreApi FastAPI 骨架

**Files:**
- Create: `coreApi/pyproject.toml`
- Create: `coreApi/config.example.toml`
- Create: `coreApi/alembic.ini`
- Create: `coreApi/migrations/env.py`
- Create: `coreApi/migrations/versions/0001_core_base.py`
- Create: `coreApi/core_api/__init__.py`
- Create: `coreApi/core_api/main.py`
- Create: `coreApi/core_api/config.py`
- Create: `coreApi/core_api/database.py`
- Create: `coreApi/core_api/logging.py`
- Create: `coreApi/core_api/celery_app.py`
- Create: `coreApi/core_api/api/router.py`
- Create: `coreApi/core_api/api/responses.py`
- Create: `coreApi/core_api/api/errors.py`
- Create: `coreApi/core_api/api/dependencies.py`
- Create: `coreApi/core_api/api/routes/health.py`
- Create: `coreApi/tests/unit/test_health.py`
- Create: `coreApi/tests/unit/test_http_contract.py`

**Interfaces:**
- Consumes: Core TOML 路径和固定服务 Bearer Token。
- Produces: `create_app() -> FastAPI`、统一响应/异常、健康检查和 SQLAlchemy 会话。

- [ ] **Step 1: 写健康检查和 HTTP 方法失败测试**

```python
def test_health_returns_envelope(client):
    response = client.get("/api/v1/health/live")
    assert response.status_code == 200
    assert response.json()["code"] == "OK"

def test_openapi_contains_only_get_and_post(client):
    paths = client.get("/openapi.json").json()["paths"].values()
    methods = {method for path in paths for method in path}
    assert methods <= {"get", "post"}
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd coreApi && python3.12 -m pytest tests/unit/test_health.py tests/unit/test_http_contract.py -q`

Expected: FAIL。

- [ ] **Step 3: 实现最小应用内核**

统一响应模型：

```python
class ApiResponse(BaseModel, Generic[T]):
    code: str
    message: str
    data: T | None = None
    request_id: str
```

`create_app()` 必须注册请求 ID、中间件、统一异常处理和 `/api/v1` Router；真实密钥仅从指定 TOML 读取。

- [ ] **Step 4: 创建并验证首次迁移**

Run:

```bash
cd coreApi
python3.12 -m alembic upgrade head
python3.12 -m alembic check
python3.12 -m pytest tests/unit/test_health.py tests/unit/test_http_contract.py -q
```

Expected: Alembic 无待生成差异，测试 PASS。

- [ ] **Step 5: Commit**

```bash
git add coreApi
git commit -m "feat: scaffold core api service"
```

### Task 5: 实现 Core Task、Attempt、租约与 Callback Outbox

**Files:**
- Create: `coreApi/core_api/tasks/models.py`
- Create: `coreApi/core_api/tasks/schemas.py`
- Create: `coreApi/core_api/tasks/state_machine.py`
- Create: `coreApi/core_api/tasks/service.py`
- Create: `coreApi/core_api/tasks/leases.py`
- Create: `coreApi/core_api/tasks/callbacks.py`
- Create: `coreApi/core_api/tasks/celery_tasks.py`
- Create: `coreApi/core_api/runtime/process_runner.py`
- Create: `coreApi/migrations/versions/0002_core_tasks.py`
- Create: `coreApi/tests/unit/test_task_state_machine.py`
- Create: `coreApi/tests/unit/test_leases.py`
- Create: `coreApi/tests/unit/test_callback_outbox.py`
- Create: `coreApi/tests/unit/test_process_runner.py`

**Interfaces:**
- Consumes: 原子任务类型和 JSON 输入快照。
- Produces: `create_core_task()`、`acquire_lease()`、`heartbeat()`、`complete_attempt()`、可靠回调 Outbox。

- [ ] **Step 1: 写状态机与迟到结果测试**

```python
def test_stale_attempt_cannot_complete_task(task_service, task):
    first = task_service.start_attempt(task.id)
    second = task_service.expire_and_restart(first.id)
    with pytest.raises(StaleLeaseError):
        task_service.complete_attempt(first.id, first.lease_token, [])
    task_service.complete_attempt(second.id, second.lease_token, [])
```

- [ ] **Step 2: 写 Outbox 去重测试**

```python
def test_terminal_callback_is_written_once(session, task_service, task):
    task_service.mark_succeeded(task.id, event_id="evt_1")
    task_service.mark_succeeded(task.id, event_id="evt_1")
    assert session.scalar(select(func.count(CallbackOutbox.id))) == 1
```

- [ ] **Step 3: 运行测试确认失败**

Run: `cd coreApi && python3.12 -m pytest tests/unit/test_task_state_machine.py tests/unit/test_leases.py tests/unit/test_callback_outbox.py -q`

Expected: FAIL。

- [ ] **Step 4: 实现状态、租约和进程治理**

状态只允许：

```python
class CoreTaskStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    RETRY_WAIT = "retry_wait"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
```

`ProcessRunner` 使用 `subprocess.Popen`、独立进程组、周期心跳、超时终止和 stdout/stderr 截断；用户取消不进入状态机。

- [ ] **Step 5: 运行测试与迁移**

Run:

```bash
cd coreApi
python3.12 -m alembic upgrade head
python3.12 -m pytest tests/unit/test_task_state_machine.py tests/unit/test_leases.py \
  tests/unit/test_callback_outbox.py tests/unit/test_process_runner.py -q
```

Expected: PASS。

- [ ] **Step 6: Commit**

```bash
git add coreApi/core_api/tasks coreApi/core_api/runtime/process_runner.py \
  coreApi/migrations/versions/0002_core_tasks.py coreApi/tests/unit
git commit -m "feat: add durable core task runtime"
```

### Task 6: 实现统一能力目录

**Files:**
- Create: `coreApi/core_api/capabilities/models.py`
- Create: `coreApi/core_api/capabilities/schemas.py`
- Create: `coreApi/core_api/capabilities/service.py`
- Create: `coreApi/core_api/capabilities/seed.py`
- Create: `coreApi/core_api/api/routes/capabilities.py`
- Create: `coreApi/migrations/versions/0003_core_capabilities.py`
- Create: `coreApi/tests/unit/test_capability_catalog.py`

**Interfaces:**
- Consumes: Core 数据库能力记录和 TOML `secret_ref`。
- Produces: `GET /api/v1/capabilities`、稳定 `model_id`/`voice_id`、统一 DTO。

- [ ] **Step 1: 写供应商无关结构测试**

```python
def test_voice_catalog_has_same_shape_for_all_providers(client, auth_header):
    items = client.get("/api/v1/capabilities", headers=auth_header).json()["data"]["voices"]
    expected = {"voice_id", "provider_code", "name", "languages", "gender", "styles",
                "sample_url", "supported_formats", "supported_sample_rates"}
    assert items and all(set(item) == expected for item in items)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd coreApi && python3.12 -m pytest tests/unit/test_capability_catalog.py -q`

Expected: FAIL。

- [ ] **Step 3: 实现目录、种子与停用规则**

只返回数据库启用且 `secret_ref` 能从 TOML 解析成功的记录；未知能力 ID 必须返回 `CAPABILITY_UNAVAILABLE`，禁止静默回退默认供应商。

- [ ] **Step 4: 验证**

Run: `cd coreApi && python3.12 -m alembic upgrade head && python3.12 -m pytest tests/unit/test_capability_catalog.py -q`

Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add coreApi/core_api/capabilities coreApi/core_api/api/routes/capabilities.py \
  coreApi/migrations/versions/0003_core_capabilities.py coreApi/tests/unit/test_capability_catalog.py
git commit -m "feat: add normalized capability catalog"
```

---

## Phase 3：Core 短剧原子能力

### Task 7: 实现 OSS、媒体探测和 ASR 原子任务

**Files:**
- Create: `coreApi/core_api/infrastructure/oss_client.py`
- Create: `coreApi/core_api/runtime/workspace.py`
- Create: `coreApi/core_api/runtime/artifact_store.py`
- Create: `coreApi/core_api/adapters/narrato/media_probe.py`
- Create: `coreApi/core_api/adapters/narrato/asr.py`
- Create: `coreApi/core_api/api/routes/media_probe.py`
- Create: `coreApi/core_api/api/routes/asr.py`
- Create: `coreApi/tests/unit/test_oss_object_keys.py`
- Create: `coreApi/tests/unit/test_media_probe_adapter.py`
- Create: `coreApi/tests/integration/test_media_probe_task.py`
- Create: `coreApi/tests/integration/test_asr_task.py`

**Interfaces:**
- Consumes: 公开 CDN URL、显式媒体类型、Core Task ID。
- Produces: `media_probe` 与 `asr` 异步任务、`narrato/coreApi/YYYY/MM/DD/<md5>.<ext>` 产物。

- [ ] **Step 1: 写对象键与媒体限制测试**

```python
def test_core_object_key_uses_required_prefix():
    key = build_object_key(now=date(2026, 7, 16), extension="srt", seed="fixed")
    assert re.fullmatch(r"narrato/coreApi/2026/07/16/[0-9a-f]{32}\.srt", key)

def test_probe_rejects_video_over_ten_minutes(fake_probe):
    fake_probe.duration_seconds = 600.001
    with pytest.raises(MediaConstraintError):
        validate_video(fake_probe)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd coreApi && python3.12 -m pytest tests/unit/test_oss_object_keys.py tests/unit/test_media_probe_adapter.py -q`

Expected: FAIL。

- [ ] **Step 3: 实现下载白名单、工作区和适配器**

Core 只允许配置中的 CDN Host 和 `narrato/api/` 前缀作为用户输入；每个 attempt 下载到独立工作区。ASR Adapter 调用现有 `app.services.fun_asr_subtitle`，输出统一 SRT Artifact。

- [ ] **Step 4: 验证**

Run:

```bash
cd coreApi
python3.12 -m pytest tests/unit/test_oss_object_keys.py tests/unit/test_media_probe_adapter.py \
  tests/integration/test_media_probe_task.py tests/integration/test_asr_task.py -q
```

Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add coreApi/core_api/infrastructure/oss_client.py coreApi/core_api/runtime \
  coreApi/core_api/adapters/narrato/media_probe.py coreApi/core_api/adapters/narrato/asr.py \
  coreApi/core_api/api/routes/media_probe.py coreApi/core_api/api/routes/asr.py coreApi/tests
git commit -m "feat: expose media probe and asr tasks"
```

### Task 8: 实现剧情分析、文案生成和脚本校验任务

**Files:**
- Create: `coreApi/core_api/adapters/narrato/short_drama.py`
- Create: `coreApi/core_api/api/routes/video_analysis.py`
- Create: `coreApi/core_api/api/routes/script_generation.py`
- Create: `coreApi/tests/unit/test_short_drama_adapter.py`
- Create: `coreApi/tests/integration/test_analysis_tasks.py`
- Create: `coreApi/tests/e2e/test_short_drama_analysis_fake_provider.py`

**Interfaces:**
- Consumes: 排序后的视频、SRT/ASR 产物、模型稳定 ID、用户配置快照。
- Produces: 分析 JSON、初始编辑草稿 JSON、确定性校验通过的时间线。

- [ ] **Step 1: 写“最多一次修复”失败测试**

```python
def test_invalid_script_is_repaired_once(adapter, fake_llm):
    fake_llm.match_results = [{"invalid": True}]
    fake_llm.repair_result = valid_script_fixture()
    result = adapter.generate_script(request_fixture())
    assert result == valid_script_fixture()
    assert fake_llm.repair_calls == 1
```

- [ ] **Step 2: 写多视频来源保持顺序测试**

```python
def test_script_preserves_explicit_video_source_order(adapter):
    result = adapter.generate_script(multi_video_request(["asset_b", "asset_a"]))
    assert [item["source_asset_id"] for item in result[:2]] == ["asset_b", "asset_a"]
```

- [ ] **Step 3: 运行测试确认失败**

Run: `cd coreApi && python3.12 -m pytest tests/unit/test_short_drama_adapter.py -q`

Expected: FAIL。

- [ ] **Step 4: 实现适配器和异步路由**

固定链路为“分析字幕 → 生成文案 → 匹配画面 → 确定性校验 → 最多一次 LLM repair → 再校验”。API 不暴露现有 `VideoClipParams` 或服务器本地路径。

- [ ] **Step 5: 验证**

Run:

```bash
cd coreApi
python3.12 -m pytest tests/unit/test_short_drama_adapter.py \
  tests/integration/test_analysis_tasks.py \
  tests/e2e/test_short_drama_analysis_fake_provider.py -q
```

Expected: PASS。

- [ ] **Step 6: Commit**

```bash
git add coreApi/core_api/adapters/narrato/short_drama.py \
  coreApi/core_api/api/routes/video_analysis.py \
  coreApi/core_api/api/routes/script_generation.py coreApi/tests
git commit -m "feat: expose short drama analysis tasks"
```

### Task 9: 实现 TTS、字幕、渲染、产物和剪映 Manifest

**Files:**
- Create: `coreApi/core_api/adapters/narrato/tts.py`
- Create: `coreApi/core_api/adapters/narrato/render.py`
- Create: `coreApi/core_api/adapters/narrato/jianying.py`
- Create: `coreApi/core_api/api/routes/tts.py`
- Create: `coreApi/core_api/api/routes/subtitle.py`
- Create: `coreApi/core_api/api/routes/video_render.py`
- Create: `coreApi/core_api/api/routes/jianying.py`
- Create: `coreApi/tests/unit/test_tts_adapter.py`
- Create: `coreApi/tests/unit/test_render_adapter.py`
- Create: `coreApi/tests/unit/test_jianying_manifest.py`
- Create: `coreApi/tests/e2e/test_short_drama_render_fake_provider.py`
- Modify: `app/services/jianying_draft_builder.py`

**Interfaces:**
- Consumes: 不可变编辑快照、稳定 `voice_id`、显式源媒体和工作区。
- Produces: MP4、SRT、合并配音、文案时间线 JSON Artifact；无状态 Jianying Manifest。

- [ ] **Step 1: 写渲染产物登记测试**

```python
def test_successful_render_registers_required_artifacts(render_service):
    result = render_service.render(render_request_fixture())
    assert {item.kind for item in result.artifacts} >= {"video", "subtitle", "voice", "timeline"}
    assert all(item.url.startswith("https://") for item in result.artifacts)
```

- [ ] **Step 2: 写剪映无 ZIP 副作用测试**

```python
def test_jianying_builder_returns_manifest_without_zip(tmp_path, builder):
    manifest = builder.build(jianying_request_fixture())
    assert manifest.package_name.endswith(".zip")
    assert all(entry.zip_path for entry in manifest.files)
    assert list(tmp_path.rglob("*.zip")) == []
```

- [ ] **Step 3: 运行测试确认失败**

Run: `cd coreApi && python3.12 -m pytest tests/unit/test_tts_adapter.py tests/unit/test_render_adapter.py tests/unit/test_jianying_manifest.py -q`

Expected: FAIL。

- [ ] **Step 4: 拆分现有剪映 Builder**

新增稳定接口：

```python
def build_jianying_base_files(request: JianyingBuildRequest) -> dict[str, str | bytes]:
    """生成剪映基础文件，但不复制 CDN 资源、不创建 ZIP。"""

def build_jianying_resource_manifest(request: JianyingBuildRequest) -> list[ManifestResource]:
    """将已完成任务的媒体映射成前端组包资源清单。"""
```

渲染适配器复用 `voice.tts_multiple`、`clip_video_unified`、`update_script_timestamps`、音频/字幕合并和 `merge_materials`，但所有路径必须位于 attempt workspace。

- [ ] **Step 5: 验证**

Run:

```bash
cd coreApi
python3.12 -m pytest tests/unit/test_tts_adapter.py tests/unit/test_render_adapter.py \
  tests/unit/test_jianying_manifest.py tests/e2e/test_short_drama_render_fake_provider.py -q
cd ..
python3.12 -m pytest app/services/test_script_subtitle_unittest.py \
  app/services/test_merger_video_concat_unittest.py app/services/test_jianying_task_unittest.py -q
```

Expected: PASS。

- [ ] **Step 6: Commit**

```bash
git add coreApi app/services/jianying_draft_builder.py
git commit -m "feat: expose render and jianying manifest capabilities"
```

---

## Phase 4：narratoApi 业务基础设施

### Task 10: 创建 narratoApi FastAPI 骨架

**Files:**
- Create: `docs/api/narratoApi/pyproject.toml`
- Create: `docs/api/narratoApi/config.example.toml`
- Create: `docs/api/narratoApi/alembic.ini`
- Create: `docs/api/narratoApi/migrations/env.py`
- Create: `docs/api/narratoApi/migrations/versions/0001_business_base.py`
- Create: `docs/api/narratoApi/narrato_api/__init__.py`
- Create: `docs/api/narratoApi/narrato_api/main.py`
- Create: `docs/api/narratoApi/narrato_api/config.py`
- Create: `docs/api/narratoApi/narrato_api/database.py`
- Create: `docs/api/narratoApi/narrato_api/redis_client.py`
- Create: `docs/api/narratoApi/narrato_api/celery_app.py`
- Create: `docs/api/narratoApi/narrato_api/api/router.py`
- Create: `docs/api/narratoApi/narrato_api/api/responses.py`
- Create: `docs/api/narratoApi/narrato_api/api/errors.py`
- Create: `docs/api/narratoApi/narrato_api/api/dependencies.py`
- Create: `docs/api/narratoApi/narrato_api/api/health.py`
- Create: `docs/api/narratoApi/tests/unit/test_health.py`
- Create: `docs/api/narratoApi/tests/unit/test_http_contract.py`

**Interfaces:**
- Consumes: 独立 TOML、PostgreSQL、Redis。
- Produces: 统一业务 API 内核、配置、迁移、日志、健康检查。

- [ ] **Step 1: 复用 Core 契约测试思想写失败测试**

测试响应 Envelope、Request ID、GET/POST 白名单、数据库未就绪时 `/ready` 返回 `503`。

- [ ] **Step 2: 运行测试确认失败**

Run: `cd docs/api/narratoApi && python3.12 -m pytest tests/unit/test_health.py tests/unit/test_http_contract.py -q`

Expected: FAIL。

- [ ] **Step 3: 实现独立业务应用内核**

不得导入 `app.services` 或 `core_api` 内部模块；服务间 DTO 在 `narrato_api/integrations/core_client.py` 内显式声明或由 OpenAPI 生成。

- [ ] **Step 4: 验证迁移和测试**

Run:

```bash
cd docs/api/narratoApi
python3.12 -m alembic upgrade head
python3.12 -m alembic check
python3.12 -m pytest tests/unit/test_health.py tests/unit/test_http_contract.py -q
```

Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add docs/api/narratoApi
git commit -m "feat: scaffold narrato business api"
```

### Task 11: 实现邮箱账户与 Redis 单点 Token

**Files:**
- Create: `docs/api/narratoApi/narrato_api/auth/models.py`
- Create: `docs/api/narratoApi/narrato_api/auth/schemas.py`
- Create: `docs/api/narratoApi/narrato_api/auth/service.py`
- Create: `docs/api/narratoApi/narrato_api/auth/router.py`
- Create: `docs/api/narratoApi/narrato_api/auth/tasks.py`
- Create: `docs/api/narratoApi/narrato_api/integrations/mail_client.py`
- Create: `docs/api/narratoApi/migrations/versions/0002_users.py`
- Create: `docs/api/narratoApi/tests/unit/test_email_codes.py`
- Create: `docs/api/narratoApi/tests/unit/test_single_session_token.py`
- Create: `docs/api/narratoApi/tests/integration/test_registration_login.py`

**Interfaces:**
- Consumes: SMTP 配置、Redis、PostgreSQL。
- Produces: 注册验证码、注册、登录、登出、找回密码、`Authorization: Bearer` 校验。

- [ ] **Step 1: 写单点替换测试**

```python
def test_second_login_revokes_first_token(auth_service, user):
    first = auth_service.login(user.email, "correct-password")
    second = auth_service.login(user.email, "correct-password")
    assert auth_service.resolve(first.token) is None
    assert auth_service.resolve(second.token).id == user.id
```

- [ ] **Step 2: 写固定 TTL 测试**

```python
def test_session_ttl_is_thirty_days(redis_client, auth_service, user):
    token = auth_service.login(user.email, "correct-password").token
    ttl = redis_client.ttl(auth_service.session_key(token))
    assert 2_591_990 <= ttl <= 2_592_000
```

- [ ] **Step 3: 运行测试确认失败**

Run: `cd docs/api/narratoApi && python3.12 -m pytest tests/unit/test_email_codes.py tests/unit/test_single_session_token.py -q`

Expected: FAIL。

- [ ] **Step 4: 实现认证链路**

Token 使用 `secrets.token_urlsafe(48)`；Redis 只存 SHA-256 哈希和用户 ID。新登录使用 Lua 或事务原子删除旧 Token 并设置新 Token，验证码 TTL 为 600 秒；所有认证失败返回 HTTP `401`。

- [ ] **Step 5: 验证**

Run:

```bash
cd docs/api/narratoApi
python3.12 -m alembic upgrade head
python3.12 -m pytest tests/unit/test_email_codes.py tests/unit/test_single_session_token.py \
  tests/integration/test_registration_login.py -q
```

Expected: PASS。

- [ ] **Step 6: Commit**

```bash
git add docs/api/narratoApi/narrato_api/auth docs/api/narratoApi/narrato_api/integrations/mail_client.py \
  docs/api/narratoApi/migrations/versions/0002_users.py docs/api/narratoApi/tests
git commit -m "feat: add email auth and single session tokens"
```

### Task 12: 实现积分账本、价格与运维充值 CLI

**Files:**
- Create: `docs/api/narratoApi/narrato_api/billing/models.py`
- Create: `docs/api/narratoApi/narrato_api/billing/schemas.py`
- Create: `docs/api/narratoApi/narrato_api/billing/pricing.py`
- Create: `docs/api/narratoApi/narrato_api/billing/service.py`
- Create: `docs/api/narratoApi/narrato_api/cli.py`
- Modify: `docs/api/narratoApi/narrato_api/auth/service.py`
- Create: `docs/api/narratoApi/migrations/versions/0003_billing.py`
- Create: `docs/api/narratoApi/tests/unit/test_pricing.py`
- Create: `docs/api/narratoApi/tests/unit/test_credit_ledger.py`
- Create: `docs/api/narratoApi/tests/integration/test_charge_and_refund.py`
- Create: `docs/api/narratoApi/tests/integration/test_registration_credit.py`

**Interfaces:**
- Consumes: 用户、总视频秒数、价格版本、幂等业务键。
- Produces: `estimate_short_drama_cost()`、`charge_project()`、`refund_failed_project()`、本地充值 CLI。

- [ ] **Step 1: 写取整和余额下限测试**

```python
@pytest.mark.parametrize(("seconds", "cost"), [(1, 20), (60, 20), (61, 40), (3000, 1000)])
def test_short_drama_pricing(seconds, cost):
    assert estimate_short_drama_cost(seconds, credits_per_minute=20) == cost

def test_charge_never_allows_negative_balance(billing_service, account):
    account.balance = 19
    with pytest.raises(InsufficientCreditsError):
        billing_service.charge_project(account.user_id, "prj_1", 20)
```

- [ ] **Step 2: 写退款幂等测试**

```python
def test_failure_refund_is_applied_once(billing_service, charged_project):
    billing_service.refund_failed_project(charged_project.id)
    billing_service.refund_failed_project(charged_project.id)
    assert billing_service.balance(charged_project.user_id) == charged_project.original_balance
```

同时补充注册赠送测试：同一用户重复消费注册完成事件时，只产生一笔 `signup_bonus` 流水，最终余额为 100。

- [ ] **Step 3: 运行测试确认失败**

Run: `cd docs/api/narratoApi && python3.12 -m pytest tests/unit/test_pricing.py tests/unit/test_credit_ledger.py -q`

Expected: FAIL。

- [ ] **Step 4: 实现整数账本和 CLI**

创建任务扣费使用数据库行锁和不可变 `credit_ledger`；注册赠送流水以用户 ID 为幂等键。CLI 形式固定为：

```bash
python -m narrato_api.cli credits grant --email user@example.com --amount 100 --reason operator_grant
```

- [ ] **Step 5: 验证**

Run: `cd docs/api/narratoApi && python3.12 -m pytest tests/unit/test_pricing.py tests/unit/test_credit_ledger.py tests/integration/test_charge_and_refund.py tests/integration/test_registration_credit.py -q`

Expected: PASS。

- [ ] **Step 6: Commit**

```bash
git add docs/api/narratoApi/narrato_api/billing docs/api/narratoApi/narrato_api/cli.py \
  docs/api/narratoApi/narrato_api/auth/service.py \
  docs/api/narratoApi/migrations/versions/0003_billing.py docs/api/narratoApi/tests
git commit -m "feat: add credit ledger and pricing"
```

---

## Phase 5：项目、上传与持久化工作流

### Task 13: 实现项目、资产和 OSS 表单直传

**Files:**
- Create: `docs/api/narratoApi/narrato_api/projects/models.py`
- Create: `docs/api/narratoApi/narrato_api/projects/schemas.py`
- Create: `docs/api/narratoApi/narrato_api/projects/service.py`
- Create: `docs/api/narratoApi/narrato_api/projects/router.py`
- Create: `docs/api/narratoApi/narrato_api/assets/models.py`
- Create: `docs/api/narratoApi/narrato_api/assets/schemas.py`
- Create: `docs/api/narratoApi/narrato_api/assets/service.py`
- Create: `docs/api/narratoApi/narrato_api/assets/router.py`
- Create: `docs/api/narratoApi/narrato_api/integrations/oss_client.py`
- Create: `docs/api/narratoApi/narrato_api/integrations/core_client.py`
- Create: `docs/api/narratoApi/migrations/versions/0004_projects_assets.py`
- Create: `docs/api/narratoApi/tests/unit/test_oss_post_policy.py`
- Create: `docs/api/narratoApi/tests/unit/test_asset_constraints.py`
- Create: `docs/api/narratoApi/tests/integration/test_upload_complete.py`

**Interfaces:**
- Consumes: 登录用户、文件声明、OSS 配置、Core media-probe。
- Produces: 项目、签名 POST Policy、资产确认、`validating -> ready/invalid`。

- [ ] **Step 1: 写 Policy 约束测试**

```python
def test_video_policy_uses_required_key_and_size_limit(policy_service, user, project):
    policy = policy_service.create_video_policy(user.id, project.id, "episode.mp4")
    assert policy.key.startswith("narrato/api/")
    assert policy.max_size == 314_572_800
    assert policy.key.endswith(".mp4")
```

- [ ] **Step 2: 写上传完成立即校验测试**

```python
def test_upload_complete_dispatches_probe(client, auth, fake_core):
    response = client.post("/api/v1/projects/prj_1/uploads/complete", headers=auth, json=complete_payload())
    assert response.status_code == 202
    assert response.json()["data"]["status"] == "validating"
    assert fake_core.media_probe_calls == 1
```

- [ ] **Step 3: 运行测试确认失败**

Run: `cd docs/api/narratoApi && python3.12 -m pytest tests/unit/test_oss_post_policy.py tests/unit/test_asset_constraints.py tests/integration/test_upload_complete.py -q`

Expected: FAIL。

- [ ] **Step 4: 实现显式状态和约束**

项目最多 5 个视频；视频扩展名、300 MiB 与 SRT 5 MiB 在签名和确认两处校验；10 分钟限制以 Core FFprobe 结果为准。未登录请求不签发 Policy。

- [ ] **Step 5: 验证**

Run: `cd docs/api/narratoApi && python3.12 -m alembic upgrade head && python3.12 -m pytest tests/unit/test_oss_post_policy.py tests/unit/test_asset_constraints.py tests/integration/test_upload_complete.py -q`

Expected: PASS。

- [ ] **Step 6: Commit**

```bash
git add docs/api/narratoApi/narrato_api/projects docs/api/narratoApi/narrato_api/assets \
  docs/api/narratoApi/narrato_api/integrations docs/api/narratoApi/migrations/versions/0004_projects_assets.py \
  docs/api/narratoApi/tests
git commit -m "feat: add projects and oss uploads"
```

### Task 14: 实现版本化 DAG、Outbox、回调与持续轮询

**Files:**
- Create: `docs/api/narratoApi/narrato_api/workflows/models.py`
- Create: `docs/api/narratoApi/narrato_api/workflows/schemas.py`
- Create: `docs/api/narratoApi/narrato_api/workflows/state_machine.py`
- Create: `docs/api/narratoApi/narrato_api/workflows/templates/short_drama_narration_v1.py`
- Create: `docs/api/narratoApi/narrato_api/workflows/service.py`
- Create: `docs/api/narratoApi/narrato_api/workflows/dispatcher.py`
- Create: `docs/api/narratoApi/narrato_api/workflows/reconciler.py`
- Create: `docs/api/narratoApi/narrato_api/workflows/tasks.py`
- Create: `docs/api/narratoApi/narrato_api/workflows/router.py`
- Create: `docs/api/narratoApi/narrato_api/events/sse.py`
- Create: `docs/api/narratoApi/migrations/versions/0005_workflows.py`
- Create: `docs/api/narratoApi/tests/unit/test_workflow_state_machine.py`
- Create: `docs/api/narratoApi/tests/unit/test_short_drama_template_v1.py`
- Create: `docs/api/narratoApi/tests/unit/test_reconciler.py`
- Create: `docs/api/narratoApi/tests/integration/test_callback_poll_race.py`
- Create: `docs/api/narratoApi/tests/integration/test_sse_resume.py`

**Interfaces:**
- Consumes: 已扣费项目、资产/能力快照、Core Client。
- Produces: DAG 快照、Node Attempt、可靠派发、双通道收口、SSE。

- [ ] **Step 1: 写禁止用户取消/重试的契约测试**

```python
def test_openapi_has_no_user_cancel_or_retry(client):
    paths = client.get("/openapi.json").json()["paths"]
    assert all("/cancel" not in path and "/retry" not in path for path in paths)
```

- [ ] **Step 2: 写回调与轮询竞态测试**

```python
def test_callback_and_poll_complete_node_once(reconciler, running_node, terminal_result):
    reconciler.apply_callback(terminal_result)
    reconciler.apply_poll_result(terminal_result)
    assert reconciler.node_completion_count(running_node.id) == 1
    assert reconciler.downstream_dispatch_count(running_node.id) == 1
```

- [ ] **Step 3: 写最终失败退款一次测试**

```python
def test_retry_exhaustion_fails_and_refunds_once(workflow_service, charged_project):
    workflow_service.fail_attempts(charged_project.id, count=3, retryable=True)
    assert workflow_service.project_status(charged_project.id) == "failed"
    assert workflow_service.refund_count(charged_project.id) == 1
```

- [ ] **Step 4: 运行测试确认失败**

Run: `cd docs/api/narratoApi && python3.12 -m pytest tests/unit/test_workflow_state_machine.py tests/unit/test_short_drama_template_v1.py tests/integration/test_callback_poll_race.py -q`

Expected: FAIL。

- [ ] **Step 5: 实现模板与双通道收口**

模板必须明确 `media_probe/asr -> video_analysis -> script_generation -> waiting_for_edit -> tts -> subtitle -> video_render -> publish_artifacts`。回调与轮询进入同一数据库事务，按 `event_id + state_version` 去重；Celery 只负责唤醒，数据库扫描补投。

- [ ] **Step 6: 实现 SSE 断点续传**

`job_events.sequence` 单调递增；`GET /api/v1/jobs/{job_id}/events` 接受 `Last-Event-ID` 并补发，用户消息不得含内部路径和堆栈。

- [ ] **Step 7: 验证**

Run:

```bash
cd docs/api/narratoApi
python3.12 -m alembic upgrade head
python3.12 -m pytest tests/unit/test_workflow_state_machine.py tests/unit/test_short_drama_template_v1.py \
  tests/unit/test_reconciler.py tests/integration/test_callback_poll_race.py tests/integration/test_sse_resume.py -q
```

Expected: PASS。

- [ ] **Step 8: Commit**

```bash
git add docs/api/narratoApi/narrato_api/workflows docs/api/narratoApi/narrato_api/events \
  docs/api/narratoApi/migrations/versions/0005_workflows.py docs/api/narratoApi/tests
git commit -m "feat: add durable short drama workflow"
```

### Task 15: 实现编辑锁定、结果、终态删除和剪映 Manifest

**Files:**
- Create: `docs/api/narratoApi/narrato_api/editor/models.py`
- Create: `docs/api/narratoApi/narrato_api/editor/schemas.py`
- Create: `docs/api/narratoApi/narrato_api/editor/service.py`
- Create: `docs/api/narratoApi/narrato_api/editor/router.py`
- Create: `docs/api/narratoApi/narrato_api/artifacts/models.py`
- Create: `docs/api/narratoApi/narrato_api/artifacts/service.py`
- Create: `docs/api/narratoApi/narrato_api/exports/service.py`
- Create: `docs/api/narratoApi/narrato_api/exports/router.py`
- Create: `docs/api/narratoApi/narrato_api/deletion/tasks.py`
- Create: `docs/api/narratoApi/migrations/versions/0006_editor_artifacts.py`
- Create: `docs/api/narratoApi/tests/unit/test_editor_last_write_wins.py`
- Create: `docs/api/narratoApi/tests/unit/test_editor_lock.py`
- Create: `docs/api/narratoApi/tests/unit/test_artifact_visibility.py`
- Create: `docs/api/narratoApi/tests/unit/test_project_deletion_rules.py`
- Create: `docs/api/narratoApi/tests/unit/test_jianying_manifest.py`

**Interfaces:**
- Consumes: `waiting_for_edit` 项目、当前草稿、已完成 Core 产物。
- Produces: LWW 保存、不可变 revision、一次渲染、结果、终态删除、Jianying Manifest。

- [ ] **Step 1: 写锁定和永久等待测试**

```python
def test_waiting_for_edit_does_not_expire(project_service, waiting_project, freezer):
    freezer.move_to("2036-07-16")
    project_service.run_expiration_scan()
    assert project_service.status(waiting_project.id) == "waiting_for_edit"

def test_submit_render_locks_editor_immediately(editor_service, waiting_project):
    editor_service.submit_render(waiting_project.id)
    with pytest.raises(ProjectLockedError):
        editor_service.save(waiting_project.id, {"tracks": []})
```

- [ ] **Step 2: 写删除和导出守卫测试**

```python
@pytest.mark.parametrize("status", ["draft", "validating", "analyzing", "waiting_for_edit", "rendering"])
def test_non_terminal_project_cannot_be_deleted(project_service, status):
    project = project_fixture(status=status)
    with pytest.raises(ProjectStateConflict):
        project_service.delete(project.id)

def test_failed_project_has_no_exports(export_service, failed_project):
    assert export_service.list_exports(failed_project.id) == []
```

- [ ] **Step 3: 运行测试确认失败**

Run: `cd docs/api/narratoApi && python3.12 -m pytest tests/unit/test_editor_lock.py tests/unit/test_artifact_visibility.py tests/unit/test_project_deletion_rules.py -q`

Expected: FAIL。

- [ ] **Step 4: 实现事务锁定和 Manifest 转发**

提交渲染在同一事务内创建 `editor_revision`、写入锁定状态和 Outbox。Jianying 接口只对 `completed` 开放，调用 Core 生成基础文件并将 CDN 资源映射为 `zip_path`；不得创建 ZIP Artifact。

- [ ] **Step 5: 验证**

Run:

```bash
cd docs/api/narratoApi
python3.12 -m alembic upgrade head
python3.12 -m pytest tests/unit/test_editor_last_write_wins.py tests/unit/test_editor_lock.py \
  tests/unit/test_artifact_visibility.py tests/unit/test_project_deletion_rules.py \
  tests/unit/test_jianying_manifest.py -q
```

Expected: PASS。

- [ ] **Step 6: Commit**

```bash
git add docs/api/narratoApi/narrato_api/editor docs/api/narratoApi/narrato_api/artifacts \
  docs/api/narratoApi/narrato_api/exports docs/api/narratoApi/narrato_api/deletion \
  docs/api/narratoApi/migrations/versions/0006_editor_artifacts.py docs/api/narratoApi/tests
git commit -m "feat: add editor lock and completed exports"
```

---

## Phase 6：React Web 接入

### Task 16: 接入认证、统一 API Client 和 401 处理

**Files:**
- Create: `docs/web/homepage-prototype/src/services/httpClient.js`
- Create: `docs/web/homepage-prototype/src/services/narratoApi.js`
- Create: `docs/web/homepage-prototype/src/features/auth/AuthProvider.jsx`
- Create: `docs/web/homepage-prototype/src/features/auth/authStorage.js`
- Create: `docs/web/homepage-prototype/src/pages/LoginPage.jsx`
- Modify: `docs/web/homepage-prototype/src/App.jsx`
- Modify: `docs/web/homepage-prototype/src/main.jsx`
- Create: `docs/web/homepage-prototype/scripts/verify-api-auth.mjs`

**Interfaces:**
- Consumes: `narratoApi` Token 和统一响应 Envelope。
- Produces: 登录、Token 缓存、Authorization Header、全局 401 清理与回登录。

- [ ] **Step 1: 写 401 验证脚本**

脚本注入返回 `401` 的 Mock Fetch，断言 Token 被清除且路由进入登录页。

- [ ] **Step 2: 运行验证确认失败**

Run: `cd docs/web/homepage-prototype && node scripts/verify-api-auth.mjs`

Expected: FAIL。

- [ ] **Step 3: 实现统一请求入口**

```javascript
export async function apiRequest(path, options = {}) {
  const token = readToken();
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}), ...options.headers },
  });
  if (response.status === 401) {
    clearToken();
    window.dispatchEvent(new CustomEvent("auth:expired"));
  }
  const payload = await response.json();
  if (!response.ok) throw new ApiError(response.status, payload.code, payload.message, payload.data);
  return payload.data;
}
```

- [ ] **Step 4: 验证构建**

Run: `cd docs/web/homepage-prototype && node scripts/verify-api-auth.mjs && npm run build`

Expected: 验证 PASS，Vite build 成功。

- [ ] **Step 5: Commit**

```bash
git add docs/web/homepage-prototype/src docs/web/homepage-prototype/scripts/verify-api-auth.mjs
git commit -m "feat: connect web authentication api"
```

### Task 17: 接入 OSS 上传、项目流程、SSE 和编辑保存

**Files:**
- Create: `docs/web/homepage-prototype/src/features/uploads/ossPostUpload.js`
- Create: `docs/web/homepage-prototype/src/features/jobs/readJobEvents.js`
- Create: `docs/web/homepage-prototype/src/features/projects/projectApi.js`
- Modify: `docs/web/homepage-prototype/src/pages/CreatePage.jsx`
- Modify: `docs/web/homepage-prototype/src/pages/NarrationSettingsPage.jsx`
- Modify: `docs/web/homepage-prototype/src/pages/NarrationAnalysisPage.jsx`
- Modify: `docs/web/homepage-prototype/src/pages/NarrationEditorPage.jsx`
- Modify: `docs/web/homepage-prototype/src/pages/ProjectsPage.jsx`
- Create: `docs/web/homepage-prototype/scripts/verify-api-project-flow.mjs`

**Interfaces:**
- Consumes: 上传 Policy、Asset 状态、费用、项目、SSE 事件、LWW 编辑 API。
- Produces: 真实上传、即时确认校验、分析等待、编辑保存和一次渲染提交。

- [ ] **Step 1: 写项目流程验证脚本**

验证：文件不超过 300 MiB；OSS POST 成功后立即调用 complete；全部资产 ready 前禁用开始；费用来自 API；编辑保存防抖；提交渲染后页面只读。

- [ ] **Step 2: 运行脚本确认失败**

Run: `cd docs/web/homepage-prototype && node scripts/verify-api-project-flow.mjs`

Expected: FAIL。

- [ ] **Step 3: 实现 SSE Fetch Reader**

```javascript
export async function readJobEvents(jobId, lastEventId, onEvent, signal) {
  const response = await fetch(`${API_BASE_URL}/api/v1/jobs/${jobId}/events`, {
    headers: { Authorization: `Bearer ${readToken()}`, ...(lastEventId ? { "Last-Event-ID": lastEventId } : {}) },
    signal,
  });
  if (!response.ok || !response.body) throw new Error(`SSE ${response.status}`);
  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  const parse = createSseParser(onEvent);
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    parse(value);
  }
}

export function createSseParser(onEvent) {
  let buffer = "";
  return (chunk) => {
    buffer += chunk.replaceAll("\r\n", "\n");
    const frames = buffer.split("\n\n");
    buffer = frames.pop() || "";
    for (const frame of frames) {
      const data = frame.split("\n").filter((line) => line.startsWith("data:"))
        .map((line) => line.slice(5).trimStart()).join("\n");
      if (data) onEvent(JSON.parse(data));
    }
  };
}
```

- [ ] **Step 4: 保持编辑器约束**

API 保存只在防抖结束触发；Pointer Move、播放头变化和本地选中不得请求服务端；最终渲染成功/失败或提交后禁止写操作。

- [ ] **Step 5: 验证**

Run:

```bash
cd docs/web/homepage-prototype
node scripts/verify-api-project-flow.mjs
npm run build
```

Expected: PASS。

- [ ] **Step 6: Commit**

```bash
git add docs/web/homepage-prototype/src docs/web/homepage-prototype/scripts/verify-api-project-flow.mjs
git commit -m "feat: connect project workflow api"
```

### Task 18: 接入结果页与前端流式剪映 ZIP

**Files:**
- Create: `docs/web/homepage-prototype/src/features/exports/jianyingZip.js`
- Modify: `docs/web/homepage-prototype/package.json`
- Modify: `docs/web/homepage-prototype/package-lock.json`
- Modify: `docs/web/homepage-prototype/src/pages/ProjectResultPage.jsx`
- Modify: `docs/web/homepage-prototype/src/components/projects/ProjectResultDetails.jsx`
- Create: `docs/web/homepage-prototype/scripts/verify-jianying-export.mjs`

**Interfaces:**
- Consumes: 完成项目 Result、Jianying Manifest、公开 CDN Range/GET。
- Produces: 固定“导出视频”和“导出到剪映草稿”动作；Chrome/Edge 磁盘流式 ZIP。

- [ ] **Step 1: 写导出守卫脚本**

验证失败项目没有下载入口；完成项目有两个固定入口；不创建服务端 ZIP 请求或 ZIP Artifact。

- [ ] **Step 2: 运行脚本确认失败**

Run: `cd docs/web/homepage-prototype && node scripts/verify-jianying-export.mjs`

Expected: FAIL。

- [ ] **Step 3: 实现浏览器能力检查和磁盘流**

```javascript
export async function exportJianyingZip(manifest) {
  if (!("showSaveFilePicker" in window)) throw new Error("仅支持桌面 Chrome/Edge");
  const handle = await window.showSaveFilePicker({ suggestedName: manifest.package_name });
  const writable = await handle.createWritable();
  await writeManifestAsZipStream(manifest, writable);
  await writable.close();
}
```

`writeManifestAsZipStream` 必须逐项拉取 CDN ReadableStream 并写入 ZIP Writer，不构造完整 Blob；失败时关闭 Writable 并展示可重试提示。
实现使用 `@zip.js/zip.js`，依赖必须进入 `package.json` 与锁文件；测试使用小型内联文件和 Mock CDN Stream 验证 ZIP 路径、内容及恒定内存策略。

- [ ] **Step 4: 浏览器和构建验证**

Run:

```bash
cd docs/web/homepage-prototype
node scripts/verify-jianying-export.mjs
npm run build
```

Expected: PASS；再用桌面 Chrome 对小型 Manifest 完成一次真实保存。

- [ ] **Step 5: Commit**

```bash
git add docs/web/homepage-prototype/src/features/exports/jianyingZip.js \
  docs/web/homepage-prototype/package.json docs/web/homepage-prototype/package-lock.json \
  docs/web/homepage-prototype/src/pages/ProjectResultPage.jsx \
  docs/web/homepage-prototype/src/components/projects/ProjectResultDetails.jsx \
  docs/web/homepage-prototype/scripts/verify-jianying-export.mjs
git commit -m "feat: add client-side jianying export"
```

---

## Phase 7：部署、契约与完整验收

### Task 19: 添加 Supervisor、Nginx、配置和运维文档

**Files:**
- Create: `docs/api/narratoApi/supervisor/narrato-api-web.conf`
- Create: `docs/api/narratoApi/supervisor/narrato-api-worker.conf`
- Create: `docs/api/narratoApi/supervisor/narrato-api-scheduler.conf`
- Create: `coreApi/supervisor/narrato-core-web.conf`
- Create: `coreApi/supervisor/narrato-core-worker-analysis.conf`
- Create: `coreApi/supervisor/narrato-core-worker-asr.conf`
- Create: `coreApi/supervisor/narrato-core-worker-tts.conf`
- Create: `coreApi/supervisor/narrato-core-worker-render.conf`
- Create: `docs/api/narratoApi/deploy/nginx.conf`
- Create: `docs/api/narratoApi/scripts/verify-supervisor-config.py`
- Create: `docs/api/narratoApi/README.md`
- Create: `coreApi/README.md`

**Interfaces:**
- Consumes: 两套 `.venv`、TOML、PostgreSQL、Redis、Nginx。
- Produces: 可启动、自动重启、优雅停止、日志轮转的宿主机部署。

- [ ] **Step 1: 写配置检查脚本**

在两个 README 中提供并执行：

```bash
export REPO_ROOT="$(git rev-parse --show-toplevel)"
python3.12 "$REPO_ROOT/docs/api/narratoApi/scripts/verify-supervisor-config.py"
nginx -t -c "$REPO_ROOT/docs/api/narratoApi/deploy/nginx.conf"
```

验证脚本使用 `configparser` 解析所有 Supervisor 文件，断言每个 Program 都具有 `command`、`directory`、`autostart`、`autorestart`、`stopasgroup`、`killasgroup` 和独立日志路径，不启动真实进程、不写入系统目录。

- [ ] **Step 2: 编写 Supervisor 配置**

每个进程配置明确 `directory`、虚拟环境命令、TOML 路径、队列、`stopasgroup=true`、`killasgroup=true`、优雅停止超时、独立日志文件；Core 进程设置根仓库 `PYTHONPATH` 以导入现有 `app`。

- [ ] **Step 3: 编写 Nginx 规则**

包含 API 反代、SSE 禁用缓冲、请求体限制、CORS 来源、超时和基础限流；OSS/CDN CORS 配置示例必须允许 Web Origin 的 `GET/HEAD/Range`。

- [ ] **Step 4: 验证配置和文档命令**

Run:

```bash
nginx -t -c "$PWD/docs/api/narratoApi/deploy/nginx.conf"
python3.12 -m compileall docs/api/narratoApi/narrato_api coreApi/core_api
```

Expected: Nginx 配置有效，Python 全部可编译。

- [ ] **Step 5: Commit**

```bash
git add docs/api/narratoApi/supervisor docs/api/narratoApi/deploy \
  docs/api/narratoApi/scripts/verify-supervisor-config.py docs/api/narratoApi/README.md \
  coreApi/supervisor coreApi/README.md
git commit -m "docs: add process deployment configuration"
```

### Task 20: 执行双服务契约、恢复和端到端验收

**Files:**
- Create: `coreApi/tests/contract/test_narrato_contract.py`
- Create: `coreApi/tests/smoke/test_real_providers.py`
- Create: `docs/api/narratoApi/tests/contract/test_core_contract.py`
- Create: `docs/api/narratoApi/tests/e2e/test_short_drama_full_flow.py`
- Create: `docs/api/narratoApi/tests/e2e/test_failure_recovery.py`
- Create: `docs/api/narratoApi/tests/e2e/test_failure_refund.py`
- Create: `docs/api/narratoApi/tests/e2e/test_callback_loss_poll_recovery.py`

**Interfaces:**
- Consumes: 两个完整服务、Fake Provider、小型测试视频、测试 OSS。
- Produces: 可审计的完整链路、故障恢复和真实供应商 Smoke 证据。

- [ ] **Step 1: 写契约失败测试**

双方固定校验：状态枚举、统一响应、稳定错误码、Capability DTO、Core Task 产物、Callback 事件与 Bearer Token。

- [ ] **Step 2: 写完整流程和故障注入测试**

覆盖：有/无 SRT、最多 5 视频、回调丢失、轮询重复、Worker 崩溃、心跳超时、旧 attempt 晚到、最终失败退款一次、失败不可导出、永久编辑等待、一次渲染锁定。

- [ ] **Step 3: 运行全部数据库迁移**

Run:

```bash
cd coreApi && .venv/bin/alembic upgrade head && .venv/bin/alembic check
cd ../docs/api/narratoApi && .venv/bin/alembic upgrade head && .venv/bin/alembic check
```

Expected: 两套迁移成功且无模型差异。

- [ ] **Step 4: 运行后端完整测试**

Run:

```bash
cd coreApi
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/mypy core_api
.venv/bin/pytest -q tests/unit tests/integration tests/contract tests/e2e

cd ../docs/api/narratoApi
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/mypy narrato_api
.venv/bin/pytest -q tests/unit tests/integration tests/contract tests/e2e
```

Expected: 全部通过。

- [ ] **Step 5: 运行原项目回归和前端验证**

Run:

```bash
cd "$(git rev-parse --show-toplevel)"
PYTHONDONTWRITEBYTECODE=1 /opt/homebrew/bin/python3.11 -m pytest -p no:cacheprovider -q \
  app/services/test_short_drama_narration_validation_unittest.py \
  app/services/llm/test_subtitle_adapter_pipeline_unittest.py \
  app/services/test_multi_video_script_sources_unittest.py \
  app/services/test_script_subtitle_unittest.py \
  app/services/test_merger_video_concat_unittest.py \
  app/services/test_jianying_task_unittest.py

cd docs/web/homepage-prototype
npm run build
node scripts/verify-api-auth.mjs
node scripts/verify-api-project-flow.mjs
node scripts/verify-jianying-export.mjs
```

Expected: 全部通过。

- [ ] **Step 6: 运行可选真实供应商 Smoke Test**

Run: `cd coreApi && RUN_REAL_PROVIDER_TESTS=1 .venv/bin/pytest -q tests/smoke/test_real_providers.py`

Expected: 使用测试配置完成至少一次 ASR、LLM、TTS 和短视频渲染；该命令不进入普通 CI。

- [ ] **Step 7: Commit**

```bash
git add coreApi/tests docs/api/narratoApi/tests docs/web/homepage-prototype/scripts
git commit -m "test: verify narrato api end to end flow"
```

---

## Implementation Gates

1. **Gate A — Core 可独立运行：** Task 2-9 全部通过，Core 原子能力、租约和回调可用，旧 Streamlit 能力回归通过。
2. **Gate B — 业务面可独立运行：** Task 10-15 全部通过，鉴权、上传、积分、DAG、编辑锁定和失败退款通过。
3. **Gate C — Web 闭环：** Task 16-18 完成，真实 UI 不再依赖 Mock 数据，Chrome/Edge 能生成剪映 ZIP。
4. **Gate D — 可部署：** Task 19-20 完成，Supervisor/Nginx 配置有效，Fake E2E 与故障恢复测试全通过。
5. 每个 Gate 完成后执行一次需求复核和独立代码审查；未通过 Gate 不进入下一阶段。

## Final Acceptance Commands

```bash
cd coreApi && .venv/bin/pytest -q && .venv/bin/ruff check . && .venv/bin/mypy core_api
cd ../docs/api/narratoApi && .venv/bin/pytest -q && .venv/bin/ruff check . && .venv/bin/mypy narrato_api
cd ../../../docs/web/homepage-prototype && npm run build
```

验收结果必须同时证明：无用户取消/重试接口；回调丢失仍可由轮询收口；自动重试不重复扣费；最终失败仅退款一次且不可导出；`waiting_for_edit` 永久保持；提交渲染立即锁定；只有终态可删除；剪映 ZIP 未进入数据库或 OSS。
