#!/usr/bin/env bash
# 在服务器上启动/停止确定性模型桩（行为 parity 与双 UI E2E 使用）。
set -euo pipefail
ACTION="${1:?usage: mock-model.sh start|stop|status}"
HOST="${MOCK_HOST:-0.0.0.0}"
PORT="${MOCK_PORT:-19000}"
PID_FILE="/tmp/prism-mock-model.pid"
LOG_FILE="/tmp/prism-mock-model.log"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

case "$ACTION" in
  start)
    if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
      echo "already running pid=$(cat "$PID_FILE")"
      exit 0
    fi
    nohup python3 "$ROOT/tests/mock-model/server.py" --host "$HOST" --port "$PORT" \
      >"$LOG_FILE" 2>&1 &
    echo $! >"$PID_FILE"
    sleep 0.5
    curl -fsS -X POST "http://127.0.0.1:$PORT/v1/chat/completions" \
      -H 'Content-Type: application/json' -d '{"messages":[{"role":"user","content":"ping"}]}' >/dev/null
    echo "started pid=$(cat "$PID_FILE") port=$PORT"
    ;;
  stop)
    if [[ -f "$PID_FILE" ]]; then
      kill "$(cat "$PID_FILE")" 2>/dev/null || true
      rm -f "$PID_FILE"
    fi
    echo stopped
    ;;
  status)
    if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
      echo "running pid=$(cat "$PID_FILE")"
    else
      echo stopped
    fi
    ;;
  *) echo "usage: mock-model.sh start|stop|status" >&2; exit 2 ;;
esac
