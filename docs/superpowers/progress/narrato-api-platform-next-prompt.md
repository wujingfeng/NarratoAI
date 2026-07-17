# SEGMENTED_GOAL_PROTOCOL_V2：NarratoAI API 平台永久续接提示词

在既有 worktree `/private/tmp/NarratoAI-narrato-api-platform`、分支 `codex/narrato-api-platform` 中继续开发。不得创建新 worktree，不得 `reset`、`restore`、`clean`、删除或覆盖已有改动；不得触碰预存未跟踪 `/.superpowers/` 与 `docs/web/docs/Oss.php`。

## 当前真实基线

- 最近实施提交：`60de8c8 feat: add workflow persistence models`。
- Gate：`Phase 5 / Gate B pending`。
- Task 14 为 `in_progress`，Task 14A 和 Task 14B 已完成。
- Task 14B 的实际迁移是 `0006_workflows`，它衔接已存在的 `0005_asset_probe_reservations`，不得新建或覆盖 `0005_workflows`。
- 预期未提交内容仅为 `.superpowers/` 与 `docs/web/docs/Oss.php`。

## 本窗口唯一原子任务：Task 14C

只实现工作流服务层的纯数据库事务：从版本化模板快照实例化持久化 workflow/node 记录；执行允许的持久化状态转换；并在同一事务中写入幂等 Outbox 记录，以及直接受影响的聚焦测试。

可涉及：

- `docs/api/narratoApi/narrato_api/workflows/service.py`
- `docs/api/narratoApi/narrato_api/workflows/models.py`
- `docs/api/narratoApi/tests/unit/test_workflow_service.py`
- 必要的最小 package/database 关联文件。

验收：模板可在单一数据库事务内生成 workflow/node；允许转换可持久化并同步写入具幂等键的 Outbox；聚焦测试通过。严格 TDD：先测试并看到明确 RED，再最小实现 GREEN。

禁止实现 Core 回调、持续轮询、Celery、dispatcher、router、SSE、Task 15 或任何其他工作流运行时行为。完成本原子任务和检查点后，禁止继续下一个任务。

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
3. 只读取 Task 14C 相关设计/计划章节；不得仅凭任务编号假设进度。
4. 目标测试：`cd docs/api/narratoApi && PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest tests/unit/test_workflow_service.py -q`，再运行直接受影响模块测试。
5. 完成后检查实际 diff 与修改范围，先提交业务代码/测试，再更新并提交三个进度文件为独立 checkpoint。
6. checkpoint 后检查 `git status --short`；任何预期未提交改动必须逐项记录在状态文件中。

## 最终回复要求

报告完成原子任务、Implementation Commit、Checkpoint Commit、测试结果、当前 Gate、下一个原子任务和工作区状态。若仍有未完成任务，必须明确输出：

> 请新建窗口，并再次使用 SEGMENTED_GOAL_PROTOCOL_V2 永久续接提示词。

仍有任务时，结束前必须重新生成本 `next-prompt.md`，供下一窗口直接执行。检查点完成后禁止继续下一个任务。
