# NarratoAI 多用户 API 平台续接摘要

## 当前检查点

- 分支：`codex/narrato-api-platform`
- worktree：`/private/tmp/NarratoAI-narrato-api-platform`
- 当前 Gate：**Phase 5 / Gate B pending**
- Task 13：已完成。Task 13A：`14952da`；Task 13B：`fc6fe20`，后续修正：`9bde894`、`7a1d06e`。
- 本窗口完成：Task 14A。
- 实施提交：`6ea93bf feat: add workflow state machine template`。
- Task 14：`in_progress`；Task 14A 已完成。

## Task 14A 完成内容

1. 新增版本化短剧解说 DAG 模板 `short_drama_narration_v1`。
2. 固定节点顺序：`media_probe -> asr -> video_analysis -> script_generation -> waiting_for_edit -> tts -> subtitle -> video_render -> publish_artifacts`；`video_analysis` 依赖探测与 ASR，后续节点按链路依赖。
3. 新增纯状态机规则：拒绝用户取消和手动重试；`waiting_for_edit` 不自动超时或失败；`completed`、`failed` 终态不可恢复。
4. 新增纯自动重试候选判断，不包含调度、持久化或运行时执行。

## 验证证据

```bash
cd docs/api/narratoApi
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest \
  tests/unit/test_workflow_state_machine.py \
  tests/unit/test_short_drama_template_v1.py -q
```

结果：`7 passed in 0.01s`。

- Ruff：`narrato_api/workflows` 与两个新增测试通过。
- `git show --check 6ea93bf`：通过。
- 本环境默认 pytest 插件加载不稳定，聚焦测试固定禁用自动插件加载。

## 范围与风险

- Task 14A 未实现数据库模型/迁移、Outbox、Core 回调/轮询、Celery、HTTP router、SSE 或 Task 15。
- 后续仍需验证真实 OSS/Core 集成与 PostgreSQL 多连接行为。
- 预存未跟踪 `/.superpowers/`、`docs/web/docs/Oss.php` 未修改、未暂存、未提交。

## 下一原子任务

仅执行 **Task 14B**：新增工作流持久化模型和 `0005_workflows` 迁移，覆盖版本化 DAG 快照、工作流实例/节点、node attempt 和 Outbox 等数据库数据结构及其模型/迁移测试。禁止实施回调、轮询、Celery、router、SSE 或 Task 15。
