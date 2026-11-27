#!/usr/bin/env sh
set -eu
cd /app
# 容器内的 localhost 指容器自己，不是宿主机或模型服务：启动即拒绝，避免"健康但一发 Run 就超时"。
case "${PRISM_AGENT_KIT_MODEL_BASE_URL:-}" in
  *localhost*|*127.0.0.1*|*0.0.0.0*)
    echo "MODEL_BASE_URL 不能指向容器自身（localhost/127.0.0.1）；请使用宿主机 LAN IP 或 host.docker.internal" >&2
    exit 1
    ;;
esac
# 启动前完成迁移；禁止在长事务里等待模型或 SSE。
uv run --no-sync alembic upgrade head
exec uv run --no-sync uvicorn prism_agent_kit.main:app \
  --host 0.0.0.0 --port "${PRISM_AGENT_KIT_PORT:-8000}"
