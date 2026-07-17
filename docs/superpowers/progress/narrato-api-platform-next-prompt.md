# SEGMENTED_GOAL_PROTOCOL_V2：NarratoAI API 平台永久续接提示词

在既有 worktree `/private/tmp/NarratoAI-narrato-api-platform`、分支 `codex/narrato-api-platform` 中继续。不得创建新 worktree，不得 `reset`、`restore`、`clean`、删除或覆盖已有改动；不得触碰预存未跟踪 `/.superpowers/` 与 `docs/web/docs/Oss.php`。

## 当前真实基线

- 最近 Implementation Commit：`b146120 feat: guard completed project export eligibility`。
- Task 14A--14E、Gate review、Task 15A、15B、15C、15D、15E 已完成。
- Task 15E 只有导出资格服务守卫：`completed` 通过；`failed` 和任何其他状态抛出 `PROJECT_NOT_COMPLETED`；不创建产物实体或导出能力。
- 验证：RED 为 `ensure_project_exportable` 缺失（13 个预期失败）；最终直接复验 `28 passed in 0.03s`；Ruff、`git diff --check` 通过。
- 项目仍为 `Phase 5 / Gate B pending`；SQLite/PostgreSQL 并发、真实 OSS/Core 和 6 个既有 assets mypy 错误仍未关闭。
- 预期未提交内容仅为 `.superpowers/` 与 `docs/web/docs/Oss.php`。

## 本窗口唯一原子任务：Task 15F

只实现 **persistent registered-artifact data model and migration**。严格 TDD：先写测试并观察预期 RED，再以最小代码使其 GREEN。验收必须证明可持久化登记项目归属的 exportable artifact 所需字段，并与现有 metadata/migration 链兼容；不得实现结果路由、可见性查询、导出/Jianying 生成、router、Core 调用、下游行为或第二个 Task 15 子任务。完成 checkpoint 后立即停止。

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
3. 只读取 Task 15F 所需计划/设计章节和相关测试；不得无目的读取完整大文档或成功日志。
4. 完成当前子任务后运行目标测试、检查 diff、提交业务代码和测试；随后更新并提交三个永久进度文件为独立 checkpoint。
5. checkpoint 后检查 `git status --short`；任何预期未提交改动必须逐项记录在状态文件中。

## 最终回复要求

报告完成的 Task 15F 子任务、Implementation Commit、Checkpoint Commit、测试结果、当前 Gate、下一个原子任务和工作区状态。若仍有未完成任务，必须明确输出：

> 请新建窗口，并再次使用 SEGMENTED_GOAL_PROTOCOL_V2 永久续接提示词。

仍有任务时，结束前必须重新生成本 `next-prompt.md`，供下一窗口直接执行。检查点完成后禁止继续下一个任务。
