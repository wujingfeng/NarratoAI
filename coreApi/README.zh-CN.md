# Narrato Core API 部署说明

`coreApi` 是私有媒体处理 API 与 Worker 服务。业务 API 调用 Core；Core 不是面向浏览器的公共入口。启动前请准备服务账号、PostgreSQL、Redis、供应商凭据、对象存储、可写工作目录与日志目录。

## 检出代码验证

以下命令可从任意检出目录执行。两个 Python 命令只做静态读取，不会启动 Supervisor、Nginx、Celery 或 Uvicorn。`nginx -t` 需要已安装 Nginx，并且当前用户有权限创建示例配置中的临时 PID 与日志文件。

```bash
export REPO_ROOT="$(git rev-parse --show-toplevel)"
python3.12 "$REPO_ROOT/docs/api/narratoApi/scripts/verify-supervisor-config.py"
python3.12 "$REPO_ROOT/docs/api/narratoApi/scripts/verify-nginx-config.py"
nginx -t -c "$REPO_ROOT/docs/api/narratoApi/deploy/nginx.conf"
```

## 配置与 Supervisor 安装

Core 进程使用 `CORE_API_CONFIG=/etc/narrato-core-api/core-api.toml`；Business API 使用 `/etc/narrato-api/narrato-api.toml`。请从示例文件创建两份私有配置，替换所有占位符，设为 `0600`，且不要提交到 Git。

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

配置默认使用 `/srv/narrato/NarratoAI`，并将 `PYTHONPATH` 设为仓库根目录。若部署在其他位置，请一致修改每个 Supervisor 配置中的 `directory`、`command` 与 `PYTHONPATH`，然后重新运行 Supervisor 验证器。

共享 Nginx 示例位于 `$REPO_ROOT/docs/api/narratoApi/deploy/nginx.conf`。它将 Business API 反代到 `127.0.0.1:8001`，将 Core 反代到 `127.0.0.1:8002`，禁用 SSE 缓冲并配置 CORS 白名单。该文件是可直接传给 `nginx -t -c` 的完整配置；合并到既有主机配置时，应合并其 `http` 子项，而不是嵌套到另一个 `http {}` 中。

### 视频翻译人声分离

默认的“替换人声”会保留环境声、动作音效和背景声，因此渲染机必须安装
Demucs/UVR wrapper。分离运行时与 Core Python 3.12 环境隔离，避免把 Torch
加入 Web/Worker 的基础依赖：

```bash
sudo install -d -m 0755 /opt/narrato/audio-separator
sudo uv venv /opt/narrato/audio-separator/venv --python 3.11
sudo UV_CACHE_DIR=/var/cache/narrato-uv uv pip install \
  --python /opt/narrato/audio-separator/venv/bin/python \
  demucs==4.0.1 torchcodec
```

在 Core 私有 TOML 中配置单独参数数组（不要写 shell 命令字符串）：

```toml
audio_separation_command = [
  "/opt/narrato/audio-separator/venv/bin/python",
  "/srv/narrato/NarratoAI/coreApi/scripts/separate_non_vocal.py",
  "--input", "{input}",
  "--output", "{output}",
]
```

首次运行会下载模型；生产应保证 Supervisor 账号的模型缓存目录可写并提前
预热。未配置、超时或分离失败时，Core 会让 `video_render` 节点明确失败并可从
该节点重试，不会退化为“完整原声叠加译音”或把所有环境声静音。

## 启动、检查、停止与回滚

为 Supervisor 服务账号创建 `/var/log/narrato-core-api` 与 `/var/log/narrato-api`，并创建可写的 `/run/narrato-core-api` 与 `/var/lib/narrato-core-api`，分别保存 Celery beat PID 和调度数据库。Core 运行 `core-api-web`、`core-api-scheduler`、`core-worker-analysis`、`core-worker-asr`、`core-worker-tts` 和 `core-worker-render`。标准输出与错误日志分别写入 `/var/log/narrato-core-api/`，并由 Supervisor 轮转。

```bash
sudo supervisorctl reread
sudo supervisorctl update
sudo supervisorctl start core-api-web core-api-scheduler core-worker-analysis core-worker-asr core-worker-tts core-worker-render
sudo supervisorctl status
sudo tail -F /var/log/narrato-core-api/web.stderr.log /var/log/narrato-core-api/scheduler.stderr.log /var/log/narrato-core-api/worker-analysis.stderr.log /var/log/narrato-core-api/worker-asr.stderr.log /var/log/narrato-core-api/worker-tts.stderr.log /var/log/narrato-core-api/worker-render.stderr.log

# 先停止 Scheduler，再停止 Worker，最后停止 Web。
sudo supervisorctl stop core-api-scheduler core-worker-render core-worker-tts core-worker-asr core-worker-analysis core-api-web
```

回滚时，只停止受影响进程，恢复保留的 Supervisor 文件和对应私有 TOML 备份，然后执行 `supervisorctl reread && supervisorctl update` 并启动已恢复进程。只有当两个服务的 API/配置契约发生变化时，才同时回滚两者。回滚 Nginx 前先执行 `nginx -t`。

## 当前 Celery 队列限制

四个 Core Worker 名称目前是容量标签，不是真正的队列隔离。`core_api.celery_app` 将持久化唤醒任务发送到唯一的 `narrato.core.default` 队列，因此所有按角色命名的 Worker 都会消费同一队列。这会增加共享处理能力，但不能保证某类任务只由对应角色 Worker 执行。

真正的按角色队列隔离需要后续补充独立队列与 `task_routes`，并同步更新生产者、消费者、重试与死信处理。在该能力落地前，不要把 Supervisor 命令改为未实现的角色队列名，否则默认队列任务会被搁置。

## OSS/CDN Range CORS

请在 OSS/CDN 本身配置 CORS，而不只依赖 Nginx。针对实际部署的 Web Origin，允许 `GET`、`HEAD` 及 `Range` 请求头，并暴露 `Accept-Ranges`、`Content-Length`、`Content-Range` 与 `ETag`。这支持浏览器 Range 播放和定位；应保留严格的 Origin 白名单，而非在携带凭据时使用通配符。

## 新增用户

#### 1. 发送验证码

#### 2. 注册
curl -i -X POST "http://127.0.0.1:8001/api/v1/auth/register" \
  -H "Content-Type: application/json" \
  -d '{
    "email":"1163377596@qq.com",
    "password":"Qwer12345678",
    "verification_code":"558579"
  }'
