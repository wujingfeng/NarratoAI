#!/usr/bin/env bash
# 本地 Core + Business 进程管理。每个进程在所属目录启动，并显式使用对应配置文件。
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CORE_DIR="$ROOT_DIR/coreApi"
BUSINESS_DIR="$ROOT_DIR/docs/api/narratoApi"
RUNTIME_DIR="$ROOT_DIR/runtime/local-services"
PID_DIR="$RUNTIME_DIR/pids"
LOG_DIR="$RUNTIME_DIR/logs"

mkdir -p "$PID_DIR" "$LOG_DIR"

usage() {
  cat <<'EOF'
用法：scripts/manage-local-services.sh <start|stop|restart|status|logs> [all|core|business]

示例：
  ./scripts/manage-local-services.sh start all
  # restart 会按命令行查找并强制停止旧进程；8001/8002 被占用时会先释放端口。
  ./scripts/manage-local-services.sh restart business
  ./scripts/manage-local-services.sh status
  ./scripts/manage-local-services.sh logs core-worker-asr
EOF
}

require_config() {
  local service_dir="$1"
  [[ -f "$service_dir/config.toml" ]] || {
    echo "缺少配置文件：$service_dir/config.toml" >&2
    exit 1
  }
}

pid_file() { echo "$PID_DIR/$1.pid"; }
log_file() { echo "$LOG_DIR/$1.log"; }

process_pattern() {
  case "$1" in
    narrato-api-web) echo "$BUSINESS_DIR/.venv/bin/uvicorn narrato_api.main:create_app.*--port 8001" ;;
    narrato-api-worker) echo "$BUSINESS_DIR/.venv/bin/celery -A narrato_api.celery_app:celery_app worker" ;;
    narrato-api-scheduler) echo "$BUSINESS_DIR/.venv/bin/celery -A narrato_api.celery_app:celery_app beat" ;;
    core-api-web) echo "$CORE_DIR/.venv/bin/uvicorn core_api.main:create_app.*--port 8002" ;;
    core-api-scheduler) echo "$CORE_DIR/.venv/bin/celery -A core_api.celery_app:celery_app beat" ;;
    core-worker-analysis) echo "$CORE_DIR/.venv/bin/celery -A core_api.celery_app:celery_app worker.*--hostname=core-analysis@" ;;
    core-worker-asr) echo "$CORE_DIR/.venv/bin/celery -A core_api.celery_app:celery_app worker.*--hostname=core-asr@" ;;
    core-worker-tts) echo "$CORE_DIR/.venv/bin/celery -A core_api.celery_app:celery_app worker.*--hostname=core-tts@" ;;
    core-worker-render) echo "$CORE_DIR/.venv/bin/celery -A core_api.celery_app:celery_app worker.*--hostname=core-render@" ;;
    *) return 1 ;;
  esac
}

listen_port() {
  case "$1" in
    narrato-api-web) echo 8001 ;;
    core-api-web) echo 8002 ;;
    *) return 1 ;;
  esac
}

is_service_master_pid() {
  local name="$1"
  local pid="$2"
  local command parent_pid

  case "$name" in
    *-worker|*-scheduler)
      # Celery pool child 会继承 master 的完整 argv，单纯 pgrep 会把所有
      # ForkPoolWorker 误当成独立服务。只控制 nohup 后由 init 接管的 master。
      command="$(ps -p "$pid" -o command= 2>/dev/null || true)"
      parent_pid="$(ps -p "$pid" -o ppid= 2>/dev/null | tr -d '[:space:]')"
      [[ -n "$command" && "$parent_pid" == "1" ]] || return 1
      [[ "$command" != *"ForkPoolWorker"* && "$command" != *"SpawnPoolWorker"* && "$command" != *"celeryd:"* ]]
      ;;
    *)
      return 0
      ;;
  esac
}

process_pids() {
  local name="$1"
  local pattern pid

  # 不信任 PID 文件：PID 可复用且 Celery 的 pool 子进程会继承 master argv。
  # 每次均按完整命令行发现服务主进程。
  pattern="$(process_pattern "$name")"
  while IFS= read -r pid; do
    [[ "$pid" =~ ^[0-9]+$ ]] || continue
    is_service_master_pid "$name" "$pid" && echo "$pid"
  done < <(pgrep -f "$pattern" 2>/dev/null || true)
}

