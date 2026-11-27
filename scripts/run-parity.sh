#!/usr/bin/env bash
# 一键跑行为 parity：启动 mock 模型 → 两端建临时档案并激活 → pytest → 清理档案与进程。
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HOST="${PRISM_PARITY_HOST:-192.168.31.90}"
TOKEN="${PRISM_PARITY_TOKEN:-change-me}"
PY_URL="http://$HOST:8000"
JAVA_URL="http://$HOST:8001"

cleanup() {
  ssh srv 'docker exec prism-agent-mysql-java-1 mysql -uprism -pprism prism -e "DELETE FROM model_profiles WHERE name=\"parity-mock\";" 2>/dev/null || true' || true
  ssh srv 'docker exec prism-agent-backend-python-1 /app/.venv/bin/python -c "
import sqlite3
db=sqlite3.connect(\"/data/agent.db\"); db.execute(\"DELETE FROM model_profiles WHERE name=\x27parity-mock\x27\"); db.commit()
" 2>/dev/null || true' || true
  ssh srv 'bash ~/prism-agent/scripts/mock-model.sh stop' >/dev/null 2>&1 || true
}
trap cleanup EXIT

ssh srv 'bash ~/prism-agent/scripts/mock-model.sh start'

for URL in "$PY_URL" "$JAVA_URL"; do
  ID=$(curl -fsS -X POST "$URL/api/v1/model-profiles" \
    -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
    -d "{\"name\":\"parity-mock\",\"base_url\":\"http://$HOST:19000/v1\",\"model\":\"mock\",\"api_key_env\":\"MOCK_API_KEY\",\"api_key\":\"mock-key\",\"context_window\":65536,\"max_output_tokens\":8192}" \
    | python3 -c 'import sys,json;print(json.load(sys.stdin)["id"])')
  curl -fsS -X POST "$URL/api/v1/model-profiles/$ID/activate" -H "Authorization: Bearer $TOKEN" >/dev/null
done

cd "$ROOT/tests/parity"
UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/uv-cache}" \
  PRISM_PARITY_PYTHON_URL="$PY_URL" PRISM_PARITY_JAVA_URL="$JAVA_URL" \
  PRISM_PARITY_TOKEN="$TOKEN" uv run --project . pytest -q "$@"
