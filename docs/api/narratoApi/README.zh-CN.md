# Narrato Business API 部署说明

`docs/api/narratoApi` 是多用户 Business API，负责面向 Web 的 HTTP API、持久化与工作流编排；它不执行 Core 媒体处理。启动前请准备服务账号、PostgreSQL、Redis、可写日志目录与私有 TOML 配置。

## 检出代码验证

在仓库根目录执行以下命令。Python 命令仅做静态读取，不会启动进程，也不会写入系统配置。`nginx -t` 需要已安装 Nginx，并且当前用户有权限创建示例配置声明的临时 PID 与日志文件。

```bash
export REPO_ROOT="$(git rev-parse --show-toplevel)"
python3.12 "$REPO_ROOT/docs/api/narratoApi/scripts/verify-supervisor-config.py"
python3.12 "$REPO_ROOT/docs/api/narratoApi/scripts/verify-nginx-config.py"
nginx -t -c "$REPO_ROOT/docs/api/narratoApi/deploy/nginx.conf"
```

Supervisor 验证器会解析 3 个 Business API 程序及 5 个 Core 程序。每次修改 Origin、TLS 或路径后，都应再次运行 `nginx -t`。

## 私有配置与安装

Supervisor 通过 `NARRATO_API_CONFIG=/etc/narrato-api/narrato-api.toml` 读取 Business API 配置；Core 使用独立的 `/etc/narrato-core-api/core-api.toml`。从仓库中的示例创建两份私有配置，替换所有占位符，设为 `0600`，且不要提交到 Git：

```bash
export REPO_ROOT="$(git rev-parse --show-toplevel)"
sudo install -d -m 0750 /etc/narrato-api /etc/narrato-core-api
sudo install -m 0600 "$REPO_ROOT/docs/api/narratoApi/config.example.toml" /etc/narrato-api/narrato-api.toml
sudo install -m 0600 "$REPO_ROOT/coreApi/config.example.toml" /etc/narrato-core-api/core-api.toml
sudoedit /etc/narrato-api/narrato-api.toml
sudoedit /etc/narrato-core-api/core-api.toml
sudo install -m 0644 "$REPO_ROOT/docs/api/narratoApi/supervisor/narrato-api-web.conf" /etc/supervisor/conf.d/narrato-api-web.conf
sudo install -m 0644 "$REPO_ROOT/docs/api/narratoApi/supervisor/narrato-api-worker.conf" /etc/supervisor/conf.d/narrato-api-worker.conf
sudo install -m 0644 "$REPO_ROOT/docs/api/narratoApi/supervisor/narrato-api-scheduler.conf" /etc/supervisor/conf.d/narrato-api-scheduler.conf
```

Nginx 示例是用于 `nginx -t -c` 的完整配置，不应嵌套包含在另一份主机 `http {}` 配置中。请将其 `upstream`、`map` 与 `server` 指令合并到主机配置，或在替换示例 Origin 并应用 TLS 策略后作为主机主配置使用。Nginx 会将 Business API 反代到 `127.0.0.1:8001`，将 Core 反代到 `127.0.0.1:8002`。

## 数据库迁移与运行期基础数据

发布新版本时先停止 Business Worker 和 Scheduler，再使用实际 PostgreSQL SQLAlchemy DSN 执行 Alembic。当前 `head` 包含视频翻译基础价格、人声分离附加费冻结表及相关工作流迁移；不得只更新代码而跳过迁移。

```bash
cd "$REPO_ROOT/docs/api/narratoApi"
export NARRATO_API_DATABASE_URL='postgresql+psycopg://USER:PASSWORD@HOST:5432/narrato'
.venv/bin/alembic upgrade head
```

随后使用对应数据库的原生 `psql` DSN 执行幂等基础数据脚本，确保产品价格与 `short_drama_narration_v2` 工作流模板存在：

```bash
psql 'postgresql://USER:PASSWORD@HOST:5432/narrato' \
  -v ON_ERROR_STOP=1 \
  -f "$REPO_ROOT/docs/api/narratoApi/sql/bootstrap-runtime-data.postgresql.sql"
```

完成后核对 `alembic_version` 为 `0027_video_translation_voice_replacement_charge`，再启动 Web、Worker 和 Scheduler。该版本冻结视频翻译基础费用与“替换人声/保留环境音”的 10 积分/分钟附加费；回滚应用版本前应使用与目标代码匹配的数据库备份或经过验证的 Alembic 降级流程。

