# syntax=docker/dockerfile:1.7
FROM --platform=$BUILDPLATFORM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    TIKTOKEN_CACHE_DIR=/opt/tiktoken

# Debian 官方源在目标网络下很慢，改用清华镜像；uv 走清华 PyPI 安装。
# nodejs：MCP stdio server 常用 npx 启动；curl：健康检查。
RUN sed -i 's|deb.debian.org|mirrors.tuna.tsinghua.edu.cn|g' /etc/apt/sources.list.d/debian.sources \
 && apt-get update \
 && apt-get install -y --no-install-recommends curl nodejs ca-certificates \
 && rm -rf /var/lib/apt/lists/* \
 && pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple uv

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
