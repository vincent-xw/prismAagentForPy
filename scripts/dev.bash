#!/usr/bin/env bash
# 本地开发启动器：准备前后端环境，迁移数据库，并共同管理两个开发进程。
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
UI_DIR="$ROOT_DIR/ui"
BACKEND_HOST="127.0.0.1"
BACKEND_PORT="${BACKEND_PORT:-8000}"
UI_HOST="127.0.0.1"
UI_PORT="${UI_PORT:-3000}"
BACKEND_URL="http://${BACKEND_HOST}:${BACKEND_PORT}"
UI_URL="http://${UI_HOST}:${UI_PORT}"
BACKEND_ENV_FILE="$BACKEND_DIR/.env"
UI_ENV_FILE="$UI_DIR/.env"
BACKEND_PID=""
UI_PID=""

log() {
  printf '[dev] %s\n' "$*"
}

die() {
  printf '[dev] 错误：%s\n' "$*" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || die "缺少命令 $1，请先安装后重试。"
}

# 从当前进程环境或 .env 文件读取配置；环境变量优先，与后端配置行为一致。
read_setting() {
  local key="$1"
  local file="$2"
  local value=""

  if [[ -n "${!key:-}" ]]; then
    value="${!key}"
  elif [[ -f "$file" ]]; then
    value="$(awk -F= -v wanted="$key" '$1 == wanted { sub(/^[^=]*=/, ""); print; exit }' "$file")"
  fi

  printf '%s' "$value"
}

ensure_env_files() {
  local created=0

  if [[ ! -f "$BACKEND_ENV_FILE" ]]; then
    cat >"$BACKEND_ENV_FILE" <<'EOF'
# 本地 DEV 最小配置；其余参数使用后端默认值，完整选项见 .env.example。
PRISM_AGENT_KIT_API_TOKEN=
PRISM_AGENT_KIT_MODEL_BASE_URL=
PRISM_AGENT_KIT_MODEL_API_KEY=
PRISM_AGENT_KIT_MODEL_NAME=
PRISM_AGENT_KIT_MODEL_CONTEXT_WINDOW=
PRISM_AGENT_KIT_MODEL_MAX_OUTPUT_TOKENS=
PRISM_AGENT_KIT_MODEL_TOKEN_ENCODING=
EOF
    created=1
  fi
  if [[ ! -f "$UI_ENV_FILE" ]]; then
    cp "$UI_DIR/.env.example" "$UI_ENV_FILE"
    created=1
  fi

  if [[ "$created" -eq 1 ]]; then
    log "已从 .env.example 创建本地环境文件。"
  fi
}

validate_backend_settings() {
  local missing=()
  local key
  local value

  for key in \
    PRISM_AGENT_KIT_API_TOKEN \
    PRISM_AGENT_KIT_MODEL_NAME \
    PRISM_AGENT_KIT_MODEL_API_KEY \
    PRISM_AGENT_KIT_MODEL_CONTEXT_WINDOW \
    PRISM_AGENT_KIT_MODEL_MAX_OUTPUT_TOKENS \
    PRISM_AGENT_KIT_MODEL_TOKEN_ENCODING; do
    value="$(read_setting "$key" "$BACKEND_ENV_FILE")"
    if [[ -z "${value//[[:space:]]/}" ]]; then
      missing+=("$key")
    fi
  done

  if [[ "${#missing[@]}" -gt 0 ]]; then
    printf '[dev] 后端配置尚未完成，请在 %s 中填写：\n' "$BACKEND_ENV_FILE" >&2
    printf '  - %s\n' "${missing[@]}" >&2
    printf '[dev] 如使用 DeepSeek 等 OpenAI-compatible 服务，请同时填写 PRISM_AGENT_KIT_MODEL_BASE_URL。\n' >&2
    exit 1
  fi
}

ensure_port_available() {
  local port="$1"
  local name="$2"

  if command -v lsof >/dev/null 2>&1 && lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
    die "$name 端口 $port 已被占用，请停止占用进程或通过环境变量指定其他端口。"
  fi
}

install_dependencies() {
  if [[ "${SKIP_DEPENDENCY_INSTALL:-0}" == "1" ]]; then
    log "按 SKIP_DEPENDENCY_INSTALL=1 跳过依赖同步。"
    return
  fi

  log "同步 Python 依赖..."
  (cd "$BACKEND_DIR" && uv sync --quiet)

  log "检查 UI 依赖..."
  (cd "$UI_DIR" && pnpm install --frozen-lockfile --prefer-offline)
}

apply_migrations() {
  log "应用 SQLite 数据库迁移..."
  (cd "$BACKEND_DIR" && uv run alembic upgrade head)
}

