# NarratoAI 多用户 API 平台恢复摘要

> 生成日期：2026-07-17；事实来源仅为当前 worktree、Git、进度日志与 SDD 工件。

## 当前 HEAD 与分支

- Worktree：`/private/tmp/NarratoAI-narrato-api-platform`
- Branch：`codex/narrato-api-platform`
- HEAD：`ae3093e feat: add email auth and single session tokens`

## 已完整完成的 Task

| 范围 | 状态 | Commit |
| --- | --- | --- |
| Task 1 基线与隔离 | 完成 | 无提交（计划规定） |
| Task 2 短剧纯服务/媒体探测 | 完成 | `721756e` |
| Task 3 工作区隔离 | 完成 | `05c81e2` |
| Task 4 coreApi 骨架 | 完成 | `557e96c` |
| Task 5 Core Task/Attempt/Outbox | 完成 | `6990308` |
| Task 6 能力目录 | 完成 | `ae608fb` |
| Task 7 OSS/媒体/ASR | 完成 | `6e9fca1` |
| Task 8 分析/文案/校验 | 完成 | `de9b075` |
| Task 9 TTS/字幕/渲染/剪映 Manifest | 完成 | `de28121` |
| Gate A Core 独立运行 | 通过 | `bbf6e30` |
| Task 10 narratoApi 骨架 | 完成 | `f016815` |

## 当前未完成 Task

- **Task 11：邮箱账户与 Redis 单点 Token**。基线提交为 `ae3093e`，已历经 R1–R4 审查；R4 仍为 FAIL（0 Critical、2 Important）。
- R4 待关闭问题：Redis 时间应作为验证码租约的事实源；SMTP 整个发送期必须维持/续租 owner，禁止旧 generation 在新 generation 后迟到投递。
- 后续计划 Task 12–20 尚未开始；Gate B/C/D 尚未达到前置条件。

## 停止时遗留未提交改动归属

- Task 11 R4 修复中的产品与测试改动：`api/dependencies.py`、`auth/redis_store.py`、`auth/tasks.py`、`config.py`、`integrations/mail_client.py`、三份 Task 11 测试。
- 未跟踪 `.superpowers/` 是既有 SDD brief/review/progress 工件；不得当作产品提交物。
- 未跟踪 `docs/web/docs/Oss.php` 为既有非 Task 11 文件；不得覆盖、删除或混入 Task 11 提交。

## 已通过的关键测试证据

- Task 1 旧能力基线：`86 passed, 4 warnings`。
- Gate A：已记录 Core/旧项目回归、迁移、发布包与审查通过，提交 `bbf6e30`。
- Task 10：已在进度日志和 SDD ledger 中标为完成，提交 `f016815`。
- Task 11 在 `ae3093e` 时，R4 记录：narratoApi 全量 `78 passed, 6 skipped, 1 warning`；真实 Redis 定向 `37 passed, 1 warning`；Ruff、Mypy、diff-check 通过。
- 上述 Task 11 证据早于当前未提交 R4 修复，不证明当前工作树通过。

## 下一步

1. 仅审阅 Task 11 相关差异与 R4 相关设计/计划行，运行当前新增测试确认 RED/GREEN 状态。
2. 完成并验证 R4 两项修复；更新 Task 11 report/progress，完成一次统一需求复核、代码审查与 Gate 前测试后独立提交。
3. 继续 Task 12–15，随后执行 Gate B。

## 尚未通过的 Gate

- Gate B：未开始（依赖 Task 11–15）。
- Gate C：未开始（依赖 Task 16–18）。
- Gate D：未开始（依赖 Task 19–20）。

## 已知风险

- Task 11 当前未提交改动未经本轮新鲜验证，且 R4 证实验证码发送并发/时钟边界仍存在需求缺口。
- PostgreSQL 多连接/行锁与真实 SMTP/Redis/Celery 端到端验证仍需在相应 Gate 执行；真实供应商 Smoke Test 为可选外部验证，不得提前宣称通过。
- 原 worktree 留有用户/前序 Agent 文件，恢复过程不得 `reset`、`restore`、`clean`、删除或覆盖。
