# SEGMENTED_GOAL_PROTOCOL_V2：NarratoAI API 平台永久续接提示词

在既有 worktree `/private/tmp/NarratoAI-narrato-api-platform`、分支 `codex/narrato-api-platform` 中继续开发。不得创建新 worktree，不得 `reset`、`restore`、`clean`、删除或覆盖已有改动；不得触碰预存未跟踪 `/.superpowers/` 与 `docs/web/docs/Oss.php`。

## 当前真实基线

- HEAD 检查点：`chore(progress): checkpoint after Task 14A`；其父实施提交为 `6ea93bf feat: add workflow state machine template`。
- Task 13 已完成：Task 13A `14952da`；Task 13B `fc6fe20`，修正 `9bde894`、`7a1d06e`。
- Gate：`Phase 5 / Gate B pending`。
- Task 14 为 `in_progress`，已完成 Task 14A。
- 预期未提交内容仅为 `.superpowers/` 与 `docs/web/docs/Oss.php`。

## 本窗口唯一原子任务：Task 14B

只实现工作流持久化模型与 `0005_workflows` Alembic 迁移：版本化 DAG/模板快照、workflow instance、workflow node、node attempt、Outbox 等数据库数据结构，以及直接模型和迁移测试。

可涉及：

- `docs/api/narratoApi/narrato_api/workflows/models.py`
- `docs/api/narratoApi/migrations/versions/0005_workflows.py`
- `docs/api/narratoApi/tests/unit/test_workflow_models.py`
- `docs/api/narratoApi/tests/unit/test_workflows_migration.py`
- 必要的最小 package/database 关联文件。

验收：模型能持久化上述实体并提供适当的归属、状态、依赖、唯一性和查询约束；迁移可从 Task 13B 迁移头升级；新增与直接受影响的模型/迁移测试通过。严格 TDD：先测试并看到明确 RED，再最小实现 GREEN。

禁止实现 Core 回调、持续轮询、Celery 派发、router、SSE、Task 15 或任何工作流运行时行为。完成本原子任务和检查点后，禁止继续下一个任务。

## 不可删除的永久规则

1. 协议标识必须为 **SEGMENTED_GOAL_PROTOCOL_V2**。
2. 每个窗口只执行一个原子任务。
3. 开始时必须校验 Git 和 `resume-state.yaml`。
4. 结束时必须更新并提交检查点。
5. 仍有任务时必须再次生成 `next-prompt.md`。
6. 最终回复必须再次提示新建窗口续接。
7. 检查点完成后禁止继续下一个任务。

## 本窗口开始操作

1. 执行 `git status --short`、`git branch --show-current`、`git log --oneline --decorate -20`。
2. 阅读 `docs/superpowers/progress/narrato-api-platform-resume-state.yaml`、`narrato-api-platform-summary.md` 和本文件；如有不一致，以 Git、实际文件和测试为准并重建状态文件。
3. 只读取 Task 14B 相关设计/计划章节；不得仅凭任务编号假设进度。
4. 完成后运行目标测试，检查实际 diff 与修改范围，先提交业务代码/测试，再更新并提交三个进度文件为独立 checkpoint。
5. checkpoint 后检查 `git status --short`；任何预期未提交改动必须逐项记录在状态文件中。

## 最终回复要求

报告完成原子任务、Implementation Commit、Checkpoint Commit、测试结果、当前 Gate、下一个原子任务和工作区状态。若仍有未完成任务，必须明确输出：

> 请新建窗口，并再次使用 SEGMENTED_GOAL_PROTOCOL_V2 永久续接提示词。

仍有任务时，结束前必须重新生成本 `next-prompt.md`，供下一窗口直接执行。