wait_for_http() {
  local name="$1"
  local url="$2"
  local pid="$3"
  local attempts=120
  local count=0

  while [[ "$count" -lt "$attempts" ]]; do
    if curl -fsS --max-time 2 "$url" >/dev/null 2>&1; then
      return 0
    fi
    if ! kill -0 "$pid" 2>/dev/null; then
      printf '[dev] %s 进程提前退出。\n' "$name" >&2
      return 1
    fi
    sleep 0.5
    count=$((count + 1))
  done

  printf '[dev] %s 就绪检查超时：%s\n' "$name" "$url" >&2
  return 1
}

# 先递归结束子进程，确保 pnpm 和 Uvicorn reloader 不会留下孤儿进程。
terminate_tree() {
  local pid="$1"
  local child

  if [[ -z "$pid" ]] || ! kill -0 "$pid" 2>/dev/null; then
    return
  fi

  while IFS= read -r child; do
    if [[ -n "$child" ]]; then
      terminate_tree "$child"
    fi
  done < <(pgrep -P "$pid" 2>/dev/null || true)

  kill -TERM "$pid" 2>/dev/null || true
}

cleanup() {
  local status=$?

  trap - EXIT INT TERM
  if [[ -n "$UI_PID" ]]; then
    terminate_tree "$UI_PID"
    wait "$UI_PID" 2>/dev/null || true
  fi
  if [[ -n "$BACKEND_PID" ]]; then
    terminate_tree "$BACKEND_PID"
    wait "$BACKEND_PID" 2>/dev/null || true
  fi
  exit "$status"
}

trap cleanup EXIT INT TERM

if [[ "${1:-}" == "--help" ]]; then
  cat <<'EOF'
用法: ./scripts/dev.sh

可选环境变量:
  BACKEND_PORT              后端端口，默认 8000
  UI_PORT                   前端端口，默认 3000
  SKIP_DEPENDENCY_INSTALL   设为 1 时跳过 uv sync 与 pnpm install

首次运行会自动创建 backend/.env 与 ui/.env。模型凭据和本地 API Token
需要手动填写到 backend/.env；UI 连接时使用同一个 API Token。
EOF
  exit 0
fi

require_command uv
require_command pnpm
require_command node
require_command curl
require_command pgrep

ensure_env_files
validate_backend_settings
ensure_port_available "$BACKEND_PORT" "后端"
ensure_port_available "$UI_PORT" "UI"

# 自定义 API 前缀时，健康检查与 Vite 代理必须使用同一个值。
API_PREFIX="$(read_setting PRISM_AGENT_KIT_API_PREFIX "$BACKEND_ENV_FILE")"
API_PREFIX="${API_PREFIX:-/api/v1}"
[[ "$API_PREFIX" == /* ]] || API_PREFIX="/$API_PREFIX"
API_PREFIX="${API_PREFIX%/}"
HEALTH_URL="${BACKEND_URL}${API_PREFIX}/health"

install_dependencies
apply_migrations

log "启动 FastAPI：$BACKEND_URL"
(
  cd "$BACKEND_DIR"
  exec uv run uvicorn prism_agent_kit.main:app \
    --host "$BACKEND_HOST" \
    --port "$BACKEND_PORT" \
    --reload
) &
BACKEND_PID=$!

if ! wait_for_http "Backend" "$HEALTH_URL" "$BACKEND_PID"; then
  die "后端未能通过健康检查，请查看上方日志。"
fi
log "Backend 已就绪。"

log "启动 Vite：$UI_URL"
(
  cd "$UI_DIR"
  export PRISM_UI_API_TARGET="$BACKEND_URL"
  export VITE_API_BASE_PATH="$API_PREFIX"
  exec pnpm run dev --host "$UI_HOST" --port "$UI_PORT"
) &
UI_PID=$!

if ! wait_for_http "UI" "$UI_URL/" "$UI_PID"; then
  die "UI 未能启动，请查看上方日志。"
fi

printf '\n'
log "本地开发环境已启动。"
printf '[dev] UI:          %s\n' "$UI_URL"
printf '[dev] Backend API: %s\n' "$BACKEND_URL"
printf '[dev] API Docs:    %s/docs\n' "$BACKEND_URL"
printf '[dev] Health:      %s\n' "$HEALTH_URL"
printf '[dev] 在 UI 中连接时，请使用 backend/.env 里的 PRISM_AGENT_KIT_API_TOKEN。\n'
printf '[dev] 按 Ctrl+C 同时停止前后端。\n\n'

while kill -0 "$BACKEND_PID" 2>/dev/null && kill -0 "$UI_PID" 2>/dev/null; do
  sleep 1
done

if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
  wait "$BACKEND_PID" || true
  printf '[dev] Backend 已退出，正在停止 UI。\n' >&2
else
  wait "$UI_PID" || true
  printf '[dev] UI 已退出，正在停止 Backend。\n' >&2
fi
exit 1
