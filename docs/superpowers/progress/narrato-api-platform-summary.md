# NarratoAI 多用户 API 平台续接摘要

## 当前检查点

- 分支：`codex/narrato-api-platform`
- worktree：`/private/tmp/NarratoAI-narrato-api-platform`
- Gate：**Gate C 已通过（用户接受原生保存选择器证据例外）**；Gate D 待完成 Task 20 剩余验收。

## Task 17A 基线

- 实施提交：`5852e3b feat: add project lifecycle api`。
- RED：生命周期测试实现前观察到 `POST /api/v1/projects` 返回 404。
- GREEN：`test_project_lifecycle_routes.py`、资产模型和定价测试共 10 项 PASS；ruff 与 `git diff --check` PASS。
- 提供认证后的 `POST /projects`、`POST /projects/{id}/cost-estimate`、`POST /projects/{id}/start`；估价采用 ready 资产、真实时长和最新价格，启动在事务中复核并创建 workflow。

## Task 17B 证据

- 实施提交：`7b85c63 feat(web): restore protected create flow`。
- RED：Create 路由/流程验证器在恢复前因 `CreationSummary.jsx` 缺失而失败。
- GREEN：Create 路由/流程验证与既有 API project-flow 验证均通过；Vite build 通过，保留既有 >500 kB chunk advisory。
- 新增受保护 `/create` 路由及工作台入口；补齐可编辑的创建数据和三个 UI 组件。
- “开始创作”只在全部素材 ready 且 API 费用已成功返回后启用，显示的费用无本地估算回退。

## Task 17C–17D 证据

- `697387b feat(web): expose protected project result`：受保护 `/projects/:projectId/result` 读取 completion-gated API；未完成、失败或拒绝时不显示导出入口。3 项直接验证 PASS。
- `91a428b feat(web): wire project editor save flow`：受保护 `/projects/:projectId/editor` 提供轻量内容草稿调用者；内容保存防抖，渲染提交前取消待写入并立即只读。3 项直接验证 PASS。
- Task 17 全量直接验证：API 项目流 6 项、Create 路由 1 项、结果路由 3 项、编辑器路由 3 项均 PASS；Vite production build PASS。

## 剩余 Gate C 风险

- 真实上传的 probe duration 尚未回填到新字段，估价会安全返回 `PROJECT_DURATION_UNAVAILABLE`。
- 2026-07-20 完成隔离 SQLite + Redis 的真实 FastAPI/认证浏览器验收：完成态结果真实调用 manifest API，Chrome 用户点击到原生 FSA 调用路径，流式 ZIP 写入 5 次并关闭。仅未可见地完成原生 macOS 保存选择器和用户目的地选择。
- 原生 macOS 保存选择器未向自动化暴露；用户已明确接受现有真实 API/浏览器/FSA/流式 ZIP 证据作为 Gate C 通过依据，保留为上线后人工复核项。
- Vite 保留 >500 kB chunk advisory。

## Task 19A 证据

- 实施提交：`e776d9e docs: add business api supervisor configuration`。
- RED：Supervisor 静态验证器在配置不存在时以 exit 1 失败。
- GREEN：`verify-supervisor-config.py` 验证 web、worker、scheduler 三个 Business API Program 的 venv、TOML、自动启停、进程组停止、超时和独立日志；`py_compile`、ruff、diff check 均通过。

## Task 19B–19D 证据

- `462ab86`：Core web 与四类 role-named worker 的 Supervisor 配置；由于现有 durable task 仅路由至 `narrato.core.default`，所有 worker 如实消费该队列。
- `3a6bc20`：Business/Core 反代、SSE、CORS、限流、超时、OSS/CDN Range CORS 示例和静态 Nginx verifier。
- `2a27f9c`：两套部署运行手册和 README 静态 verifier。
- 全 Task 19 静态验证、ruff、py_compile/compileall 和 diff check PASS；`nginx -t` 在 macOS sandbox 因 sysctl/日志权限无法运行，已在运行手册记录。

## Task 20A 证据

- 实施提交：`02a5620 test: add shared api contract coverage`。
- RED：两个新增契约测试路径不存在，pytest exit 4。
- GREEN：Core 4 项、Business 2 项契约测试均通过；覆盖 response envelope 四字段、未知字段拒绝和稳定 public error code。

## Task 20B 证据

- 实施提交：`1aa2134 feat: add core callback contract endpoint`。
- RED：新增 Business callback 契约先失败，因 `/api/v1/internal/core/callbacks` 不存在而返回 404，未满足要求的专用 Bearer 401。
- GREEN：Core callback delivery 6 项、Business callback contract + reconciler 5 项通过；targeted ruff 与 diff check 通过。
- Business 内部路由要求独立 `core_callback_token`，禁止复用 request token；`X-Idempotency-Key` 必须等于正文 `event_id`，不匹配稳定返回 `CALLBACK_EVENT_ID_MISMATCH`（409），成功仅确认事件 ID 和接收状态。

## 下一原子任务

**Task 20E**：修复 Core 开发环境后运行剩余静态与测试验收；不运行真实 Provider smoke。

Task 20C：`0381536 test: add workflow end to end acceptance`。fresh SQLite 双服务迁移通过；Business E2E 4 项通过，覆盖终态、轮询补偿、失败状态和一次退款。原项目回归 52 项、前端 build/API 验证通过。

预存未提交内容仅 `.superpowers/`、`docs/web/docs/Oss.php` 与 `docs/web/homepage-prototype/.playwright-cli/`，不得触碰。
