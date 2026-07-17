# Task 14 Gate B 复核报告

日期：2026-07-17  
范围：仅复核已提交的 Task 14A--14E；未实现或修改 Core HTTP、router、polling、SSE、重投扫描、Task 15 或下游运行行为。

## 需求对齐复核

- **14A**：`short_drama_narration_v1` 固定为 `media_probe -> asr -> video_analysis -> script_generation -> waiting_for_edit -> tts -> subtitle -> video_render -> publish_artifacts`；状态机拒绝用户取消和用户手动重试，`waiting_for_edit` 不存在自动失败转换。
- **14B**：`0006_workflows` 与模型保存不可变模板快照、每项目唯一 workflow、节点/attempt、Outbox；唯一键与外键覆盖节点 attempt 和 Outbox 幂等键。
- **14C**：`WorkflowService` 在单一事务内从快照建立 workflow/节点；状态转换与唯一 `workflow.state_changed` Outbox 一起提交。
- **14D**：callback/polling 都进入 `WorkflowReconciler._reconcile`；对同一 attempt 的旧/同版本终态无副作用，终态不会被覆盖。
- **14E**：dispatcher 以 `pending + available_at` 条件更新领取一个事件，只把稳定 event id/idempotency key 交给注入 wake-up；异常时回写 `pending` 并保留 attempt count。

原始总计划中列出的 router、任务执行、数据库扫描补投和 SSE 仍是后续分段边界，未在本 Gate 伪称已完成。

## 独立代码审查

发现一个 Gate-blocking 测试隔离缺陷：Alembic `fileConfig()` 默认禁用既有 `narrato_api` logger。完整 pytest 中，先执行的迁移测试会导致后续安全日志断言丢失。

- 新增回归测试 `test_alembic_migration_does_not_disable_business_logger`，修复前按预期 RED（`namespace.disabled == True`）。
- 修复：`migrations/env.py` 改为 `fileConfig(..., disable_existing_loggers=False)`；保留 Alembic 日志配置且不关闭业务日志。
- 同时更新 OpenAPI 精确路径契约，纳入已存在、已受测的三条上传/资产接口；没有放宽为子集断言。
- 未发现 Task 14A--14E 的额外阻塞性缺陷；本轮没有扩展业务能力。

## 验证证据

- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -q`：**135 passed, 7 skipped, 7 warnings**。
- `.venv/bin/python -m ruff check .`：**All checks passed**。
- `.venv/bin/python -m alembic upgrade head && .venv/bin/python -m alembic check`：升级至 `0007_workflow_reconciliation`，且 **No new upgrade operations detected**。
- `git diff --check`：通过。
- `.venv/bin/python -m mypy narrato_api`：**未通过，6 个既有资产模块类型错误**（`assets/service.py` 4 个、`assets/router.py` 2 个）；不属于 Task 14 代码且本窗口未扩大范围修复。

## Gate 结论与风险

- **Task 14 Gate B 复核：通过（带已记录的全库 mypy 基线风险）**；日志隔离缺陷已用 TDD 修复。
- **项目 Gate：仍为 `Phase 5 / Gate B pending`**，因为总计划的 Task 15 及其验收尚未完成；不能宣称业务面 Gate B 已整体达成。
- 未验证：真实 PostgreSQL 多连接/行锁语义、真实 OSS/Core 集成，以及总库 mypy 清零。
- 建议下一原子任务：按永久续接协议执行 **Task 15A** 的最小可验证子任务；不得在本报告所涉范围继续开发。
