# Narrato Business API deployment

`docs/api/narratoApi` is the multi-user Business API. It owns the Web-facing
HTTP API, persistence, and workflow orchestration; it does not run Core media
processing. Provision the service account, PostgreSQL, Redis, writable log
directories, and private TOML files before starting Supervisor.

## Checkout verification

Run at the repository root. The Python commands are static readers: they do
not start a process or write system configuration. `nginx -t` needs an
installed Nginx binary and permission to create the temporary PID/log files
declared by the example.

```bash
export REPO_ROOT="$(git rev-parse --show-toplevel)"
python3.12 "$REPO_ROOT/docs/api/narratoApi/scripts/verify-supervisor-config.py"
python3.12 "$REPO_ROOT/docs/api/narratoApi/scripts/verify-nginx-config.py"
nginx -t -c "$REPO_ROOT/docs/api/narratoApi/deploy/nginx.conf"
```

The Supervisor verifier parses all three Business API programs and all five
Core programs. Always run `nginx -t` again after adapting origins, TLS, or
paths for a real host.

## Private configuration and installation

Supervisor reads `NARRATO_API_CONFIG=/etc/narrato-api/narrato-api.toml`; Core
uses the distinct `/etc/narrato-core-api/core-api.toml`. Create both from their
checked-in examples, replace every placeholder, set mode `0600`, and never
commit them:

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

The Nginx example is a complete configuration used by `nginx -t -c`; do not
include it inside another host `http {}` block. Merge its `upstream`, `map`,
and `server` directives into the host configuration, or operate it as the
host's main config after replacing example origins and applying TLS policy.
Nginx proxies Business API `127.0.0.1:8001` and Core `127.0.0.1:8002`.

## Database migrations and runtime seed data

Stop the Business Worker and Scheduler before a release, then run Alembic with the real PostgreSQL SQLAlchemy DSN. The current head includes the automatic workflow, Artifact truth gate, and persisted multi-video source ordering; do not deploy the application code without its migrations.

```bash
cd "$REPO_ROOT/docs/api/narratoApi"
export NARRATO_API_DATABASE_URL='postgresql+psycopg://USER:PASSWORD@HOST:5432/narrato'
.venv/bin/alembic upgrade head
```

Then run the idempotent runtime-data script with the matching native `psql` DSN so the product price and `short_drama_narration_v2` workflow template exist:

```bash
psql 'postgresql://USER:PASSWORD@HOST:5432/narrato' \
  -v ON_ERROR_STOP=1 \
  -f "$REPO_ROOT/docs/api/narratoApi/sql/bootstrap-runtime-data.postgresql.sql"
```

Confirm that `alembic_version` is `0036_admin_rbac` before starting the Web, Worker, and Scheduler processes. Earlier revision `0031_normalize_model_generation` normalizes the generic model, play-mode, provider, rule, price, task, asset and output tables; it also evolves the former `ai_video_tasks` into `model_tasks`; revision `0036_admin_rbac` adds the independent management RBAC schema. Model provider URLs/API keys and pricing are configured in PostgreSQL, while provider field/state adaptation remains code-owned. The migration intentionally has no downgrade after it removes legacy JSON configuration; roll back from a database backup matching the target application version.

## AI video provider polling

LLM、图片和视频模型任务状态均由 Business API 收敛，而不是由浏览器调用
供应商刷新接口。必须同时运行 `narrato-api-worker` 与
`narrato-api-scheduler`：Beat 触发 `narrato.ai_video.poll_tasks`，Worker 以
PostgreSQL 行锁和短租约领取到期的 `submitting`/`queued`/`processing`/`finalizing`
任务后直接查询已配置 Provider。图片和视频结果会转存自有 OSS；视频随后调用
Core 媒体探测获取实际时长，再按实际用量结算。

The polling options in the private TOML have safe defaults. Tune the interval
and batch size for provider quota, keep the lease longer than the provider HTTP
timeout, and use the max-error/backoff values to bound transient outages. A
stale `submitting` task is recovered after
`ai_video_submission_recovery_delay_seconds` using its local task id as the
provider idempotency key. Terminal provider failures refund through the existing
idempotent credit ledger exactly once.

## Run, logs, stopping, and rollback

Create `/var/log/narrato-api` and `/var/log/narrato-core-api` with ownership
for the Supervisor service account. Business programs are `narrato-api-web`,
`narrato-api-worker`, and `narrato-api-scheduler`; their independent stdout
and stderr logs are under `/var/log/narrato-api/` and Supervisor rotates them.

```bash
sudo supervisorctl reread
sudo supervisorctl update
sudo supervisorctl start narrato-api-web narrato-api-worker narrato-api-scheduler
sudo supervisorctl status
sudo tail -F /var/log/narrato-api/web.stderr.log /var/log/narrato-api/worker.stderr.log /var/log/narrato-api/scheduler.stderr.log

# Controlled stop: preserve configured stopasgroup/killasgroup and stopwaitsecs.
sudo supervisorctl stop narrato-api-scheduler narrato-api-worker narrato-api-web
```

Before replacing a live Supervisor/Nginx file, retain a dated deployed copy.
To roll back, stop affected programs, restore that copy and its matching
private TOML backup, run `supervisorctl reread && supervisorctl update`, then
start only the restored programs. Run `nginx -t` before reloading restored
Nginx. Restore Core together with Business only if their API/config contract
changed.

## OSS/CDN range CORS

Signed uploads and media reads are served by OSS/CDN, not by this Nginx file.
Configure its CORS rule for the exact Web Origin, `GET` and `HEAD`, and the
`Range` request header. Expose `Accept-Ranges`, `Content-Length`,
`Content-Range`, and `ETag` for browser seeking. Do not use wildcard origin
with credentialed browser calls.

See [the Core deployment guide](../../../coreApi/README.md) for Core programs
and its current queue-isolation limitation.

## Management console API

The independent management API is mounted below `/api/v1/admin`. Run migration
`0036_admin_rbac`, set the private admin bootstrap settings, and then start the
Web process once to provision the initial `Admin` superuser. See
[`docs/admin-api.md`](docs/admin-api.md) for the RBAC, audit and endpoint contract.
