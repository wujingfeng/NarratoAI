# SEGMENTED_GOAL_PROTOCOL_V2：NarratoAI API 平台永久续接提示词

在既有 worktree `/private/tmp/NarratoAI-narrato-api-platform`、分支 `codex/narrato-api-platform` 中继续。不得创建新 worktree，不得 `reset`、`restore`、`clean`、删除或覆盖已有改动；不得触碰预存未跟踪 `/.superpowers/` 与 `docs/web/docs/Oss.php`。

## 开始时恢复真实进度

1. 运行 `git status --short`、`git branch --show-current`、`git log --oneline --decorate -20`。
2. 读取 `docs/superpowers/progress/narrato-api-platform-resume-state.yaml` 与 `narrato-api-platform-summary.md`。
3. 检查最近的 Task brief、report、提交和测试证据。若状态与 Git、实际文件或测试证据不一致，以实际证据重建状态；不得重复已提交且验证通过的功能，也不得丢弃未提交改动。

## 当前真实基线

- Task 18 已完成：桌面 Chrome/Edge File System Access 守卫、Range 流式 CDN ZIP、错误 abort/retry，以及完成项目的两个固定导出动作。
- Task 18 实施提交：`6734fb5 feat: add client-side jianying export`。
- 验证：Jianying export verifier 4 项 PASS 与 `npm run build` PASS；Vite 保留已有大 chunk advisory。

## 本窗口唯一原子任务：Gate C

只执行 Phase 6 的需求复核、独立代码审查和 Web 闭环验证。核对 Task 16-18 是否使真实 UI 不依赖 Mock 数据，并取得桌面 Chrome/Edge 生成剪映 ZIP 的证据；若不满足，记录最小、可独立验证的修复或阻塞。不得开始 Task 19。

## 不可删除的永久规则

1. 协议标识 **SEGMENTED_GOAL_PROTOCOL_V2**。
2. 每个窗口只执行一个原子任务。
3. 开始时校验 Git 和 `resume-state.yaml`。
4. 结束时更新并提交检查点。
5. 仍有任务时必须再次生成 `next-prompt.md`。
6. 最终回复必须再次提示新建窗口续接。
7. 检查点完成后禁止继续下一个任务。

最终报告必须包含 Implementation Commit、Checkpoint Commit、测试、Gate、下一任务和工作区状态；仍有任务时明确提示：**请新建窗口，并再次使用 SEGMENTED_GOAL_PROTOCOL_V2 永久续接提示词。**
