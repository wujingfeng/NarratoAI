# NarratoAI 多用户 API 平台续接摘要

## 当前检查点

- 分支：`codex/narrato-api-platform`
- worktree：`/private/tmp/NarratoAI-narrato-api-platform`
- Gate：**Phase 5 / Gate B pending**
- Task 14 为 `in_progress`；Task 14A、14B、14C、14D 已完成。
- 最新实施提交：`322f2d5 feat: reconcile Core workflow results`。

## Task 14 已完成部分

### Task 14A

1. 版本化短剧解说 DAG 模板：`media_probe -> asr -> video_analysis -> script_generation -> waiting_for_edit -> tts -> subtitle -> video_render -> publish_artifacts`。
2. 纯状态机：拒绝用户取消/手动重试，终态不可恢复，`waiting_for_edit` 不自动超时。

### Task 14B

1. 新增模板快照、工作流实例、工作流节点、节点尝试和 Outbox 持久化模型及迁移 `0006_workflows`。
2. `0006_workflows` 正确衔接既有 `0005_asset_probe_reservations`，未覆盖历史迁移。

### Task 14C

1. 新增纯事务 `WorkflowService`：从不可变 `WorkflowTemplateSnapshot` 创建一个 `Workflow` 和完整 `WorkflowNode` 集合。
2. 允许的工作流状态转换会增加 `state_version`，并在同一事务写入唯一幂等键的 `workflow.state_changed` Outbox 事件。
3. 未引入 callback、polling、Celery、dispatcher、router、SSE 或 Task 15 行为。

### Task 14D

1. 新增 `WorkflowReconciler`，让 Core callback 与 polling 通过同一个事务型收口入口处理终态。
2. 节点尝试新增 `state_version`，并以持久化的 `workflow_reconciliation_events` 对 `(attempt, event_id)` 与 `(attempt, state_version)` 去重。
3. 重复、等版本或过期终态不覆盖已确认的节点/工作流；本任务不投递下游任务、退款或启动运行时派发。

## 新鲜验证证据

```bash
cd docs/api/narratoApi
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest \
  tests/unit/test_reconciler.py \
  tests/unit/test_workflow_models.py \
  tests/unit/test_workflows_migration.py \
  tests/unit/test_workflow_service.py \
  tests/unit/test_workflow_models.py \
  tests/unit/test_workflow_state_machine.py \
  tests/unit/test_short_drama_template_v1.py -q
```

结果：`14 passed, 2 warnings in 0.62s`；Ruff 与 `git diff --check` 均通过。

- Task 14D TDD RED 证据：新增 reconciler 测试在实现前因缺失 `narrato_api.workflows.reconciler` 报 `ModuleNotFoundError`。
- 本环境默认 pytest 插件加载不稳定，聚焦测试固定使用 `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`。

## 范围与风险

- 下一原子任务 Task 14E：为已有 `WorkflowOutbox` 增加最小的 durable claim-and-wake-up 服务。
- Celery runtime、数据库重投扫描、router、SSE、Task 15 仍未实现。
- 真实 OSS/Core 集成与 PostgreSQL 多连接行为尚未验证。
- 预存未跟踪 `/.superpowers/`、`docs/web/docs/Oss.php` 未修改、未暂存、未提交。

## 下一原子任务

仅执行 **Task 14E**：实现 `WorkflowOutbox` 最小 durable claim-and-wake-up 服务及聚焦测试。禁止 Core HTTP、callback router、polling loop、SSE、数据库重投扫描、Task 15；完成检查点后立即结束。
