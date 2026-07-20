# NarratoAI 多用户 API 平台续接摘要

## 当前检查点

- 分支：`codex/narrato-api-platform`
- worktree：`/private/tmp/NarratoAI-narrato-api-platform`
- Gate：**Gate C 已重新验收但仍阻塞**；Task 17 恢复完成。

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
- 2026-07-20 重新验收：18 项直接验证和 build 均通过，Playwright 确认三个受保护路由均会跳转登录；但无本地认证 API/项目 fixture，无法验证真实 Create → Result → Chrome/Edge 用户手势 File System Access 导出。
- Vite 保留 >500 kB chunk advisory。

## 下一原子任务

**Gate C 认证浏览器验收**：在可运行的认证 API 与 ready/completed fixture 下，验证完整 Create → Result → Chrome/Edge 用户手势剪映导出；Gate 通过前不得开始 Task 19。

预存未提交内容仅 `.superpowers/` 与 `docs/web/docs/Oss.php`，不得触碰。
