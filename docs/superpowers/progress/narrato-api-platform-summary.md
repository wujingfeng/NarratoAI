# NarratoAI 多用户 API 平台续接摘要

## 当前检查点

- 分支：`codex/narrato-api-platform`
- worktree：`/private/tmp/NarratoAI-narrato-api-platform`
- Gate：**Task 15 的 Phase 5 / Gate B 已通过；Phase 6 pending**。

## Task 15 已完成

1. 编辑：永久 `waiting_for_edit`、草稿 LWW、不可变 revision、一次渲染锁和认证的读取/保存/提交接口。
2. 结果与导出：完成态/归属守卫、已登记产物持久化和读取、结果接口、纯 Jianying 映射及 Core-backed manifest 接口。
3. Core 输入：持久化 size、checksum、content type、宽高、时长；仅在 Core 调用前衍生其 `assets/*` 路径，纯 mapper 路径不变。
4. 删除：终态项目幂等删除请求、可恢复 Worker、OSS 404 幂等成功、失败审计；资产记录保留审计。

Task 15 最后实施提交：
- `8ad2e01`（15O 元数据）
- `834aa45`（15P Core Manifest）
- `1585b7a`（15Q 删除 Worker）
- `889a445`（保持纯 Manifest 路径）
- `c1a573f`（15R 编辑 HTTP）
- `4ad100d`（Gate 格式修复）

## Task 15 Gate 证据

- 新鲜 SQLite `alembic upgrade head` 通过 `0013_project_deletion_worker`。
- Task 15 直接单元/集成子集：**100 passed，1 个既有 Starlette TestClient 弃用警告**。
- Ruff check、Ruff format check 和 `git diff --check` 通过。

## 风险与续接

- 真实 PostgreSQL 并发、Core HTTP、OSS 删除和浏览器流式 ZIP 尚未真实联调。
- `retryable_failed` 删除 Job 的调度重试策略仍待后续实现。
- 项目仍有 6 个既有 assets mypy 错误；pytest 默认插件加载不稳定，继续使用 `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`。
- 预存未提交内容只能是 `.superpowers/` 与 `docs/web/docs/Oss.php`，不得触碰。

## 下一原子任务

**Task 16**：仅接入 Web 认证、统一 API Client、Token 存储与全局 401 清理；完成 checkpoint 后立即停止。