running_pids() {
  process_pids "$1" | awk '/^[0-9]+$/ && !seen[$0]++'
}

is_running() {
  [[ -n "$(running_pids "$1")" ]]
}

force_release_port() {
  local port="$1"
  local owner="$2"
  local pid elapsed=0
  local pids=()

  command -v lsof >/dev/null 2>&1 || {
    echo "无法检查端口 ${port}：系统未安装 lsof" >&2
    return 1
  }
  while IFS= read -r pid; do
    [[ "$pid" =~ ^[0-9]+$ ]] && pids+=("$pid")
  done < <(lsof -nP -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null | awk '!seen[$0]++')
  ((${#pids[@]})) || return 0

  echo "${owner} 启动端口 ${port} 已被 PID ${pids[*]} 占用，正在强制释放"
  kill -TERM "${pids[@]}" 2>/dev/null || true
  while ((elapsed < 5)); do
    local alive=0
    for pid in "${pids[@]}"; do
      kill -0 "$pid" 2>/dev/null && alive=1
    done
    ((alive == 0)) && break
    sleep 1
    elapsed=$((elapsed + 1))
  done
  for pid in "${pids[@]}"; do
    if kill -0 "$pid" 2>/dev/null; then
      echo "端口 ${port} 的 PID ${pid} 未退出，发送 SIGKILL"
      kill -KILL "$pid" 2>/dev/null || true
    fi
  done
}

start_process() {
  local name="$1"
  local service_dir="$2"
  local config_env="$3"
  local config_path="$service_dir/config.toml"
  local port existing_pids started_pid
  shift 3

  require_config "$service_dir"
  if is_running "$name"; then
    existing_pids="$(running_pids "$name" | paste -sd, -)"
    echo "${existing_pids%%,*}" >"$(pid_file "$name")"
    echo "${name} 已运行，PID ${existing_pids}"
    return
  fi
  rm -f "$(pid_file "$name")"
  if port="$(listen_port "$name" 2>/dev/null)"; then
    force_release_port "$port" "$name"
  fi
  (
    cd "$service_dir"
    # 配置加载器会优先读取 *_CONFIG 环境变量；覆盖继承值，避免 Core 与
    # Business 在同一终端或 IDE 中启动时误读对方的 config.toml。
    # 每个 API 包均位于各自 service_dir 下（coreApi/core_api、
    # docs/api/narratoApi/narrato_api）；不能只把仓库根目录放入模块搜索路径。
    env -u CORE_API_CONFIG -u NARRATO_API_CONFIG \
      "$config_env=$config_path" \
      PYTHONPATH="$service_dir${PYTHONPATH:+:$PYTHONPATH}" PYTHONUNBUFFERED=1 \
      nohup "$@" >"$(log_file "$name")" 2>&1 < /dev/null &
    echo "$!" >"$(pid_file "$name")"
  )
  started_pid="$(cat "$(pid_file "$name")")"
  sleep 1
  if ! kill -0 "$started_pid" 2>/dev/null; then
    echo "${name} 启动失败，最近日志如下：" >&2
    tail -n 30 "$(log_file "$name")" >&2 || true
    return 1
  fi
  echo "已启动 ${name}，PID ${started_pid}，日志：$(log_file "$name")"
}

stop_process() {
  local name="$1"
  local pid_path pid elapsed=0 alive
  local pids=()
  pid_path="$(pid_file "$name")"
  while IFS= read -r pid; do
    [[ "$pid" =~ ^[0-9]+$ ]] && pids+=("$pid")
  done < <(running_pids "$name")
  if ((${#pids[@]} == 0)); then
    rm -f "$pid_path"
    echo "${name} 未启动"
    return
  fi
  echo "正在停止 ${name}，PID ${pids[*]}"
  kill -TERM "${pids[@]}" 2>/dev/null || true
  while [[ "$elapsed" -lt 20 ]]; do
    alive=0
    for pid in "${pids[@]}"; do
      kill -0 "$pid" 2>/dev/null && alive=1
    done
    [[ "$alive" -eq 0 ]] && break
    sleep 1
    elapsed=$((elapsed + 1))
  done
  for pid in "${pids[@]}"; do
    if kill -0 "$pid" 2>/dev/null; then
      echo "${name} 的 PID ${pid} 未在 20 秒内退出，发送 SIGKILL"
      kill -KILL "$pid" 2>/dev/null || true
    fi
  done
  rm -f "$pid_path"
  echo "已停止 ${name}"
}

status_process() {
  local name="$1" pids
  if is_running "$name"; then
    pids="$(running_pids "$name" | paste -sd, -)"
    echo "RUNNING  ${name} (PID ${pids})"
  else
    echo "STOPPED  ${name}"
  fi
}

start_business() {
  start_process narrato-api-web "$BUSINESS_DIR" \
    NARRATO_API_CONFIG \
    "$BUSINESS_DIR/.venv/bin/uvicorn" narrato_api.main:create_app --factory --host 127.0.0.1 --port 8001
  start_process narrato-api-worker "$BUSINESS_DIR" \
    NARRATO_API_CONFIG \
    "$BUSINESS_DIR/.venv/bin/celery" -A narrato_api.celery_app:celery_app worker --loglevel=INFO --queues=narrato.business.default
  start_process narrato-api-scheduler "$BUSINESS_DIR" \
    NARRATO_API_CONFIG \
    "$BUSINESS_DIR/.venv/bin/celery" -A narrato_api.celery_app:celery_app beat --loglevel=INFO \
    --pidfile="$RUNTIME_DIR/business-scheduler.pid" --schedule="$RUNTIME_DIR/business-celerybeat-schedule"
}

stop_business() {
  stop_process narrato-api-scheduler
  stop_process narrato-api-worker
  stop_process narrato-api-web
}

start_core() {
  start_process core-api-web "$CORE_DIR" \
    CORE_API_CONFIG \
    "$CORE_DIR/.venv/bin/uvicorn" core_api.main:create_app --factory --host 127.0.0.1 --port 8002
  start_process core-api-scheduler "$CORE_DIR" \
    CORE_API_CONFIG \
    "$CORE_DIR/.venv/bin/celery" -A core_api.celery_app:celery_app beat --loglevel=INFO \
    --pidfile="$RUNTIME_DIR/core-scheduler.pid" --schedule="$RUNTIME_DIR/core-celerybeat-schedule"
  start_process core-worker-analysis "$CORE_DIR" \
    CORE_API_CONFIG \
    "$CORE_DIR/.venv/bin/celery" -A core_api.celery_app:celery_app worker --loglevel=INFO --queues=narrato.core.default --hostname=core-analysis@%h --concurrency=2
  start_process core-worker-asr "$CORE_DIR" \
    CORE_API_CONFIG \
    "$CORE_DIR/.venv/bin/celery" -A core_api.celery_app:celery_app worker --loglevel=INFO --queues=narrato.core.default --hostname=core-asr@%h --concurrency=1
  start_process core-worker-tts "$CORE_DIR" \
    CORE_API_CONFIG \
    "$CORE_DIR/.venv/bin/celery" -A core_api.celery_app:celery_app worker --loglevel=INFO --queues=narrato.core.default --hostname=core-tts@%h --concurrency=2
  start_process core-worker-render "$CORE_DIR" \
    CORE_API_CONFIG \
    "$CORE_DIR/.venv/bin/celery" -A core_api.celery_app:celery_app worker --loglevel=INFO --queues=narrato.core.default --hostname=core-render@%h --concurrency=1
}

stop_core() {
  stop_process core-api-scheduler
  stop_process core-worker-render
  stop_process core-worker-tts
  stop_process core-worker-asr
  stop_process core-worker-analysis
  stop_process core-api-web
}

status_all() {
  for name in narrato-api-web narrato-api-worker narrato-api-scheduler \
    core-api-web core-api-scheduler core-worker-analysis core-worker-asr core-worker-tts core-worker-render; do
    status_process "$name"
  done
}

action="${1:-}"
target="${2:-all}"
case "$action:$target" in
  start:all) start_business; start_core ;;
  start:business) start_business ;;
  start:core) start_core ;;
  stop:all) stop_business; stop_core ;;
  stop:business) stop_business ;;
  stop:core) stop_core ;;
  restart:all) stop_business; stop_core; start_business; start_core ;;
  restart:business) stop_business; start_business ;;
  restart:core) stop_core; start_core ;;
  status:all|status:business|status:core) status_all ;;
  logs:*)
    [[ -n "${2:-}" && "$target" != "all" ]] || { usage; exit 1; }
    tail -F "$(log_file "$target")"
    ;;
  *) usage; exit 1 ;;
esac
