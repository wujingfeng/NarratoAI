# NarratoAI API 平台：Task 13B 续接提示词

在 worktree `/private/tmp/NarratoAI-narrato-api-platform`、分支 `codex/narrato-api-platform` 继续实施。不得创建新 worktree，不得 reset、restore、clean、删除或覆盖已有改动；尤其不得触碰预存未跟踪 `/.superpowers/` 与 `docs/web/docs/Oss.php`。

## 先恢复事实状态

只读执行：

1. `git status --short`
2. `git branch --show-current`
3. `git log --oneline --decorate -10`
4. 阅读 `docs/superpowers/progress/narrato-api-platform-resume-state.yaml`、`summary.md` 和本文件。
5. 按标题/行号读取 `docs/superpowers/plans/2026-07-16-narrato-api-platform.md:893-959` 及设计中 OSS 上传和状态机相关段落。

以 Git、测试和真实文件为准。当前事实：Task 12 完整完成于 `52e973f`；Task 13A 完成于 `14952da`；Task 13 仍为 `in_progress`；Gate 为 `Phase 5 / Gate B pending`。

## 本窗口唯一原子任务：Task 13B

只实现 Task 13 剩余上传链路：

- 认证用户的 OSS POST Policy；
- 前缀、扩展名/Content-Type、视频 300 MiB、SRT 5 MiB 限制；
- 上传完成后的 OSS HEAD 校验；
- 调用 Core 媒体探测，并将资产从 `validating` 更新为 `ready` 或 `invalid`。

可涉及：

- `docs/api/narratoApi/narrato_api/projects/{schemas,service,router}.py`
- `docs/api/narratoApi/narrato_api/assets/{schemas,service,router}.py`
- `docs/api/narratoApi/narrato_api/integrations/{oss_client,core_client}.py`
- Task 13A 模型的必要共享接口调整
- `tests/unit/test_oss_post_policy.py`、`tests/integration/test_upload_complete.py` 与直接受影响测试。

禁止实施工作流、Task 14/15、任务路由之外的功能。

## 执行与验证

严格 TDD：先新增测试并记录明确 RED，再做最小 GREEN。先运行新增和直接受影响测试；Gate 前不要扩大为全量测试。至少验证：未登录不签发 policy、对象键前缀和文件边界、HEAD 成功后触发 probe、状态 `validating -> ready/invalid`。完成后检查 diff 范围、提交业务代码与测试，并按当前协议创建新的检查点文件和单独 checkpoint 提交。
