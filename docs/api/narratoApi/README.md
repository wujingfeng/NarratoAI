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
