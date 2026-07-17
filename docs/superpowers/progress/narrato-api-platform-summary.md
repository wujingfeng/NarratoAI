# NarratoAI 多用户 API 平台续接摘要

## 当前检查点

- 分支：`codex/narrato-api-platform`
- worktree：`/private/tmp/NarratoAI-narrato-api-platform`
- Gate：**Phase 5 / Gate B pending**
- Task 13 已完成：`14952da`、`fc6fe20`，修正 `9bde894`、`7a1d06e`。
- Task 14 为 `in_progress`；Task 14A、Task 14B 已完成。
- 最新实施提交：`60de8c8 feat: add workflow persistence models`。

## Task 14 已完成部分

### Task 14A

1. 版本化短剧解说 DAG 模板：`media_probe -> asr -> video_analysis -> script_generation -> waiting_for_edit -> tts -> subtitle -> video_render -> publish_artifacts`。
2. 纯状态机：拒绝用户取消/手动重试，终态不可恢复，`waiting_for_edit` 不自动超时。

### Task 14B

1. 新增模板快照、工作流实例、工作流节点、节点尝试和 Outbox 持久化模型及其归属、状态、依赖、唯一性与查询约束。
2. 新增 `0006_workflows` Alembic 迁移。由于 `0005_asset_probe_reservations` 已存在，不能覆盖旧迁移；`0006_workflows` 正确衔接该 revision。
3. 新增模型和迁移聚焦测试。

## 新鲜验证证据

```bash
cd docs/api/narratoApi
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest \
  tests/unit/test_workflow_models.py \
  tests/unit/test_workflows_migration.py \
  tests/unit/test_workflow_state_machine.py \
  tests/unit/test_short_drama_template_v1.py -q
```

结果：`10 passed, 2 warnings`。

- Ruff：通过。
- `git show --check 60de8c8`：通过。
- 本环境默认 pytest 插件加载不稳定，聚焦测试固定禁用自动插件加载。

## 范围与风险

- Task 14C 尚未实现：纯数据库事务内的 DAG 实例化、持久化状态转换与 Outbox 写入。
- 未实现 Core 回调/轮询、Celery、dispatcher、router、SSE、Task 15 或其他工作流运行时。
- 真实 OSS/Core 集成与 PostgreSQL 多连接行为尚未验证。
- 预存未跟踪 `/.superpowers/`、`docs/web/docs/Oss.php` 未修改、未暂存、未提交。

## 下一原子任务

仅执行 **Task 14C**：实现工作流服务层的 DAG 实例化与持久化状态转换/Outbox 写入的纯数据库事务及聚焦测试。禁止回调、轮询、Celery、router、SSE 等运行时功能；完成检查点后立即结束。
