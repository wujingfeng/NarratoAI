# SEGMENTED_GOAL_PROTOCOL_V2：NarratoAI API 平台永久续接提示词

在既有 worktree `/private/tmp/NarratoAI-narrato-api-platform`、分支 `codex/narrato-api-platform` 中继续。不得创建新 worktree，不得 `reset`、`restore`、`clean`、删除或覆盖已有改动；不得触碰预存未跟踪 `/.superpowers/` 与 `docs/web/docs/Oss.php`。

## 当前真实基线

- 最近 Implementation Commit：`4ca8568 feat: add editor draft last-write-wins`。
- Task 14A--14E、Gate review、Task 15A 和 Task 15B 已完成。
- Task 15B 使用每项目唯一 `EditorDraft` 实现 LWW：有序保存的最后接受内容覆盖当前草稿；`submit_render` 从该草稿创建不可变 revision 再锁定。
- 验证：RED 是缺失 `EditorDraft` import；GREEN `3 passed`，直接受影响 `9 passed, 3 warnings`；Ruff、Alembic upgrade/check、`git diff --check` 均通过。
- 项目仍为 `Phase 5 / Gate B pending`；SQLite/PostgreSQL 并发、真实 OSS/Core 和 6 个既有 assets mypy 错误仍未关闭。
- 预期未提交内容仅为 `.superpowers/` 与 `docs/web/docs/Oss.php`。

## 本窗口唯一原子任务：Task 15C

只选择一个独立的 Task 15 边界，优先实现 **终态项目删除守卫**。严格 TDD：先写测试并观察预期 RED，再以最小代码使其 GREEN。验收必须证明仅 `completed`/`failed` 项目可通过删除资格检查，草稿、上传、校验、排队、分析、等待编辑和渲染中的项目稳定拒绝。不要实现实际删除、结果/产物、导出/Jianying、router、Core 调用、下游行为或第二个 Task 15 子任务。完成 checkpoint 后立即停止。

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
3. 只读取 Task 15C 所需计划/设计章节、项目状态代码和测试；不得无目的读取完整大文档或成功日志。
4. 完成当前子任务后运行目标测试、检查 diff、提交业务代码和测试；随后更新并提交三个永久进度文件为独立 checkpoint。
5. checkpoint 后检查 `git status --short`；任何预期未提交改动必须逐项记录在状态文件中。

## 最终回复要求

报告完成的 Task 15C 子任务、Implementation Commit、Checkpoint Commit、测试结果、当前 Gate、下一个原子任务和工作区状态。若仍有未完成任务，必须明确输出：

> 请新建窗口，并再次使用 SEGMENTED_GOAL_PROTOCOL_V2 永久续接提示词。

仍有任务时，结束前必须重新生成本 `next-prompt.md`，供下一窗口直接执行。检查点完成后禁止继续下一个任务。
