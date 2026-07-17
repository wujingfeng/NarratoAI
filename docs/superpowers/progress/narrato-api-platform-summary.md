# NarratoAI 多用户 API 平台续接摘要

## 当前检查点

- 分支：`codex/narrato-api-platform`
- worktree：`/private/tmp/NarratoAI-narrato-api-platform`
- 项目 Gate：**Phase 5 / Gate B pending**（Task 15 尚未开始，不能宣称项目 Gate B 完成）。
- Task 14A--14E 与集中 Gate review 已完成；最新 Gate 修复/Implementation Commit：`ddd012d fix: preserve app logs during migrations`。

## Task 14 已完成部分

1. **14A**：固定版本的短剧解说 DAG 与状态机；拒绝用户取消/手动重试，`waiting_for_edit` 不自动超时。
2. **14B**：模板快照、workflow、节点、attempt、Outbox 和迁移持久化。
3. **14C**：从不可变快照事务化建立 workflow/节点；状态变更和唯一 Outbox 同时提交。
4. **14D**：callback 与 polling 经同一幂等收口事务处理，不覆盖已确认终态。
5. **14E**：条件领取 due pending Outbox；只唤醒注入 callable；失败回到 durable pending。
6. **Gate review**：发现 Alembic `fileConfig()` 会禁用既有业务 logger；新增 RED/GREEN 回归测试并在 `ddd012d` 修复。OpenAPI 契约补齐既有上传/资产路由，仍为精确断言。

## 新鲜验证证据

- Gate 直接验证：`25 passed, 4 warnings`。
- 全量：`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -q` 为 `135 passed, 7 skipped, 7 warnings`。
- Ruff、Alembic `upgrade head`/`check`、`git diff --check` 通过。
- Mypy 仍有 6 个既有 `assets/service.py`、`assets/router.py` 类型错误，未扩大 Task 14 范围修复。

## 范围、风险与续接

- 本分段没有实现 Core HTTP、router、polling、SSE、数据库重投扫描、Task 15 或下游执行；这些不得被误报为 Task 14 已完成能力。
- 真实 OSS/Core 集成和 PostgreSQL 多连接语义仍未验证；pytest 使用 `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`。
- 预存未跟踪 `/.superpowers/`、`docs/web/docs/Oss.php` 不得触碰；本窗口三个永久进度文件待单独 checkpoint 提交。
- 唯一下一原子任务：**Task 15A**。只启动一个可独立验证的编辑锁定/永久等待边界子任务；完成 checkpoint 后立即停止，不得开始下一个 Task 15 子任务。
