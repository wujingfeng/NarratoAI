# NarratoAI 多用户 API 平台续接摘要

## 当前检查点

- 分支：`codex/narrato-api-platform`
- worktree：`/private/tmp/NarratoAI-narrato-api-platform`
- Gate：**Gate C 仍阻塞**；Task 17A 已恢复缺失项目 HTTP 生命周期。

## Task 17A 证据

- 实施提交：`5852e3b feat: add project lifecycle api`。
- RED：生命周期测试实现前观察到 `POST /api/v1/projects` 返回 404。
- GREEN：`test_project_lifecycle_routes.py`、资产模型和定价测试共 10 项 PASS；ruff 与 `git diff --check` PASS。
- 提供认证后的 `POST /projects`、`POST /projects/{id}/cost-estimate`、`POST /projects/{id}/start`；估价采用 ready 资产、真实时长和最新价格，启动在事务中复核并创建 workflow。

## 剩余 Gate C 风险

- 真实上传的 probe duration 尚未回填到新字段，估价会安全返回 `PROJECT_DURATION_UNAVAILABLE`。
- `CreatePage`、`ProjectResultPage` 尚未路由；CreatePage 还缺少四个本地依赖。
- 编辑器 UI 与真实 Chrome/Edge 保存证据仍缺失；Vite 保留大 chunk advisory。

## 下一原子任务

**Task 17B**：只恢复 CreatePage 缺失依赖和受保护 `/create` 路由，令真实渲染的开始控件使用 API 费用并在资产未 ready 时禁用；不处理 Result/编辑器/时长回填/Task 19。

预存未提交内容仅 `.superpowers/` 与 `docs/web/docs/Oss.php`，不得触碰。
