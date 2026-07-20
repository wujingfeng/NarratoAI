# SEGMENTED_GOAL_PROTOCOL_V2：NarratoAI API 平台永久续接提示词

在既有 worktree `/private/tmp/NarratoAI-narrato-api-platform`、分支 `codex/narrato-api-platform` 中继续。不得创建新 worktree，不得 `reset`、`restore`、`clean`、删除或覆盖已有改动；不得触碰预存未跟踪 `/.superpowers/` 与 `docs/web/docs/Oss.php`。

## 开始时恢复真实进度

1. 运行 `git status --short`、`git branch --show-current`、`git log --oneline --decorate -20`。
2. 读取 `docs/superpowers/progress/narrato-api-platform-resume-state.yaml` 与 `narrato-api-platform-summary.md`。
3. 检查最近的 Task brief、report、提交和测试证据。若状态与 Git、实际文件或测试证据不一致，以实际证据重建状态；不得重复已提交且验证通过的功能，也不得丢弃未提交改动。

## 当前真实基线

- Task 17A 已完成：认证项目创建、费用估算和 ready-only 启动 API，提交 `5852e3b`。
- Task 17B 已完成：受保护 `/create` 路由、缺失 Create 依赖和 API 费用/ready 门禁，提交 `7b85c63`。
- Create route/flow verifier、API project-flow verifier 和 Vite build 已通过；Vite 的 >500 kB chunk advisory 保留。
- Gate C 仍因 ProjectResultPage 不可达以及编辑器真实 UI/浏览器保存验证而阻塞。

## 本窗口唯一原子任务：Task 17C

只恢复一个受保护的项目结果路由：由既有 API 加载完成项目的结果，并复用既有的完成态下载/剪映导出控件。严格 TDD：先让直接 result-route/data-flow verifier 失败，再实现并验证通过。不得修改 Create flow、添加编辑器 UI、probe duration 回填或 Task 19。

## 不可删除的永久规则

1. 协议标识 **SEGMENTED_GOAL_PROTOCOL_V2**。
2. 每个窗口只执行一个原子任务。
3. 开始时校验 Git 和 `resume-state.yaml`。
4. 结束时更新并提交检查点。
5. 仍有任务时必须再次生成 `next-prompt.md`。
6. 最终回复必须再次提示新建窗口续接。
7. 检查点完成后禁止继续下一个任务。

最终报告必须包含 Implementation Commit、Checkpoint Commit、测试、Gate、下一任务和工作区状态；仍有任务时明确提示：**请新建窗口，并再次使用 SEGMENTED_GOAL_PROTOCOL_V2 永久续接提示词。**
