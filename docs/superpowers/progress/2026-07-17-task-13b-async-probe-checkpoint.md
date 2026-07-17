# Task 13B 异步探测收敛检查点

- 分支：`codex/narrato-api-platform`
- worktree：`/private/tmp/NarratoAI-narrato-api-platform`
- 业务提交：`7a1d06e fix: reconcile asynchronous upload probes`
- Gate：**Phase 5 / Gate B pending**；Task 13 仍为 `in_progress`。

## 本次闭环

1. Core `POST` 返回 `202` 时只持久化 `core_task_id`，不再在上传完成请求中立即 `GET` 一次。
2. 新增认证的单资产读取 `GET /api/v1/assets/{asset_id}`：资产仍为 `validating` 时在该后续请求轮询 Core，同一资产按 `succeeded -> ready`、`failed -> invalid` 收敛。
3. OSS HEAD 的临时失败统一映射为 `503 OSS_UNAVAILABLE`。
4. Policy 预留增加十分钟 TTL；过期且尚未提交 Core 的预留会在新的签发事务中清理，避免安全重签永久占用视频配额。
5. 签发预留在 PostgreSQL 使用项目行 `FOR UPDATE` 和同一事务内配额计数；SQLite 不具备等价行锁语义，测试仅断言 PostgreSQL 编译结果。

## TDD 与验证

- RED：新增异步 `202` 集成测试首次失败，显示上传完成请求错误地立即轮询 `core_1`；OSS HEAD 故障测试首次得到 `422` 而非期望 `503`。行锁测试初次因接口未实现收集失败。
- GREEN：
  ```bash
  cd docs/api/narratoApi && .venv/bin/python -m pytest \
    tests/unit/test_projects_assets_migration.py \
    tests/unit/test_project_asset_constraints.py \
    tests/unit/test_project_asset_models.py \
    tests/unit/test_oss_post_policy.py \
    tests/unit/test_core_upload_polling.py \
    tests/integration/test_upload_complete.py -q
  ```
  结果：`26 passed, 3 warnings`（FastAPI/Alembic 既有弃用告警）。
- Ruff、`alembic upgrade head`、`alembic check` 与 `git diff --check` 均通过。

## 范围与遗留风险

- 未引入工作流、DAG、回调、后台调度或 Task 14/15 功能；轮询仅由认证单资产读取请求触发。
- Fake OSS/Core 覆盖协议边界；真实 OSS 与 Core、以及真实 PostgreSQL 多连接并发仍待 Gate B 环境验证。
- 预存未跟踪 `/.superpowers/` 与 `docs/web/docs/Oss.php` 未修改、未暂存。
