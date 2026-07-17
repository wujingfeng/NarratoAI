# NarratoAI 多用户 API 平台续接摘要

## 当前检查点

- 分支：`codex/narrato-api-platform`
- worktree：`/private/tmp/NarratoAI-narrato-api-platform`
- 当前 Gate：**Phase 5 / Gate B pending**
- 最近完整完成的 Task：Task 12，提交 `52e973f feat: add credit ledger and pricing`
- 本窗口完成：Task 13A
- 实施提交：`14952da feat: add project asset domain constraints`
- Task 13 总体状态：`in_progress`；Task 13A 已完成。

## Task 13A 完成内容

1. 新建 `projects` 与 `assets` SQLAlchemy 持久化模型。
2. 新增 Alembic `0004_projects_assets`，从 `0003_billing` 建立项目和资产表。
3. 两表均含用户归属外键、状态 CHECK、时间戳和面向归属查询的索引；资产还包含项目外键、文件名长度/大小约束和 OSS 对象唯一性。
4. 增加纯声明约束：每个项目最多 5 个视频；视频扩展名 `.mp4/.mov/.avi`、最大 300 MiB；字幕扩展名 `.srt`、最大 5 MiB；文件名最大 255 字符。
5. 添加模型、约束和迁移链的聚焦测试。

## TDD 与验证证据

- RED：新增测试首次执行因模块未实现而出现 `ModuleNotFoundError: narrato_api.assets`。
- GREEN：
  ```bash
  cd docs/api/narratoApi && .venv/bin/python -m pytest \
    tests/unit/test_project_asset_constraints.py \
    tests/unit/test_project_asset_models.py \
    tests/unit/test_projects_assets_migration.py -q
  ```
  结果：`11 passed, 2 warnings`。
- `alembic upgrade head && alembic check`：通过。
- 受影响文件 Ruff：通过。
- `git show --check 14952da`：通过。

## 范围决策

本检查点故意只完成持久化模型、迁移与声明约束。没有实现 HTTP 路由、OSS POST 策略、上传确认、Core 客户端或媒体探测；这些属于 Task 13B。

## 风险与工作区状态

- 真实 OSS、Core 集成尚未验证。
- PostgreSQL 多连接行为尚未验证；本 Task 的模型和迁移测试使用 SQLite。
- 工作区不会为空：预先存在的未跟踪 `/.superpowers/` 与 `docs/web/docs/Oss.php` 未修改、未暂存、未提交。

## 下一原子任务

仅执行 **Task 13B**：实现 OSS POST 策略、上传确认和 Core 媒体探测对接。验收要求：鉴权；对象前缀/类型/大小限制；OSS HEAD 确认；资产 `validating -> ready/invalid`；不实施工作流或 Task 14/15 内容。
