# NarratoAI 多用户 API 平台续接摘要

## 当前检查点

- 分支：`codex/narrato-api-platform`
- worktree：`/private/tmp/NarratoAI-narrato-api-platform`
- 项目 Gate：**Phase 5 / Gate B pending**；Task 15 仍有未完成子任务。
- 最新 Implementation Commit：`d98394a feat: add pure jianying manifest resource mapping`（Task 15J）。

## 已完成

1. **Task 14A--14E + Gate review**：版本化 DAG、持久化/事务 Outbox、callback/polling 幂等收口、Outbox wake-up 及 Alembic 日志修复。
2. **Task 15A**：无过期 `waiting_for_edit`、render lock、提交后不可变 revision 和 pending render Outbox。
3. **Task 15B**：每项目唯一 `EditorDraft`，最后接受保存覆盖当前草稿；提交前复制为 immutable revision。
4. **Task 15C**：仅完成删除资格守卫；`completed`/`failed` 通过，所有非终态稳定为 `PROJECT_NOT_TERMINAL`，不执行实际删除。
5. **Task 15D**：仅完成产物可见性服务守卫；`completed` 保留已登记序列，`failed` 和所有非完成状态均不暴露产物。
6. **Task 15E**：仅完成导出资格服务守卫；只有 `completed` 通过，`failed` 和所有非完成状态稳定返回 `PROJECT_NOT_COMPLETED`。
7. **Task 15F**：仅完成已登记产物的持久化模型与迁移；模型字段为项目归属、种类、CDN URL 和创建时间。
8. **Task 15G**：仅完成调用方事务内的产物登记服务；服务仅 `session.add()`，不自行提交或回滚。
9. **Task 15H**：仅完成 completed 项目的已登记产物读取服务；按 `created_at/id` 稳定排序，其他状态均为空。
10. **Task 15I**：仅完成用户归属的 completed 项目结果查询；仅 `user_id + project_id` 命中且完成时返回最小结果记录。
11. **Task 15J**：仅完成纯剪映 Manifest 资源映射；固定包名、按产物 ID 排序，路径不依赖 URL。

## 新鲜验证证据

- Task 15J RED：缺少 `narrato_api.exports`（3 个预期失败）。
- Task 15J 直接复验：`3 passed in 0.27s`（路径安全、确定性和无 I/O 依赖）。
- Task 15J Ruff、`git diff --check` 通过。

## 范围、风险与续接

- Task 15J 未实现实际删除、受用户归属的 Manifest 服务、HTTP/结果呈现、Core 基础文件、router、下游或其他 Task 15 子任务。
- SQLite/PostgreSQL 并发差异、真实 OSS/Core 集成和 6 个既有 assets mypy 错误仍是风险。
- 预期未提交内容仅 `/.superpowers/` 与 `docs/web/docs/Oss.php`，二者不得触碰。
- 唯一下一原子任务：**Task 15K**，只实现用户归属 completed 项目的剪映 Manifest 服务；完成 checkpoint 后立即停止。
