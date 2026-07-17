# SEGMENTED_GOAL_PROTOCOL_V2：NarratoAI API 平台永久续接提示词

在既有 worktree `/private/tmp/NarratoAI-narrato-api-platform`、分支 `codex/narrato-api-platform` 中继续。不得创建新 worktree，不得 `reset`、`restore`、`clean`、删除或覆盖已有改动；不得触碰预存未跟踪 `/.superpowers/` 与 `docs/web/docs/Oss.php`。

## 当前真实基线

- 最近实施提交：`b6da053 feat: dispatch workflow outbox events`。
- Gate：`Phase 5 / Gate B pending`。
- Task 14 的 Task 14A、14B、14C、14D、14E 已完成。
- Task 14E 已验证：pending Outbox 事件被条件更新原子 claim；仅对窄注入 wake-up callable 传稳定 event ID 与 idempotency key；重复/已 claim 不重复 wake；wake 失败恢复 durable retryable pending 状态。
- Task 14E 聚焦与直接受影响测试结果：`9 passed, 2 warnings`；Ruff 和 `git diff --check` 已通过。
- 预期未提交内容仅为 `.superpowers/` 与 `docs/web/docs/Oss.php`。

## 本窗口唯一原子任务：Gate B

仅执行 **Gate B** 的集中需求复核、独立代码审查和全量测试验证。以 Task 14 相关设计、计划、提交和实际代码为依据，记录可审查证据；若发现普通缺陷，可在本 Gate 内最小修复并验证。禁止提前开始后续功能、Task 15、Core HTTP、router、polling、SSE、数据库 re-delivery scanner 或任何新运行时行为。

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
3. 只读取 Gate B 所需的 Task 14 设计/计划章节和相关提交、测试证据；不得无目的读取完整大文档或成功日志。
4. 集中运行 Gate 所需的需求复核、独立审查和全量测试；不得把聚焦测试通过伪报为全量测试通过。
5. 完成后检查实际 diff 与修改范围，提交必要修复后，再更新并提交三个进度文件为独立 checkpoint。
6. checkpoint 后检查 `git status --short`；任何预期未提交改动必须逐项记录在状态文件中。

## 最终回复要求

报告 Gate B 结果、相关提交、测试结果、当前 Gate、下一个原子任务和工作区状态。若仍有未完成任务，必须明确输出：

> 请新建窗口，并再次使用 SEGMENTED_GOAL_PROTOCOL_V2 永久续接提示词。

仍有任务时，结束前必须重新生成本 `next-prompt.md`，供下一窗口直接执行。检查点完成后禁止继续下一个任务。
