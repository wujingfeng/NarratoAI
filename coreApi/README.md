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
sudo install -m 0644 "$REPO_ROOT/coreApi/supervisor/core-api-scheduler.conf" /etc/supervisor/conf.d/core-api-scheduler.conf
sudo install -m 0644 "$REPO_ROOT/coreApi/supervisor/core-worker-analysis.conf" /etc/supervisor/conf.d/core-worker-analysis.conf
sudo install -m 0644 "$REPO_ROOT/coreApi/supervisor/core-worker-asr.conf" /etc/supervisor/conf.d/core-worker-asr.conf
sudo install -m 0644 "$REPO_ROOT/coreApi/supervisor/core-worker-tts.conf" /etc/supervisor/conf.d/core-worker-tts.conf
sudo install -m 0644 "$REPO_ROOT/coreApi/supervisor/core-worker-render.conf" /etc/supervisor/conf.d/core-worker-render.conf
```

### ASR Provider

`asr_provider = "local"` 使用部署机的 FunASR-Pack（默认）。切换为
`asr_provider = "volcengine"` 时，填写 `volcengine_asr_appid`、
`volcengine_asr_token` 与 `volcengine_asr_cluster`；Core 会直接把已受 CDN
白名单保护的媒体 URL 提交给火山录音文件识别，并将其 `utterances` 转为统一
SRT Artifact。凭据只写入权限为 `0600` 的 Core 私有 TOML，不得放入
`provider_secrets`、任务快照、数据库或日志。切换后重启 `core-worker-asr`。

### 视频翻译的人声分离（AI MediaKit）

当视频翻译选择“替换人声 / 保留环境音”且没有预先提供
`non_vocal_audio_url` 时，`core-worker-render` 会调用火山 AI MediaKit 的
`POST /api/v1/tools/separate-voice`，以固定 `wav` 输出格式提交源视频公网
URL；随后轮询 `GET /api/v1/tasks/{task_id}`，下载
`result.background_audio_url` 到当前 attempt 的私有工作区后再交给 FFmpeg 混音。

在私有 `core-api.toml` 填写 `mediakit_api_key`，并按需要配置轮询间隔、总
超时和 `mediakit_queue_id`。每次 Core task 的第三方请求均使用稳定、无业务
数据的 `client_token`，任务重试不会重复创建分离任务。Core 只保存第三方的
`task_id`、`request_id` 与固定错误字段（code/param/type）用于排障，不保存
API Key、供应商原始错误消息或带签名的 URL。

保持 `mediakit_media_output_destination` 为空：此时 MediaKit 返回可下载的 HTTPS
临时结果（通常有效 24 小时），Core 会立即保存背景音。当前 Core 尚未集成
VOD/TOS 取回接口；若误配为 `vod://` 或 `tos://`，Core 会在创建第三方任务前
明确失败，避免产生一个注定无法下载的付费任务。该实现不再依赖 Demucs/UVR、
PyTorch 或 `TORCH_HOME`；更新私有配置后重启 `core-worker-render`。

结果下载会严格校验 HTTPS 和 `mediakit_result_allowed_hosts`。默认仅信任
`volces.com` 与 `volcvideo.com` 及其子域，避免供应商响应中的任意 URL 被 Core
Worker 请求。只有经过安全评审的火山自定义下载域才可加入该列表；不要为空或
使用泛化的公共域名。

分离接口返回 WAV。下载大小上限为 300 MiB，与单个源视频上限一致，可覆盖
10 分钟 PCM 音轨，同时仍保持明确的磁盘与网络边界。

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
Supervisor account. Also create writable `/run/narrato-core-api` and
`/var/lib/narrato-core-api` directories for the Celery beat PID and schedule
database. Core runs `core-api-web`, `core-api-scheduler`, `core-worker-analysis`,
`core-worker-asr`, `core-worker-tts`, and `core-worker-render`. Independent
stdout/stderr logs are under `/var/log/narrato-core-api/` and rotate through
Supervisor.

```bash
sudo supervisorctl reread
sudo supervisorctl update
sudo supervisorctl start core-api-web core-api-scheduler core-worker-analysis core-worker-asr core-worker-tts core-worker-render
sudo supervisorctl status
sudo tail -F /var/log/narrato-core-api/web.stderr.log /var/log/narrato-core-api/scheduler.stderr.log /var/log/narrato-core-api/worker-analysis.stderr.log /var/log/narrato-core-api/worker-asr.stderr.log /var/log/narrato-core-api/worker-tts.stderr.log /var/log/narrato-core-api/worker-render.stderr.log

# Stop the scheduler first, then workers, then the web process.
sudo supervisorctl stop core-api-scheduler core-worker-render core-worker-tts core-worker-asr core-worker-analysis core-api-web
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
