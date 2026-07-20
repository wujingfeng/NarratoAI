# SEGMENTED_GOAL_PROTOCOL_V2：NarratoAI API 平台永久续接提示词

在既有 worktree `/private/tmp/NarratoAI-narrato-api-platform`、分支 `codex/narrato-api-platform` 中继续。不得创建新 worktree，不得 `reset`、`restore`、`clean`、删除或覆盖已有改动；不得触碰预存未跟踪 `/.superpowers/` 与 `docs/web/docs/Oss.php`。

## 开始时恢复真实进度

1. 运行 `git status --short`、`git branch --show-current`、`git log --oneline --decorate -20`。
2. 读取 `docs/superpowers/progress/narrato-api-platform-resume-state.yaml` 与 `narrato-api-platform-summary.md`。
3. 检查最近的 Task brief、report、提交和测试证据。若状态与 Git、实际文件或测试证据不一致，以实际证据重建状态；不得重复已提交且验证通过的功能，也不得丢弃未提交改动。

## 当前真实基线

- Task 17 已完整恢复：项目生命周期 API（`5852e3b`）、Create flow（`7b85c63`）、项目结果路由（`697387b`）及编辑器保存/渲染锁定 UI（`91a428b`）。
- Task 17 的 13 项直接验证均通过，Vite production build 通过；保留既有 >500 kB chunk advisory。
- 当前为 Gate C 重新验收，必须先完成 Task 16–18 的集中复核及浏览器证据，不能提前进入 Task 19。

## 本窗口唯一原子任务：Gate C re-evaluation

运行 Task 16–18 的直接验证和 production build，检查受保护 Create、结果、编辑器路由与完成态导出控制。使用真实浏览器会话验证或准确记录 Chrome/Edge 用户手势 File System Access 保存证据缺口。输出 Gate C 报告并决定通过或继续阻塞；没有 Gate C 通过结论不得开始 Task 19。

## 不可删除的永久规则

1. 协议标识 **SEGMENTED_GOAL_PROTOCOL_V2**。
2. 每个窗口只执行一个原子任务。
3. 开始时校验 Git 和 `resume-state.yaml`。
4. 结束时更新并提交检查点。
5. 仍有任务时必须再次生成 `next-prompt.md`。
6. 最终回复必须再次提示新建窗口续接。
7. 检查点完成后禁止继续下一个任务。

最终报告必须包含 Implementation Commit、Checkpoint Commit、测试、Gate、下一任务和工作区状态；仍有任务时明确提示：**请新建窗口，并再次使用 SEGMENTED_GOAL_PROTOCOL_V2 永久续接提示词。**
