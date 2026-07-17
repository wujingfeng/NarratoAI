# Task 13B 检查点：OSS 上传校验

- 分支：`codex/narrato-api-platform`
- worktree：`/private/tmp/NarratoAI-narrato-api-platform`
- 业务提交：`fc6fe20 feat: add oss upload validation`
- Task 13：Task 13A 与 Task 13B 已完成；本检查点未实现任何工作流、Task 14 或 Task 15 功能。

## 已完成

1. 仅向认证且拥有项目的用户签发 OSS POST Policy，键固定在 `narrato/api/YYYY/MM/DD/` 前缀。
2. Policy 绑定单一对象键、扩展名对应 Content-Type 和内容长度上限：视频 300 MiB，SRT 5 MiB。
3. 上传确认会重新校验声明，执行 OSS HEAD，核对对象键、长度和 Content-Type 后登记 `validating` 资产。
4. 调用 Core 媒体探测；同步探测结论将资产转换为 `ready` 或 `invalid`。Core 的 `202` 异步确认会保留 `validating`，留待后续已规划的状态回收链路处理。

## TDD 与验证

- RED：
  ```bash
  cd docs/api/narratoApi && .venv/bin/python -m pytest \
    tests/unit/test_oss_post_policy.py tests/integration/test_upload_complete.py -q
  ```
  初次结果为 `ModuleNotFoundError: narrato_api.integrations.oss_client` 和 `ModuleNotFoundError: narrato_api.assets.router`，原因是 Task 13B 功能尚未实现。
- GREEN：
  ```bash
  cd docs/api/narratoApi && .venv/bin/python -m pytest \
    tests/unit/test_oss_post_policy.py tests/integration/test_upload_complete.py \
    tests/unit/test_project_asset_constraints.py tests/unit/test_project_asset_models.py \
    tests/unit/test_projects_assets_migration.py -q
  ```
  结果：`19 passed`（现有 FastAPI 与 Alembic deprecation warnings）。
- Ruff：受影响 `projects/assets/integrations` 与新增测试通过。
- 迁移：`alembic upgrade head && alembic check` 通过。

## 残余风险

- 普通测试使用 Fake OSS 与 Fake Core；真实 OSS 签名、HEAD 和 Core 网络调用仍需独立 smoke test。
- Core 当前原子接口通常返回 `202`，其最终异步回调/轮询收口属于后续 Task 14，不在本检查点实现。
- 预存未跟踪 `/.superpowers/` 与 `docs/web/docs/Oss.php` 未修改、未暂存、未提交。
