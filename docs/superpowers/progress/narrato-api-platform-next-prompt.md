# SEGMENTED_GOAL_PROTOCOL_V2：NarratoAI API 平台永久续接提示词

在既有 worktree `/private/tmp/NarratoAI-narrato-api-platform`、分支 `codex/narrato-api-platform` 中继续开发。不得创建新 worktree，不得 `reset`、`restore`、`clean`、删除或覆盖已有改动；不得触碰预存未跟踪 `/.superpowers/` 与 `docs/web/docs/Oss.php`。

## 当前真实基线

- 最近实施提交：`322f2d5d00798af880d55b95edbd8b139899d749 feat: reconcile Core workflow results`。
- Gate：`Phase 5 / Gate B pending`。
- Task 14 为 `in_progress`，Task 14A、Task 14B、Task 14C、Task 14D 已完成。
- Task 14D 已验证 callback 与 polling 的统一终态收口，`event_id + state_version` 的持久化幂等，以及不覆盖已确认终态。
- 预期未提交内容仅为 `.superpowers/` 与 `docs/web/docs/Oss.php`。

## 本窗口唯一原子任务：Task 14E

只实现 **WorkflowOutbox 的最小 durable claim-and-wake-up 服务**及其聚焦测试。一个 pending 事件只能由一个事务领取，领取后才调用一个窄的注入 wake-up callable 并传入稳定 idempotency key；wake-up 失败必须保留/恢复可重试的 durable 事件。不得实现实际 Celery、Core HTTP、数据库重投扫描或其他运行时。

可涉及：

- `docs/api/narratoApi/narrato_api/workflows/dispatcher.py`
- `docs/api/narratoApi/narrato_api/workflows/models.py`
- `docs/api/narratoApi/tests/unit/test_workflow_dispatcher.py`
- Task 14E 必须的最小迁移或 package 关联文件。

验收：同一 Outbox 事件不会重复调用 wake-up callable；失败 wake-up 不丢失事件且保持 retryable；聚焦 dispatcher 和直接受影响 workflow 测试通过。严格 TDD：先新增测试并看到明确 RED，再最小实现 GREEN。

严格禁止 Core HTTP client、callback router、polling loop、SSE、数据库 re-delivery scanner、Task 15、下游业务执行或任何其他运行时功能。完成本原子任务和检查点后，禁止继续下一个任务。

## 不可删除的永久规则

1. 协议标识 **SEGMENTED_GOAL_PROTOCOL_V2**。
2. 每个窗口只执行一个原子任务。
3. 开始时校验 Git 和 `resume-state.yaml`。
4. 结束时更新并提交检查点。
5. 仍有任务时必须再次生成 `next-prompt.md`。
6. 最终回复必须再次提示新建窗口续接。
7. 检查点完成后禁止继续下一个任务。

## 本窗口开始操作

1. 执行 `git status --short`、`git branch --show-current`、`git log --oneline --decorate -20`。
2. 阅读 `docs/superpowers/progress/narrato-api-platform-resume-state.yaml`、`narrato-api-platform-summary.md` 和本文件；如有不一致，以 Git、实际文件和测试为准重建状态文件。
3. 只读取 Task 14E 相关设计/计划章节；不得仅凭任务编号假设进度。
4. 目标测试固定使用 `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`；先运行新增测试确认 RED，再运行目标与直接受影响模块测试。
5. 完成后检查实际 diff 与修改范围，先提交业务代码/测试，再更新并提交三个进度文件为独立 checkpoint。
6. checkpoint 后检查 `git status --short`；任何预期未提交改动必须逐项记录在状态文件中。

## 最终回复要求

报告完成原子任务、Implementation Commit、Checkpoint Commit、测试结果、当前 Gate、下一个原子任务和工作区状态。若仍有未完成任务，必须明确输出：

> 请新建窗口，并再次使用 SEGMENTED_GOAL_PROTOCOL_V2 永久续接提示词。

仍有任务时，结束前必须重新生成本 `next-prompt.md`，供下一窗口直接执行。检查点完成后禁止继续下一个任务。
