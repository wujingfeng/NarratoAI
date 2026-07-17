# SEGMENTED_GOAL_PROTOCOL_V2：NarratoAI API 平台永久续接提示词

在既有 worktree `/private/tmp/NarratoAI-narrato-api-platform`、分支 `codex/narrato-api-platform` 中继续。不得创建新 worktree，不得 `reset`、`restore`、`clean`、删除或覆盖已有改动；不得触碰预存未跟踪 `/.superpowers/` 与 `docs/web/docs/Oss.php`。

## 开始时恢复真实进度

1. 运行 `git status --short`、`git branch --show-current`、`git log --oneline --decorate -20`。
2. 读取 `docs/superpowers/progress/narrato-api-platform-resume-state.yaml` 与 `narrato-api-platform-summary.md`。
3. 若状态与 Git、实际文件或测试证据不一致，以实际证据重建状态；不得重复已提交且验证通过的功能，也不得丢弃未提交改动。

## 当前真实基线

- Task 15 已完成并通过 Gate：新鲜 SQLite migration 到 `0013_project_deletion_worker`，Task 15 直接子集 `100 passed, 1 warning`。
- 最新 Task 15 实施提交：`4ad100d style(api): format project service for Task 15 Gate`。
- 后续从 Task 16 开始，Task 15 不得重新实现。

## 本窗口唯一原子任务：Task 16

只实现 React Web 认证接入：统一 API client、Token 存储、Authorization Header、全局 401 清理、登录页与应用接线。严格 TDD：先让 `scripts/verify-api-auth.mjs` 失败，再最小实现使其通过；运行该脚本和直接相关的 Web build。不得实施 Task 17。

## 不可删除的永久规则

1. 协议标识 **SEGMENTED_GOAL_PROTOCOL_V2**。
2. 每个窗口只执行一个原子任务。
3. 开始时校验 Git 和 `resume-state.yaml`。
4. 结束时更新并提交检查点。
5. 仍有任务时必须再次生成 `next-prompt.md`。
6. 最终回复必须再次提示新建窗口续接。
7. 检查点完成后禁止继续下一个任务。

最终报告必须包含 Implementation Commit、Checkpoint Commit、测试、Gate、下一任务和工作区状态；仍有任务时明确提示：**请新建窗口，并再次使用 SEGMENTED_GOAL_PROTOCOL_V2 永久续接提示词。**
