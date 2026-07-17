# SEGMENTED_GOAL_PROTOCOL_V2：NarratoAI API 平台永久续接提示词

在既有 worktree `/private/tmp/NarratoAI-narrato-api-platform`、分支 `codex/narrato-api-platform` 中继续。不得创建新 worktree，不得 `reset`、`restore`、`clean`、删除或覆盖已有改动；不得触碰预存未跟踪 `/.superpowers/` 与 `docs/web/docs/Oss.php`。

## 当前真实基线

- 最近 Implementation Commit：`3b4ea19 feat(api): add terminal project deletion requests`。
- Task 15A--15N 已完成；结果路由、Manifest 路由和终态删除请求审计已具备。
- Task 15 Gate 子集：`90 passed, 1 warning`；全新 SQLite Alembic 升级通过 `0011_project_deletion_jobs`。
- Task 15 尚未完成真实 OSS/Worker 删除与 Core 剪映基础文件转发；Core 资源输入所需 size/checksum/content type/video 元数据尚未持久化。
- 预期未提交内容仅为 `.superpowers/` 与 `docs/web/docs/Oss.php`。

## 本窗口唯一原子任务：Task 15O

只实现 **Core Jianying resource metadata persistence**。严格 TDD：先写测试并观察预期 RED，再以最小代码使其 GREEN。只为 RegisteredArtifact 持久化 Core 资源所需 size、checksum、content type 与可选视频 metadata；不得调用 Core、创建 ZIP、写文件/OSS、修改路由或实施第二个 Task 15 子项。

## 不可删除的永久规则

1. 协议标识 **SEGMENTED_GOAL_PROTOCOL_V2**。
2. 每个窗口只执行一个原子任务。
3. 开始时校验 Git 和 `resume-state.yaml`。
4. 结束时更新并提交检查点。
5. 仍有任务时必须再次生成 `next-prompt.md`。
6. 最终回复必须再次提示新建窗口续接。
7. 检查点完成后禁止继续下一个任务。

结束时必须报告 Task 15O 的 Implementation Commit、Checkpoint Commit、测试、Gate、下一任务和工作区状态；仍有任务时明确提示：请新建窗口，并再次使用 SEGMENTED_GOAL_PROTOCOL_V2 永久续接提示词。
