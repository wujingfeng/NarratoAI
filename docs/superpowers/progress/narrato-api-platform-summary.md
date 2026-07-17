# NarratoAI 多用户 API 平台续接摘要

## 当前检查点

- 分支：`codex/narrato-api-platform`
- worktree：`/private/tmp/NarratoAI-narrato-api-platform`
- Gate：**Phase 5 / Gate B pending**
- Task 14 的 Task 14A 至 Task 14E 已完成。
- 最新实施提交：`b6da053 feat: dispatch workflow outbox events`。

## Task 14 已完成部分

1. **14A**：版本化短剧解说 DAG 与纯状态机；用户取消/手动重试被拒绝，`waiting_for_edit` 不自动超时。
2. **14B**：模板快照、工作流、节点、节点尝试和 Outbox 的持久化模型及 `0006_workflows` 迁移。
3. **14C**：`WorkflowService` 在一个事务内从不可变快照创建工作流与节点，并对状态转换写入唯一幂等 Outbox 事件。
4. **14D**：`WorkflowReconciler` 统一 callback/polling 的终态收口；按 event ID 与 state version 持久化去重，不覆盖已确认终态。
5. **14E**：`WorkflowOutboxDispatcher` 以条件更新原子领取 due pending Outbox 事件，并仅向注入的 wake-up callable 传入 stable event ID 和 idempotency key；成功标记 `sent`，wake-up 异常将事件恢复为 durable `pending`，保留递增的 attempt count。

## 新鲜验证证据

- Task 14E TDD RED：实现前 dispatcher 聚焦测试因 `narrato_api.workflows.dispatcher` 缺失产生预期 `ModuleNotFoundError`。
- 聚焦与直接受影响 workflow 测试：`9 passed, 2 warnings`。
- Ruff 与 `git diff --check` 通过。
- 测试固定使用 `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`，因为默认 pytest 插件加载在本机不稳定。

## 范围与风险

- Task 14E 未实现 Core HTTP、router、polling、SSE、数据库重投扫描、Task 15 或下游业务执行。
- 真实 OSS/Core 集成与 PostgreSQL 多连接行为尚未验证。
- 预存未跟踪 `/.superpowers/`、`docs/web/docs/Oss.php` 未修改、未暂存、未提交。

## 下一原子任务

执行 **Gate B**：集中进行需求复核、独立代码审查和全量测试验证；这不是继续开发任务。完成 Gate 检查点后立即结束，不得开始后续功能开发。
