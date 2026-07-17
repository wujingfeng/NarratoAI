# SEGMENTED_GOAL_PROTOCOL_V2：NarratoAI API 平台永久续接提示词

在既有 worktree `/private/tmp/NarratoAI-narrato-api-platform`、分支 `codex/narrato-api-platform` 中继续。不得创建新 worktree，不得 `reset`、`restore`、`clean`、删除或覆盖已有改动；不得触碰预存未跟踪 `/.superpowers/` 与 `docs/web/docs/Oss.php`。

## 开始时恢复真实进度

1. 运行 `git status --short`、`git branch --show-current`、`git log --oneline --decorate -20`。
2. 读取 `docs/superpowers/progress/narrato-api-platform-resume-state.yaml` 与 `narrato-api-platform-summary.md`。
3. 检查最近的 Task brief、report、提交和测试证据。若状态与 Git、实际文件或测试证据不一致，以实际证据重建状态；不得重复已提交且验证通过的功能，也不得丢弃未提交改动。

## 当前真实基线

- Task 17 已完成：OSS POST 上传后立即 complete、300 MiB 前置限制、费用估算、ready-only 项目启动、资产轮询、带 Bearer/Last-Event-ID 的 SSE reader，以及 render 后只读的防抖编辑保存。
- Task 17 实施提交：`34d77dc feat: connect project workflow api`。
- 验证：project-flow verifier 6 项 PASS 与 `npm run build` PASS；Vite 保留已有大 chunk advisory。

## 本窗口唯一原子任务：Task 18

只实现结果页固定下载动作和浏览器流式剪映 ZIP。严格 TDD：先让 `scripts/verify-jianying-export.mjs` 失败，再最小实现使其通过；运行该脚本和直接相关 Web build。不得实施任何后续任务。

## 不可删除的永久规则

1. 协议标识 **SEGMENTED_GOAL_PROTOCOL_V2**。
2. 每个窗口只执行一个原子任务。
3. 开始时校验 Git 和 `resume-state.yaml`。
4. 结束时更新并提交检查点。
5. 仍有任务时必须再次生成 `next-prompt.md`。
6. 最终回复必须再次提示新建窗口续接。
7. 检查点完成后禁止继续下一个任务。

最终报告必须包含 Implementation Commit、Checkpoint Commit、测试、Gate、下一任务和工作区状态；仍有任务时明确提示：**请新建窗口，并再次使用 SEGMENTED_GOAL_PROTOCOL_V2 永久续接提示词。**
