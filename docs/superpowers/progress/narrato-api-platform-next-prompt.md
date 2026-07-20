# SEGMENTED_GOAL_PROTOCOL_V2：NarratoAI API 平台永久续接提示词

在既有 worktree `/private/tmp/NarratoAI-narrato-api-platform`、分支 `codex/narrato-api-platform` 中继续。不得创建新 worktree，不得 `reset`、`restore`、`clean`、删除或覆盖已有改动；不得触碰预存未跟踪 `/.superpowers/`、`docs/web/docs/Oss.php` 与 `docs/web/homepage-prototype/.playwright-cli/`。

## 开始时恢复真实进度

1. 运行 `git status --short`、`git branch --show-current`、`git log --oneline --decorate -20`。
2. 读取 `docs/superpowers/progress/narrato-api-platform-resume-state.yaml` 与 `narrato-api-platform-summary.md`。
3. 检查最近的 Gate report、提交和测试证据。若状态与 Git、实际文件或测试证据不一致，以实际证据重建状态；不得重复已提交且验证通过的功能，也不得丢弃未提交改动。

## 当前真实基线

- Gate C 已通过：用户明确接受真实隔离 FastAPI、认证浏览器、完成态 manifest、File System Access 调用及流式 ZIP 证据；原生 macOS picker 可见选址未自动捕获，作为上线后人工复核项保留。
- Task 19 尚未开始；按小原子单元先执行 Task 19A。

## 本窗口唯一原子任务：Task 19A

仅创建 Business API 的 web、worker、scheduler Supervisor 定义及静态 `verify-supervisor-config.py`。严格 TDD：先让 verifier 因配置缺失失败，再实现使其验证命令、目录、自动启动/重启、进程组停止、优雅超时和独立日志路径。不得创建 Core Supervisor、Nginx、README 大幅改写或 Task 20 内容。

## 不可删除的永久规则

1. 协议标识 **SEGMENTED_GOAL_PROTOCOL_V2**。
2. 每个窗口只执行一个原子任务。
3. 开始时校验 Git 和 `resume-state.yaml`。
4. 结束时更新并提交检查点。
5. 仍有任务时必须再次生成 `next-prompt.md`。
6. 最终回复必须再次提示新建窗口续接。
7. 检查点完成后禁止继续下一个任务。

最终报告必须包含 Implementation Commit、Checkpoint Commit、测试、Gate、下一任务和工作区状态；仍有任务时明确提示：**请新建窗口，并再次使用 SEGMENTED_GOAL_PROTOCOL_V2 永久续接提示词。**
