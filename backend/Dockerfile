# syntax=docker/dockerfile:1.7

# 提供 Node 22（含 npm/npx）给 MCP stdio server 使用；Debian 自带 node 版本过旧且无 npx。
FROM node:22-bookworm-slim AS node

FROM --platform=$BUILDPLATFORM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    TIKTOKEN_CACHE_DIR=/opt/tiktoken

# Debian 官方源在目标网络下很慢，改用清华镜像；uv 走清华 PyPI 安装。
RUN sed -i 's|deb.debian.org|mirrors.tuna.tsinghua.edu.cn|g' /etc/apt/sources.list.d/debian.sources \
 && apt-get update \
 && apt-get install -y --no-install-recommends curl ca-certificates \
 && rm -rf /var/lib/apt/lists/* \
 && pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple uv

# Node 22（node + npm/npx）
COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY --from=node /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -sf /usr/local/lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
 && ln -sf /usr/local/lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx

WORKDIR /app

# 依赖层先于源码，最大化构建缓存
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY backend/ ./
RUN uv sync --frozen --no-dev

# 预下载 tiktoken 编码，避免运行时联网
RUN uv run --no-sync python -c "import tiktoken; tiktoken.get_encoding('cl100k_base')"

COPY backend/docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh \
 && useradd --create-home --uid 10001 app \
 && mkdir -p /data /workspaces \
 && chown -R app:app /app /data /workspaces /opt/tiktoken

USER app
EXPOSE 8000
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
