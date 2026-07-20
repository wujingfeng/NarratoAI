# SEGMENTED_GOAL_PROTOCOL_V2：NarratoAI API 平台永久续接提示词

在既有 worktree `/private/tmp/NarratoAI-narrato-api-platform`、分支 `codex/narrato-api-platform` 中继续。不得创建新 worktree，不得 `reset`、`restore`、`clean`、删除或覆盖已有改动；不得触碰预存未跟踪 `/.superpowers/`、`docs/web/docs/Oss.php` 与 `docs/web/homepage-prototype/.playwright-cli/`。

## 开始时恢复真实进度

1. 运行 `git status --short`、`git branch --show-current`、`git log --oneline --decorate -20`。
2. 读取 `docs/superpowers/progress/narrato-api-platform-resume-state.yaml` 与 `narrato-api-platform-summary.md`。
3. 检查最近的 Task brief、提交和测试证据。若状态与 Git、实际文件或测试证据不一致，以实际证据重建状态；不得重复已提交且验证通过的功能，也不得丢弃未提交改动。

## 当前真实基线

- Gate C 已通过（用户接受原生 picker 证据例外）；Task 19 全部完成，Task 20A、20B 已完成，Gate D 待剩余 Task 20 验收。
- Task 19 提交：`e776d9e`、`462ab86`、`3a6bc20`、`2a27f9c`。静态部署、README、编译和 lint 证据已通过；macOS sandbox 无法运行 nginx -t。

## 本窗口唯一原子任务：Task 20C

仅完成一个双服务迁移验收切片：使用 fresh SQLite URL 分别执行 Core 与 Business 的 Alembic upgrade 和 check，并记录真实结果。若发现迁移缺陷，只添加最小直接回归测试或修复；不得添加 workflow recovery、完整 e2e 或真实 Provider smoke。

## 不可删除的永久规则

1. 协议标识 **SEGMENTED_GOAL_PROTOCOL_V2**。
2. 每个窗口只执行一个原子任务。
3. 开始时校验 Git 和 `resume-state.yaml`。
4. 结束时更新并提交检查点。
5. 仍有任务时必须再次生成 `next-prompt.md`。
6. 最终回复必须再次提示新建窗口续接。
7. 检查点完成后禁止继续下一个任务。

最终报告必须包含 Implementation Commit、Checkpoint Commit、测试、Gate、下一任务和工作区状态；仍有任务时明确提示：**请新建窗口，并再次使用 SEGMENTED_GOAL_PROTOCOL_V2 永久续接提示词。**
