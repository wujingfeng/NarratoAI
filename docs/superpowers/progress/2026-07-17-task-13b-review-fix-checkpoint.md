# Task 13B 审查修复检查点

- 业务修复：`9bde894 fix: bind uploads to issued policies`
- Policy 签发时预留唯一 `validating` 资产；complete 仅接受相同用户、项目、桶、键和声明的预留对象，重复 complete 不会再插入资产。
- Core 202 使用现有 `GET /api/v1/tasks/{core_task_id}` 查询一次；成功转 `ready`、失败转 `invalid`、未终态保留 `validating`，不引入 Task 14 工作流。
- RED：新增测试证明 content-type、Core 202 查询、未签发对象拒绝均在修复前失败。
- GREEN：`pytest tests/unit/test_oss_post_policy.py tests/unit/test_core_upload_polling.py tests/integration/test_upload_complete.py -q` 为 `11 passed`；Ruff 通过。
- 已知限制：PostgreSQL 项目行锁和可串行化隔离仍需后续真实并发集成测试；SQLite 不提供等价行锁语义。
- 预存 `.superpowers/` 和 `docs/web/docs/Oss.php` 未修改。
