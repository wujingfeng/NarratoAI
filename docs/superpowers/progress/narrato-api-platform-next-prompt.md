# SEGMENTED_GOAL_PROTOCOL_V2：NarratoAI API 平台永久续接提示词

在既有 worktree `/private/tmp/NarratoAI-narrato-api-platform`、分支 `codex/narrato-api-platform` 中继续。不得创建新 worktree，不得 `reset`、`restore`、`clean`、删除或覆盖已有改动；不得触碰预存未跟踪 `/.superpowers/` 与 `docs/web/docs/Oss.php`。

## 当前真实基线

- 最近 Gate 修复/Implementation Commit：`ddd012d fix: preserve app logs during migrations`。
- Task 14A--14E 已完成，Task 14 Gate review 通过；Alembic logger disabling 缺陷已用 RED/GREEN 回归测试修复。
- 项目仍为 `Phase 5 / Gate B pending`，因为 Task 15 未完成。
- Gate 证据：直接验证 `25 passed, 4 warnings`；全量 pytest `135 passed, 7 skipped, 7 warnings`；Ruff、Alembic upgrade/check、`git diff --check` 通过。
- 已知风险：`mypy narrato_api` 有 6 个既有 assets 模块错误，未在 Task 14 范围内修复；真实 OSS/Core 与 PostgreSQL 多连接未验证。
- 预期未提交内容：`.superpowers/`、`docs/web/docs/Oss.php`，以及本窗口尚待提交的三个永久进度文件。

## 本窗口唯一原子任务：Task 15A

只启动 **Task 15A** 的一个可独立验证子任务：优先建立 `waiting_for_edit` 永久等待和提交渲染立即锁定编辑器的测试/最小实现边界。严格 TDD：先写测试并观察预期 RED，再写最小实现并运行新增及直接受影响测试。不得提前实现结果、终态删除、剪映 Manifest、Task 15 的其他子任务或任何后续 Task。完成本子任务 checkpoint 后立即停止。

验收标准：所选边界有真实自动化测试；`waiting_for_edit` 不自动过期，且如实现提交渲染边界则立即拒绝后续编辑保存；只修改必要文件；目标测试通过、实际 diff 已检查、业务代码和测试先提交，再更新并提交三个永久进度文件。

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
3. 只读取 Task 15A 所需计划/设计章节、相关提交和测试；不得无目的读取完整大文档或成功日志。
4. 完成当前子任务后运行目标测试、检查 diff、提交业务代码和测试；随后更新并提交三个永久进度文件为独立 checkpoint。
5. checkpoint 后检查 `git status --short`；任何预期未提交改动必须逐项记录在状态文件中。

## 最终回复要求

报告完成的 Task 15A 子任务、Implementation Commit、Checkpoint Commit、测试结果、当前 Gate、下一个原子任务和工作区状态。若仍有未完成任务，必须明确输出：

> 请新建窗口，并再次使用 SEGMENTED_GOAL_PROTOCOL_V2 永久续接提示词。

仍有任务时，结束前必须重新生成本 `next-prompt.md`，供下一窗口直接执行。检查点完成后禁止继续下一个任务。
