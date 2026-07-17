# NarratoAI 多用户 API 平台续接摘要

## 当前检查点

- 分支：`codex/narrato-api-platform`
- worktree：`/private/tmp/NarratoAI-narrato-api-platform`
- Gate：**Phase 5 / Gate B pending**。
- 最新 Implementation Commit：`8ad2e01 feat(api): persist Core Jianying metadata for Task 15O`。

## 已完成基线

1. Task 14A--14E：版本化 DAG、事务 Outbox、Core 结果收口与补投边界。
2. Task 15A--15B：永久编辑等待、渲染锁与不可变 revision、草稿 LWW。
3. Task 15C--15E：终态删除资格、失败产物隐藏、已完成导出资格服务边界。
4. Task 15F--15I：已登记产物模型、事务内登记、完成项目读取和用户归属结果查询。
5. Task 15J--15M：纯 Jianying manifest 映射、用户归属服务、认证结果和 manifest 路由。
6. Task 15N：终态项目幂等异步删除请求与 `deleting` 转换；尚未实际删除 OSS 对象。
7. **Task 15O**：`RegisteredArtifact` 可选持久化 `size`、`checksum`、`content_type`、`width`、`height`、`duration`；纯 manifest 仅在值存在时透传这些元数据。新增迁移 `0012_artifact_core_manifest_metadata`。

## 本窗口验证

- TDD RED：`test_artifact_core_manifest_metadata.py` 初始 `2 failed`，因字段和注册参数尚不存在。
- GREEN：`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest tests/unit/test_artifact_core_manifest_metadata.py tests/unit/test_artifact_model.py tests/unit/test_artifact_registration.py tests/unit/test_jianying_manifest.py -q` → **8 passed**。
- Task 15O 目标 Ruff、format check 和 `git diff --check` 均通过。

## 风险与续接

- `alembic upgrade head --sql` 在已有 `0007_workflow_reconciliation` 的 SQLite batch-reflection 限制处停止，未构成本次 `0012` 在线迁移验证。
- 真实 PostgreSQL、Core HTTP 契约/集成、不可变 snapshot/timeline 转发、浏览器流式 ZIP、实际 OSS/Worker 删除仍未验证或未实现。
- 项目仍有 6 个既有 assets mypy 错误；默认 pytest 插件加载不稳定，继续使用 `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`。
- 预存未提交项只能是 `.superpowers/` 与 `docs/web/docs/Oss.php`，不得触碰。

## 唯一下一原子任务

**Task 15P**：只实现 typed Core Jianying manifest client boundary，向它转发已完成且归属用户项目的持久化资源元数据和不可变 editor snapshot/timeline 输入；不创建 ZIP、不写文件/OSS、不改浏览器 UI、不实现真实删除。完成检查点后立即停止。
