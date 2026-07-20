# NarratoAI 多用户 API 平台续接摘要

## 当前检查点

- 分支：`codex/narrato-api-platform`
- worktree：`/private/tmp/NarratoAI-narrato-api-platform`
- Gate：**Gate C 仍阻塞**；Task 17B 已恢复受保护的 Create 流程。

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

## 剩余 Gate C 风险

- 真实上传的 probe duration 尚未回填到新字段，估价会安全返回 `PROJECT_DURATION_UNAVAILABLE`。
- `ProjectResultPage` 仍未路由，因此完成结果尚不可从真实 UI 到达。
- 编辑器 UI 与真实 Chrome/Edge 保存证据仍缺失；Vite 保留大 chunk advisory。

## 下一原子任务

**Task 17C**：只恢复加载完成项目结果的受保护结果路由，并复用既有导出控件；不处理 Create、编辑器、时长回填或 Task 19。

预存未提交内容仅 `.superpowers/` 与 `docs/web/docs/Oss.php`，不得触碰。
