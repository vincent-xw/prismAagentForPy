#!/usr/bin/env sh
set -eu
cd /app
# 启动前完成迁移；禁止在长事务里等待模型或 SSE。
uv run --no-sync alembic upgrade head
exec uv run --no-sync uvicorn prism_agent_kit.main:app \
  --host 0.0.0.0 --port "${PRISM_AGENT_KIT_PORT:-8000}"