## 启动、日志、停止与回滚

为 Supervisor 服务账号创建 `/var/log/narrato-api` 与 `/var/log/narrato-core-api`。Business 进程包括 `narrato-api-web`、`narrato-api-worker` 和 `narrato-api-scheduler`；各自独立的标准输出和错误日志位于 `/var/log/narrato-api/`，并由 Supervisor 轮转。

```bash
sudo supervisorctl reread
sudo supervisorctl update
sudo supervisorctl start narrato-api-web narrato-api-worker narrato-api-scheduler
sudo supervisorctl status
sudo tail -F /var/log/narrato-api/web.stderr.log /var/log/narrato-api/worker.stderr.log /var/log/narrato-api/scheduler.stderr.log

# 受控停止：保留配置中的 stopasgroup/killasgroup 与 stopwaitsecs。
sudo supervisorctl stop narrato-api-scheduler narrato-api-worker narrato-api-web
```

替换线上 Supervisor/Nginx 文件前，请保留带日期的已部署副本。回滚时停止受影响进程，恢复该副本及与之匹配的私有 TOML 备份，执行 `supervisorctl reread && supervisorctl update`，然后仅启动已恢复进程。恢复 Nginx 前先运行 `nginx -t`。只有当 Business 与 Core 的 API/配置契约发生改变时，才需要同时恢复 Core。

## OSS/CDN Range CORS

签名上传和媒体读取由 OSS/CDN 提供，而非此 Nginx 配置。请为实际 Web Origin 配置 CORS，允许 `GET`、`HEAD` 及 `Range` 请求头，并暴露 `Accept-Ranges`、`Content-Length`、`Content-Range` 与 `ETag`，以支持浏览器定位播放。不要在带凭据的浏览器请求上使用通配符 Origin。

Core 的进程配置和当前队列隔离限制请参见 [Core 部署说明](../../../coreApi/README.zh-CN.md)。

## AI 分析编排与 Outbox 重放

短剧分析依次执行 `subtitle_recognition`（ASR）、`plot_structure`、
`conflict_highlights`、`highlight_scoring`。`plot_structure` 通过 Core 生成一次
包含剧情结构、冲突爽点和高光评分的完整分析报告；后两个节点只投影并复用同一
分析 Artifact，不再重复调用 LLM。每一步仅在其依赖已完成时提交；
Core 回调和轮询都通过同一幂等收口事务写回状态。Celery beat 会按
`workflow_poll_interval_seconds` 轮询运行中的 Core task，并按
`workflow_outbox_replay_interval_seconds` 重放未投递 Outbox。
若 Worker 在认领 Outbox 后异常退出，超过
`workflow_outbox_lease_seconds` 的 `sending` 记录会自动还原为 `pending`，
并在下一次重放周期继续处理；不需要人工执行恢复命令。

Celery beat 还会按 `project_deletion_sweep_interval_seconds` 扫描项目删除任务。
`pending` 与 `retryable_failed` 均会幂等执行；如果项目仍有未过期的 OSS
直传 Policy，则保持 `pending`，待 Policy 过期后再清理对象并收口为 `deleted`。

项目中如已存在状态为 `ready` 的 `.srt` 字幕资产，`subtitle_recognition`
会自动跳过，后续 Qwen 节点直接使用该字幕 URL；无 SRT 时才提交 ASR。

脚本时间线会按约 5 个非空白字符/秒动态匹配口播时长：在不越过下一片段或
源视频结尾时自动延长解说片段；无法延长时记录 `validation_warnings` 供编辑与
诊断，但不再仅因建议字数超限终止整条任务。字段、来源、时间范围、顺序等结构性
错误仍会失败，并在 Core/Business 错误中保留 `reason`、`details` 与有界诊断摘要。

历史 Outbox 默认只做审计 dry-run；以下命令按项目、事件类型、状态和重试次数
筛选，并输出事件 ID、幂等键与原状态。加 `--apply` 才会把选中项重新置为
`pending`，由 worker 处理；重复重放仍使用原幂等键。

```bash
cd "$REPO_ROOT/docs/api/narratoApi"
python -m narrato_api.cli workflows replay-outbox --project-id prj_example --status dead
python -m narrato_api.cli workflows replay-outbox --project-id prj_example --status dead --apply
```
