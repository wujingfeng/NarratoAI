# Narrato Core API deployment

`coreApi` is the private media-processing API and worker service. The Business
API is its caller; Core is not the public browser entry point. Provision the
service account, PostgreSQL, Redis, provider credentials, object storage,
writable work root, and log directories before startup.

## Checkout verification

Run these from any checkout location. Both Python commands are static readers;
they do not start Supervisor, Nginx, Celery, or Uvicorn. `nginx -t` requires
the binary and permission to create the example's temporary PID/log files.

```bash
export REPO_ROOT="$(git rev-parse --show-toplevel)"
python3.12 "$REPO_ROOT/docs/api/narratoApi/scripts/verify-supervisor-config.py"
python3.12 "$REPO_ROOT/docs/api/narratoApi/scripts/verify-nginx-config.py"
nginx -t -c "$REPO_ROOT/docs/api/narratoApi/deploy/nginx.conf"
```

## Configuration and Supervisor installation

Core programs use `CORE_API_CONFIG=/etc/narrato-core-api/core-api.toml`; the
Business API uses `/etc/narrato-api/narrato-api.toml`. Build both from their
examples, replace placeholders, protect them with mode `0600`, and never
commit them.

```bash
export REPO_ROOT="$(git rev-parse --show-toplevel)"
sudo install -d -m 0750 /etc/narrato-api /etc/narrato-core-api
sudo install -m 0600 "$REPO_ROOT/coreApi/config.example.toml" /etc/narrato-core-api/core-api.toml
sudo install -m 0600 "$REPO_ROOT/docs/api/narratoApi/config.example.toml" /etc/narrato-api/narrato-api.toml
sudoedit /etc/narrato-core-api/core-api.toml
sudoedit /etc/narrato-api/narrato-api.toml
sudo install -m 0644 "$REPO_ROOT/coreApi/supervisor/core-api-web.conf" /etc/supervisor/conf.d/core-api-web.conf
sudo install -m 0644 "$REPO_ROOT/coreApi/supervisor/core-worker-analysis.conf" /etc/supervisor/conf.d/core-worker-analysis.conf
sudo install -m 0644 "$REPO_ROOT/coreApi/supervisor/core-worker-asr.conf" /etc/supervisor/conf.d/core-worker-asr.conf
sudo install -m 0644 "$REPO_ROOT/coreApi/supervisor/core-worker-tts.conf" /etc/supervisor/conf.d/core-worker-tts.conf
sudo install -m 0644 "$REPO_ROOT/coreApi/supervisor/core-worker-render.conf" /etc/supervisor/conf.d/core-worker-render.conf
```

Definitions use `/srv/narrato/NarratoAI` and set `PYTHONPATH` to the repository
root. If deployed elsewhere, change every Supervisor `directory`, `command`,
and `PYTHONPATH` consistently before rerunning the Supervisor verifier.

The shared Nginx example is
`$REPO_ROOT/docs/api/narratoApi/deploy/nginx.conf`. It proxies Business at
`127.0.0.1:8001` and Core at `127.0.0.1:8002`, disables SSE buffering, and has
a CORS allowlist. It is a complete config for `nginx -t -c`; merge its `http`
children into an existing host config instead of including it inside another
`http {}` block.

## Run, inspect, stop, and roll back

Create `/var/log/narrato-core-api` and `/var/log/narrato-api` for the
Supervisor account. Core runs `core-api-web`, `core-worker-analysis`,
`core-worker-asr`, `core-worker-tts`, and `core-worker-render`. Independent
stdout/stderr logs are under `/var/log/narrato-core-api/` and rotate through
Supervisor.

```bash
sudo supervisorctl reread
sudo supervisorctl update
sudo supervisorctl start core-api-web core-worker-analysis core-worker-asr core-worker-tts core-worker-render
sudo supervisorctl status
sudo tail -F /var/log/narrato-core-api/web.stderr.log /var/log/narrato-core-api/worker-analysis.stderr.log /var/log/narrato-core-api/worker-asr.stderr.log /var/log/narrato-core-api/worker-tts.stderr.log /var/log/narrato-core-api/worker-render.stderr.log

# Stop workers before the web process; keep stopasgroup/killasgroup and stopwaitsecs.
sudo supervisorctl stop core-worker-render core-worker-tts core-worker-asr core-worker-analysis core-api-web
```

For rollback, stop only affected programs, restore the retained Supervisor
file(s) and matching private TOML backup, then run `supervisorctl reread && supervisorctl update` and start restored programs. Run `nginx -t` before
reloading reverted Nginx. Restore both services only when their
version/configuration contract changed.

## Current Celery queue limitation

The four Core worker names are capacity labels, not true queue isolation.
`core_api.celery_app` currently sends durable wake tasks to the single
`narrato.core.default` queue, so every role-named worker consumes that same
queue. This increases shared capacity but cannot guarantee a task reaches its
matching role.

True per-role queue isolation needs future Celery task-routing work: separate
queues and `task_routes`, followed by producer, consumer, retry, and
dead-letter changes. Do not change Supervisor commands to unimplemented role
queue names before that work lands; the current default queue's tasks would be
stranded.

## OSS/CDN range CORS

Configure OSS/CDN itself, not just Nginx, for the exact deployed Web Origin.
Allow `GET` and `HEAD` with the `Range` request header and expose
`Accept-Ranges`, `Content-Length`, `Content-Range`, and `ETag`. This supports
browser range playback/seeking; retain a narrow origin allowlist instead of
wildcard credentialed CORS.
