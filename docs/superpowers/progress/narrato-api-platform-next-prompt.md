# SEGMENTED_GOAL_PROTOCOL_V2：NarratoAI API 平台永久续接提示词

在既有 worktree `/private/tmp/NarratoAI-narrato-api-platform`、分支 `codex/narrato-api-platform` 中继续。不得创建新 worktree，不得 `reset`、`restore`、`clean`、删除或覆盖已有改动；不得触碰预存未跟踪 `/.superpowers/`、`docs/web/docs/Oss.php` 与 `docs/web/homepage-prototype/.playwright-cli/`。

## 开始时恢复真实进度

1. 运行 `git status --short`、`git branch --show-current`、`git log --oneline --decorate -20`。
2. 读取 `docs/superpowers/progress/narrato-api-platform-resume-state.yaml` 与 `narrato-api-platform-summary.md`。
3. 检查最近的 Gate report、提交和测试证据。若状态与 Git、实际文件或测试证据不一致，以实际证据重建状态；不得重复已提交且验证通过的功能，也不得丢弃未提交改动。

## 当前真实基线

- Task 17 已完整恢复，提交为 `5852e3b`、`7b85c63`、`697387b`、`91a428b`。
- Gate C 直接验证共 18 项与 production build 已通过；三个未认证受保护路由在真实浏览器中均跳转 `/login`。
- Gate C 仍阻塞：没有本地认证 API/ready+completed 项目 fixture，因此无法在真实 Chrome/Edge 用户手势下验证 File System Access 剪映 ZIP 导出。详见 `docs/superpowers/progress/2026-07-20-gate-c-reevaluation-report.md`。

## 本窗口唯一原子任务：Gate C authenticated browser acceptance

启动或连接可用的本地认证 API，并准备 ready 和 completed 项目 fixture。用桌面 Chrome 或 Edge 完成 Create → Result → 点击“导出到剪映草稿”流程，记录 File System Access 保存选择器和流式 ZIP 成功的简洁证据。Gate C 通过前绝不开始 Task 19；若环境仍不可用，准确记录阻塞而不伪造证据。

## 不可删除的永久规则

1. 协议标识 **SEGMENTED_GOAL_PROTOCOL_V2**。
2. 每个窗口只执行一个原子任务。
3. 开始时校验 Git 和 `resume-state.yaml`。
4. 结束时更新并提交检查点。
5. 仍有任务时必须再次生成 `next-prompt.md`。
6. 最终回复必须再次提示新建窗口续接。
7. 检查点完成后禁止继续下一个任务。

最终报告必须包含 Implementation Commit、Checkpoint Commit、测试、Gate、下一任务和工作区状态；仍有任务时明确提示：**请新建窗口，并再次使用 SEGMENTED_GOAL_PROTOCOL_V2 永久续接提示词。**
