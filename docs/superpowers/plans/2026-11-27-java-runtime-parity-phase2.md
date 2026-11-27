# Java 双语言 Runtime —— Phase 2 容器化与双 UI 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用一条 `docker compose up -d --build` 在 `192.168.31.90`（x86_64）上跑起两个独立后端 + 同一个 UI 镜像的两个容器 + 独立 MySQL，并让同一套黑盒契约测试能分别打向两个后端。

**Architecture:** 三个镜像（Python 后端、Java 后端、UI），Compose 五常驻服务（`backend-python`、`backend-java`、`ui-python`、`ui-java`、`mysql-java`）+ 四个命名卷。UI 只构建一次，两个容器用同一 image tag、仅运行时 `API_TARGET` 不同；nginx 在容器内做同源反代与 SPA 回退。契约测试是独立 `tests/contract` uv 工程，用 `BASE_URL` 参数化，对两端跑同一套断言。

**Tech Stack:** Docker Engine 29（服务器）、Docker Compose v2、`python:3.12-slim` + `uv`、`eclipse-temurin:21-jre`、`node:22-slim` + pnpm、`nginx:1.27-alpine`（envsubst 模板）、`mysql:8.4`、pytest + httpx（契约测试）。

**Spec:** `docs/superpowers/specs/2026-11-27-java-runtime-v14-parity-design.md`（§6、§9、§12、§13）

## Global Constraints

- 部署目标机 `192.168.31.90` 为 **x86_64**；所有镜像必须构建为 `linux/amd64`。
- **禁止使用本机 Mac 的 Docker Desktop**；镜像构建与 Compose 都在服务器上执行（仓库通过 rsync 同步到 `~/prism-agent`）。
- 端口：`backend-python` → 宿主 `8000`，`backend-java` → 宿主 `8001`，`ui-python` → 宿主 `3000`，`ui-java` → 宿主 `3001`，`mysql-java` 不发布到宿主；全部可用 `.env` 覆盖。
- 两个 UI 容器必须使用**同一个 image tag**（`prism-agent-ui:${PRISM_VERSION}`），并通过 `docker compose images` 证明 Image ID 相同。
- UI 的 API 基址必须**运行时注入**（`API_TARGET`），不得写进构建产物；浏览器只走同源 `/api/v1`。
- 两个后端不得声明互相依赖；停掉任一端，另一端与对应 UI 必须继续可用。
- 每端有自己的持久化卷：`python-data`（SQLite）、`workspace-python`、`workspace-java`、`mysql-data`；禁止共享数据卷。
- 容器内不得用 `localhost` 指代宿主机或模型服务；模型走外部 OpenAI-compatible 服务（`MODEL_BASE_URL`）。
- 容器以非 root 用户运行；不使用 `privileged`、不挂 Docker Socket、不挂宿主机用户目录。
- 日志配置轮转（`logging.options.max-size=10m`、`max-file=3`）。
- 不修改 Python/Java 业务代码；本阶段只新增容器与测试基础设施（唯一例外：为容器化补 `.dockerignore` 与启动脚本）。
- 契约测试断言**只读**，不得创建会话以外的副作用；跑完需清理自己创建的数据（用专用测试 token 与独立测试库/文件）。

## Review Focus

1. **`localhost` 陷阱**：容器里把模型地址写成 `127.0.0.1` 时，健康检查照样绿、但一发 Run 就超时 —— 在 Task 2 的 env 校验测试里钉住。
2. **SSE 被代理缓冲**：nginx 默认 `proxy_buffering on` 会让事件流"一次性到达"或超时断开 —— 在 Task 4 的流式探针里钉住（`curl -N` 分块到达 + 首字节时间）。
3. **两个 UI 镜像 ID 不一致**：两次独立构建会产生两个镜像，违反"单镜像双容器" —— 在 Task 5 的 `compose images` 断言里钉住。
4. **卷权限**：容器内非 root 用户写 `/data`、`/workspaces` 失败会导致启动即崩 —— 在 Task 2/3 的启动冒烟里钉住（容器必须 healthy，且能写文件）。
5. **错误被 SPA 回退吃掉**：`/api/` 的 404 若返回 `index.html`（200 HTML），客户端会把错误当成功 —— 在 Task 4 的 nginx 用例里钉住（404 + `application/json`）。

---

## 文件结构（Phase 2 结束时）

```text
.
├── .env.example                       # 根级 Compose 变量样例（无真实密钥）
├── .dockerignore                      # 根级构建上下文忽略
├── docker-compose.yml                 # 五常驻服务 + 卷 + 健康检查
├── deploy/
│   ├── nginx/default.conf.template    # UI 同源反代 + SSE + SPA 回退
│   ├── docker-compose.dev.yml         # 本机/服务器开发覆盖（发布 MySQL 端口）
│   └── README.md                      # 部署、排障、端口与卷说明
├── backend/
│   ├── Dockerfile                     # python:3.12-slim + uv + node（MCP stdio）
│   ├── .dockerignore
│   └── docker/entrypoint.sh           # alembic upgrade head → uvicorn
├── backend-java/
│   ├── Dockerfile                     # maven 构建 → temurin jre 21
│   ├── .dockerignore
│   └── docker/entrypoint.sh           # 等待 MySQL → 启动 jar（Flyway 在应用内）
├── ui/
│   ├── Dockerfile                     # node 构建 → nginx 运行
│   └── .dockerignore
├── contracts/
│   ├── README.md                      # 冻结/变更规则
│   ├── openapi/prism-agent-api.yaml   # 从运行中的 Python 导出的快照
│   └── events/events.schema.json      # 27 事件 JSON Schema（Phase 2 先放骨架）
└── tests/
    └── contract/
        ├── pyproject.toml             # pytest + httpx
        ├── conftest.py                # BASE_URL / TOKEN 夹具
        ├── test_health.py
        ├── test_auth.py
        ├── test_sessions.py
        └── test_error_envelope.py
```

职责边界：Dockerfile 只负责构建与启动；Compose 只负责编排与环境；nginx 模板只负责同源反代与静态回退；契约测试只做黑盒 HTTP 断言，不 import 任何后端代码。

**部署路径约定**：仓库同步到服务器 `~/prism-agent`（`rsync -az --delete --exclude .git --exclude 'backend-java/target' ./ srv:~/prism-agent/`），所有 `docker`/`docker compose` 命令在服务器上执行。

---

### Task 1: 契约测试骨架（先红）

**Files:**
- Create: `tests/contract/pyproject.toml`
- Create: `tests/contract/conftest.py`
- Create: `tests/contract/test_health.py`
- Create: `tests/contract/test_auth.py`
- Create: `tests/contract/README.md`

**Interfaces:**
- Consumes: 无（纯黑盒）
- Produces: 环境变量契约 `PRISM_CONTRACT_BASE_URL`（如 `http://127.0.0.1:8000`）、`PRISM_CONTRACT_TOKEN`；pytest 夹具 `base_url`、`token`、`client`（`httpx.Client`，自动带 Bearer）

- [ ] **Step 1: 写失败测试**

`tests/contract/conftest.py`：

```python
import os
import httpx
import pytest

@pytest.fixture(scope="session")
def base_url() -> str:
    value = os.environ.get("PRISM_CONTRACT_BASE_URL")
    if not value:
        raise RuntimeError("必须设置 PRISM_CONTRACT_BASE_URL")
    return value.rstrip("/")

@pytest.fixture(scope="session")
def token() -> str:
    value = os.environ.get("PRISM_CONTRACT_TOKEN")
    if not value:
        raise RuntimeError("必须设置 PRISM_CONTRACT_TOKEN")
    return value

@pytest.fixture(scope="session")
def client(base_url: str, token: str) -> httpx.Client:
    with httpx.Client(base_url=base_url, headers={"Authorization": f"Bearer {token}"}, timeout=30.0) as c:
        yield c
```

`tests/contract/test_health.py`：

```python
def test_health_contract(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert set(body) >= {"status", "service", "version", "environment", "workspace_fts"}
    assert body["environment"] in {"development", "test", "production"}

def test_health_needs_no_auth(base_url):
    import httpx
    response = httpx.get(f"{base_url}/api/v1/health", timeout=10.0)
    assert response.status_code == 200
```

`tests/contract/test_auth.py`：

```python
import httpx

def test_missing_token_is_401(base_url):
    response = httpx.get(f"{base_url}/api/v1/sessions", timeout=10.0)
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json()["error"]["code"] == "UNAUTHORIZED"

def test_wrong_token_is_401(base_url):
    response = httpx.get(
        f"{base_url}/api/v1/sessions",
        headers={"Authorization": "Bearer wrong-token"},
        timeout=10.0,
    )
    assert response.status_code == 401
```

`tests/contract/pyproject.toml`：

```toml
[project]
name = "prism-contract-tests"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = ["pytest>=8.3,<10.0", "httpx>=0.28,<1.0"]

[tool.pytest.ini_options]
testpaths = ["."]
addopts = "-ra --strict-config --strict-markers"
```

- [ ] **Step 2: 运行确认失败**

Run: `cd tests/contract && PRISM_CONTRACT_BASE_URL=http://127.0.0.1:8000 PRISM_CONTRACT_TOKEN=dev-token uv run --project . pytest -q`
Expected: FAIL —— `httpx.ConnectError: [Errno 61] Connection refused`（两个后端都还没容器化）

- [ ] **Step 3: 写契约测试说明**

`tests/contract/README.md` 必须写清：这是**语言无关**的黑盒测试；只允许通过 `PRISM_CONTRACT_BASE_URL` 切换目标；不得 import 后端代码、不得读后端数据库；新增断言要同时能在 Python 与 Java 上通过；失败时先判断是协议差异还是实现缺陷。

- [ ] **Step 4: 提交**

```bash
git add tests/contract
git commit -m "test(contract): 建立语言无关的 HTTP 契约测试骨架"
```

---

### Task 2: Python 后端镜像

**Files:**
- Create: `backend/Dockerfile`
- Create: `backend/.dockerignore`
- Create: `backend/docker/entrypoint.sh`

**Interfaces:**
- Consumes: Task 1 的契约测试
- Produces: 镜像 `prism-backend-python:${PRISM_VERSION}`；容器内路径 `/app`（代码）、`/data`（SQLite）、`/workspaces`（工作区）、`/opt/tiktoken`（编码缓存）；监听 `8000`

- [ ] **Step 1: 写失败检查**

Run: `ssh srv 'docker image inspect prism-backend-python:dev >/dev/null 2>&1 && echo exists || echo missing'`
Expected: `missing`

- [ ] **Step 2: 实现 Dockerfile**

```dockerfile
# syntax=docker/dockerfile:1.7
FROM --platform=$BUILDPLATFORM python:3.12-slim AS base
ENV PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    TIKTOKEN_CACHE_DIR=/opt/tiktoken
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl nodejs ca-certificates \
 && rm -rf /var/lib/apt/lists/* \
 && curl -LsSf https://astral.sh/uv/install.sh | sh \
 && mv /root/.local/bin/uv /usr/local/bin/uv
WORKDIR /app
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY backend/ ./
RUN uv sync --frozen --no-dev
# 预下载 tiktoken 编码，避免运行时联网
RUN uv run python -c "import tiktoken; tiktoken.get_encoding('cl100k_base')"
COPY backend/docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh \
 && useradd --create-home --uid 10001 app \
 && mkdir -p /data /workspaces \
 && chown -R app:app /app /data /workspaces /opt/tiktoken
USER app
EXPOSE 8000
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
```

`backend/docker/entrypoint.sh`：

```bash
#!/usr/bin/env sh
set -eu
cd /app
uv run --no-sync alembic upgrade head
exec uv run --no-sync uvicorn prism_agent_kit.main:app --host 0.0.0.0 --port "${PRISM_AGENT_KIT_PORT:-8000}"
```

`backend/.dockerignore`：`.venv`、`__pycache__`、`.pytest_cache`、`.mypy_cache`、`.ruff_cache`、`tests`、`.env`、`*.db`。

> 注意：构建上下文是**仓库根**（`docker build -f backend/Dockerfile .`），否则 `COPY backend/...` 不成立；Task 5 的 Compose 里用 `context: .` + `dockerfile: backend/Dockerfile`。

- [ ] **Step 3: 构建并启动冒烟**

```bash
rsync -az --delete --exclude .git --exclude 'backend-java/target' ./ srv:~/prism-agent/
ssh srv 'cd ~/prism-agent && docker build --platform linux/amd64 -f backend/Dockerfile -t prism-backend-python:dev .'
```

以最小 env 启动（模型配置用占位，健康检查不需要真实模型）：

```bash
ssh srv 'docker run -d --rm --name smoke-python -p 18000:8000 \
  -e PRISM_AGENT_KIT_ENVIRONMENT=development \
  -e PRISM_AGENT_KIT_API_TOKEN=dev-token \
  -e PRISM_AGENT_KIT_DATABASE_PATH=/data/agent.db \
  -e PRISM_AGENT_KIT_MODEL_BASE_URL=https://api.deepseek.com/v1 \
  -e PRISM_AGENT_KIT_MODEL_API_KEY=placeholder \
  -e PRISM_AGENT_KIT_MODEL_NAME=deepseek-chat \
  -e PRISM_AGENT_KIT_MODEL_CONTEXT_WINDOW=65536 \
  -e PRISM_AGENT_KIT_MODEL_MAX_OUTPUT_TOKENS=8192 \
  -e PRISM_AGENT_KIT_MODEL_TOKEN_ENCODING=cl100k_base \
  prism-backend-python:dev'
```

- [ ] **Step 4: 跑契约测试**

Run: `cd tests/contract && PRISM_CONTRACT_BASE_URL=http://192.168.31.90:18000 PRISM_CONTRACT_TOKEN=dev-token uv run --project . pytest -q`
Expected: `5 passed`（health 2 + auth 2 + 健康免鉴权 1）

- [ ] **Step 5: 清理与提交**

```bash
ssh srv 'docker rm -f smoke-python'
git add backend/Dockerfile backend/.dockerignore backend/docker/entrypoint.sh
git commit -m "build(python): 后端容器镜像与迁移启动入口"
```

---

### Task 3: Java 后端镜像

**Files:**
- Create: `backend-java/Dockerfile`
- Create: `backend-java/.dockerignore`
- Create: `backend-java/docker/entrypoint.sh`

**Interfaces:**
- Consumes: Task 1 契约测试
- Produces: 镜像 `prism-backend-java:${PRISM_VERSION}`；监听 `8080`；环境变量沿用 `PRISM_*`（见 `backend-java/README.md`）

- [ ] **Step 1: 写失败检查**

Run: `ssh srv 'docker image inspect prism-backend-java:dev >/dev/null 2>&1 && echo exists || echo missing'`
Expected: `missing`

- [ ] **Step 2: 实现 Dockerfile**

```dockerfile
# syntax=docker/dockerfile:1.7
FROM --platform=$BUILDPLATFORM maven:3.9-eclipse-temurin-21 AS build
WORKDIR /workspace
COPY backend-java/pom.xml ./
RUN mvn -B -q dependency:go-offline
COPY backend-java/ ./
RUN mvn -B -q -DskipTests package

FROM eclipse-temurin:21-jre-jammy
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl nodejs ca-certificates \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --create-home --uid 10001 app \
 && mkdir -p /app /workspaces \
 && chown -R app:app /app /workspaces
WORKDIR /app
COPY --from=build /workspace/target/prism-agent-java-*.jar /app/app.jar
COPY backend-java/docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh
USER app
EXPOSE 8080
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
```

`backend-java/docker/entrypoint.sh`：

```bash
#!/usr/bin/env sh
set -eu
# Flyway 在应用启动时执行；这里只做 JVM 参数与启动。
exec java ${JAVA_OPTS:--XX:MaxRAMPercentage=75} -jar /app/app.jar
```

`backend-java/.dockerignore`：`target`、`.idea`、`*.iml`。

> 构建上下文同样是仓库根：`docker build -f backend-java/Dockerfile .`。

- [ ] **Step 3: 构建并启动冒烟**

```bash
ssh srv 'cd ~/prism-agent && docker build --platform linux/amd64 -f backend-java/Dockerfile -t prism-backend-java:dev .'
```

冒烟需要可达的 MySQL。**不要复用** `prism-java-test-mysql`（它只绑定回环，容器间不可达），也**不要**用 `--network host`（服务器 8080 已被其他项目占用）。建一个一次性网络：

```bash
ssh srv 'docker network create prism-smoke 2>/dev/null || true
docker run -d --rm --name smoke-mysql --network prism-smoke \
  -e MYSQL_ROOT_PASSWORD=prism -e MYSQL_DATABASE=prism mysql:8.4
sleep 20
docker run -d --rm --name smoke-java --network prism-smoke -p 18001:8080 \
  -e PRISM_DB_URL="jdbc:mysql://smoke-mysql:3306/prism?connectionTimeZone=UTC&forceConnectionTimeZoneToSession=true" \
  -e PRISM_DB_USER=root -e PRISM_DB_PASSWORD=prism \
  -e PRISM_API_TOKEN=dev-token -e PRISM_ENVIRONMENT=development \
  prism-backend-java:dev'
```

- [ ] **Step 4: 跑契约测试**

Run: `cd tests/contract && PRISM_CONTRACT_BASE_URL=http://192.168.31.90:18001 PRISM_CONTRACT_TOKEN=dev-token uv run --project . pytest -q`
Expected: `5 passed`

- [ ] **Step 5: 清理与提交**

```bash
ssh srv 'docker rm -f smoke-java smoke-mysql; docker network rm prism-smoke 2>/dev/null || true'
git add backend-java/Dockerfile backend-java/.dockerignore backend-java/docker/entrypoint.sh
git commit -m "build(java): 后端多阶段镜像与非 root 运行"
```

---

### Task 4: UI 镜像与 nginx 运行时反代

**Files:**
- Create: `ui/Dockerfile`
- Create: `ui/.dockerignore`
- Create: `deploy/nginx/default.conf.template`

**Interfaces:**
- Consumes: Task 2/3 的后端（契约测试的目标）
- Produces: 镜像 `prism-agent-ui:${PRISM_VERSION}`；容器内 nginx 监听 `8080`，读取环境变量 `API_TARGET`（如 `http://backend-python:8000`）

- [ ] **Step 1: 写失败测试**

`tests/contract/test_ui_proxy.py`：

```python
import httpx

def test_ui_serves_spa(ui_base_url):
    response = httpx.get(f"{ui_base_url}/", timeout=10.0)
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]

def test_ui_proxies_api_health(ui_base_url):
    response = httpx.get(f"{ui_base_url}/api/v1/health", timeout=10.0)
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

def test_api_404_is_json_not_html(ui_base_url):
    response = httpx.get(f"{ui_base_url}/api/v1/does-not-exist", timeout=10.0)
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/json")
    assert response.json()["error"]["code"] == "NOT_FOUND"

def test_spa_route_falls_back_to_index(ui_base_url):
    response = httpx.get(f"{ui_base_url}/sessions/abc", timeout=10.0)
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
```

并在 `conftest.py` 追加：

```python
@pytest.fixture(scope="session")
def ui_base_url() -> str:
    value = os.environ.get("PRISM_CONTRACT_UI_BASE_URL")
    if not value:
        raise RuntimeError("必须设置 PRISM_CONTRACT_UI_BASE_URL")
    return value.rstrip("/")
```

Run: `PRISM_CONTRACT_UI_BASE_URL=http://192.168.31.90:13000 uv run --project . pytest test_ui_proxy.py -q`
Expected: FAIL —— `ConnectError: Connection refused`

- [ ] **Step 2: 实现 nginx 模板**

`deploy/nginx/default.conf.template`：

```nginx
server {
    listen 8080;
    server_name _;
    root /usr/share/nginx/html;
    index index.html;
    client_max_body_size 8m;

    # API 反向代理：不缓冲、长读超时、透传错误
    location /api/ {
        proxy_pass ${API_TARGET};
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header Connection "";
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
        add_header X-Accel-Buffering no;
    }

    # 静态资源长缓存
    location /assets/ {
        try_files $uri =404;
        expires 7d;
        add_header Cache-Control "public, immutable";
    }

    # SPA 回退：/api/ 之外才回退到 index.html
    location / {
        try_files $uri $uri/ /index.html;
    }
}
```

- [ ] **Step 3: 实现 UI Dockerfile**

```dockerfile
# syntax=docker/dockerfile:1.7
FROM --platform=$BUILDPLATFORM node:22-slim AS build
RUN corepack enable
WORKDIR /app
COPY ui/package.json ui/pnpm-lock.yaml ui/.npmrc ./
RUN pnpm install --frozen-lockfile
COPY ui/ ./
RUN pnpm build

FROM nginx:1.27-alpine
ENV API_TARGET=http://backend-python:8000
COPY --from=build /app/dist /usr/share/nginx/html
COPY deploy/nginx/default.conf.template /etc/nginx/templates/default.conf.template
EXPOSE 8080
```

`ui/.dockerignore`：`node_modules`、`dist`、`test-results`、`.env`。

> nginx 官方镜像启动时用 `envsubst` 渲染 `/etc/nginx/templates/*.template`，`API_TARGET` 只在运行时生效，不进入构建产物。

- [ ] **Step 4: 构建并验证两个 UI 容器**

```bash
rsync -az --delete --exclude .git --exclude 'backend-java/target' ./ srv:~/prism-agent/
ssh srv 'cd ~/prism-agent && docker build --platform linux/amd64 -f ui/Dockerfile -t prism-agent-ui:dev .'
ssh srv 'docker run -d --rm --name smoke-ui-python -p 13000:8080 -e API_TARGET=http://192.168.31.90:18000 prism-agent-ui:dev'
```

UI 的 `/api/` 需要一个真实后端，先起一个一次性 Python 后端容器：

```bash
ssh srv 'docker run -d --rm --name smoke-python -p 18000:8000 \
  -e PRISM_AGENT_KIT_ENVIRONMENT=development -e PRISM_AGENT_KIT_API_TOKEN=dev-token \
  -e PRISM_AGENT_KIT_DATABASE_PATH=/data/agent.db \
  -e PRISM_AGENT_KIT_MODEL_BASE_URL=https://api.deepseek.com/v1 -e PRISM_AGENT_KIT_MODEL_API_KEY=placeholder \
  -e PRISM_AGENT_KIT_MODEL_NAME=deepseek-chat -e PRISM_AGENT_KIT_MODEL_CONTEXT_WINDOW=65536 \
  -e PRISM_AGENT_KIT_MODEL_MAX_OUTPUT_TOKENS=8192 -e PRISM_AGENT_KIT_MODEL_TOKEN_ENCODING=cl100k_base \
  prism-backend-python:dev'
sleep 15'
```

Run: `cd tests/contract && PRISM_CONTRACT_UI_BASE_URL=http://192.168.31.90:13000 uv run --project . pytest test_ui_proxy.py -q`
Expected: `4 passed`

- [ ] **Step 5: 验证 SSE 不被缓冲**

```bash
ssh srv "curl -sN -H 'Authorization: Bearer dev-token' http://127.0.0.1:13000/api/v1/runs/not-a-run/events -o /dev/null -w '%{http_code} %{time_starttransfer}\n'"
```
Expected: 返回 404 且 `time_starttransfer < 2s`（说明反代没有挂起；真正的流式验证在 Phase 3 的 Run 场景）

- [ ] **Step 6: 清理与提交**

```bash
ssh srv 'docker rm -f smoke-ui-python smoke-python'
git add ui/Dockerfile ui/.dockerignore deploy/nginx/default.conf.template tests/contract/test_ui_proxy.py tests/contract/conftest.py
git commit -m "build(ui): 单镜像 nginx 运行时反代与 SPA 回退"
```

---

### Task 5: Docker Compose 五服务编排

**Files:**
- Create: `docker-compose.yml`
- Create: `deploy/docker-compose.dev.yml`
- Create: `.env.example`
- Create: `.dockerignore`
- Create: `deploy/README.md`

**Interfaces:**
- Consumes: 三个镜像（Task 2–4）
- Produces: 服务名 `backend-python`/`backend-java`/`ui-python`/`ui-java`/`mysql-java`；卷 `python-data`/`workspace-python`/`workspace-java`/`mysql-data`

- [ ] **Step 1: 写失败检查**

Run: `cd ~/prism-agent 2>/dev/null; docker compose config >/dev/null 2>&1 && echo ok || echo "no compose file"`
Expected: `no compose file`

- [ ] **Step 2: 实现 Compose**

```yaml
name: prism-agent

x-logging: &logging
  driver: json-file
  options:
    max-size: "10m"
    max-file: "3"

services:
  mysql-java:
    image: mysql:8.4
    command: ["--character-set-server=utf8mb4", "--collation-server=utf8mb4_0900_ai_ci"]
    environment:
      MYSQL_DATABASE: ${PRISM_JAVA_DB_NAME:-prism}
      MYSQL_USER: ${PRISM_JAVA_DB_USER:-prism}
      MYSQL_PASSWORD: ${PRISM_JAVA_DB_PASSWORD:-prism}
      MYSQL_ROOT_PASSWORD: ${PRISM_JAVA_DB_ROOT_PASSWORD:-prism}
    volumes:
      - mysql-data:/var/lib/mysql
    healthcheck:
      test: ["CMD-SHELL", "mysqladmin ping -h 127.0.0.1 -p\"$$MYSQL_ROOT_PASSWORD\" --silent"]
      interval: 5s
      timeout: 5s
      retries: 20
    logging: *logging
    restart: unless-stopped

  backend-python:
    image: prism-backend-python:${PRISM_VERSION:-dev}
    build:
      context: .
      dockerfile: backend/Dockerfile
      platforms: [linux/amd64]
    environment:
      PRISM_AGENT_KIT_ENVIRONMENT: production
      PRISM_AGENT_KIT_API_TOKEN: ${PRISM_API_TOKEN:?set PRISM_API_TOKEN}
      PRISM_AGENT_KIT_DATABASE_PATH: /data/agent.db
      PRISM_AGENT_KIT_WORKSPACE_INDEX_MAX_FILES: ${PRISM_WORKSPACE_MAX_FILES:-20000}
      PRISM_AGENT_KIT_PRISM_HOME: /skills
      PRISM_AGENT_KIT_MODEL_BASE_URL: ${MODEL_BASE_URL:?set MODEL_BASE_URL}
      PRISM_AGENT_KIT_MODEL_API_KEY: ${MODEL_API_KEY:?set MODEL_API_KEY}
      PRISM_AGENT_KIT_MODEL_NAME: ${MODEL_NAME:?set MODEL_NAME}
      PRISM_AGENT_KIT_MODEL_CONTEXT_WINDOW: ${MODEL_CONTEXT_WINDOW:-65536}
      PRISM_AGENT_KIT_MODEL_MAX_OUTPUT_TOKENS: ${MODEL_MAX_OUTPUT_TOKENS:-8192}
      PRISM_AGENT_KIT_MODEL_TOKEN_ENCODING: ${MODEL_TOKEN_ENCODING:-cl100k_base}
    ports:
      - "${PRISM_PORT_BACKEND_PYTHON:-8000}:8000"
    volumes:
      - python-data:/data
      - workspace-python:/workspaces
      - ./skills:/skills:ro
    healthcheck:
      test: ["CMD", "curl", "-fsS", "http://127.0.0.1:8000/api/v1/health"]
      interval: 10s
      timeout: 5s
      retries: 12
    logging: *logging
    restart: unless-stopped

  backend-java:
    image: prism-backend-java:${PRISM_VERSION:-dev}
    build:
      context: .
      dockerfile: backend-java/Dockerfile
      platforms: [linux/amd64]
    environment:
      PRISM_DB_URL: jdbc:mysql://mysql-java:3306/${PRISM_JAVA_DB_NAME:-prism}?connectionTimeZone=UTC&forceConnectionTimeZoneToSession=true
      PRISM_DB_USER: ${PRISM_JAVA_DB_USER:-prism}
      PRISM_DB_PASSWORD: ${PRISM_JAVA_DB_PASSWORD:-prism}
      PRISM_API_TOKEN: ${PRISM_API_TOKEN:?set PRISM_API_TOKEN}
      PRISM_ENVIRONMENT: production
    ports:
      - "${PRISM_PORT_BACKEND_JAVA:-8001}:8080"
    volumes:
      - workspace-java:/workspaces
      - ./skills:/skills:ro
    depends_on:
      mysql-java:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-fsS", "http://127.0.0.1:8080/api/v1/health"]
      interval: 10s
      timeout: 5s
      retries: 12
    logging: *logging
    restart: unless-stopped

  ui-python:
    image: prism-agent-ui:${PRISM_VERSION:-dev}
    build:
      context: .
      dockerfile: ui/Dockerfile
      platforms: [linux/amd64]
    environment:
      API_TARGET: http://backend-python:8000
    ports:
      - "${PRISM_PORT_UI_PYTHON:-3000}:8080"
    depends_on:
      backend-python:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "wget", "-q", "-O", "/dev/null", "http://127.0.0.1:8080/"]
      interval: 10s
      timeout: 5s
      retries: 12
    logging: *logging
    restart: unless-stopped

  ui-java:
    image: prism-agent-ui:${PRISM_VERSION:-dev}
    environment:
      API_TARGET: http://backend-java:8080
    ports:
      - "${PRISM_PORT_UI_JAVA:-3001}:8080"
    depends_on:
      backend-java:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "wget", "-q", "-O", "/dev/null", "http://127.0.0.1:8080/"]
      interval: 10s
      timeout: 5s
      retries: 12
    logging: *logging
    restart: unless-stopped

volumes:
  python-data:
  workspace-python:
  workspace-java:
  mysql-data:
```

`deploy/docker-compose.dev.yml`（覆盖：发布 MySQL 端口，供宿主机 IDE 调试）：

```yaml
services:
  mysql-java:
    ports:
      - "127.0.0.1:13306:3306"
```

`.env.example`（根级，无真实密钥）：

```dotenv
PRISM_VERSION=dev
PRISM_API_TOKEN=change-me
MODEL_BASE_URL=https://api.deepseek.com/v1
MODEL_API_KEY=change-me
MODEL_NAME=deepseek-chat
MODEL_CONTEXT_WINDOW=65536
MODEL_MAX_OUTPUT_TOKENS=8192
MODEL_TOKEN_ENCODING=cl100k_base
PRISM_PORT_UI_PYTHON=3000
PRISM_PORT_UI_JAVA=3001
PRISM_PORT_BACKEND_PYTHON=8000
PRISM_PORT_BACKEND_JAVA=8001
```

根 `.dockerignore`：`.git`、`.venv`、`**/node_modules`、`**/target`、`**/dist`、`.superpowers`、`docs`、`tests`。

- [ ] **Step 3: 准备只读技能目录**

仓库还没有 `skills/` 目录，bind mount 会在宿主机生成 root 属主目录并让非 root 容器不可读。先建占位：

```bash
mkdir -p skills && touch skills/.gitkeep
git add skills/.gitkeep
```

- [ ] **Step 4: 校验配置并启动**

```bash
rsync -az --delete --exclude .git --exclude 'backend-java/target' --exclude 'ui/node_modules' ./ srv:~/prism-agent/
ssh srv 'cd ~/prism-agent && cp -n .env.example .env && docker compose config >/dev/null && echo config-ok'
ssh srv 'cd ~/prism-agent && docker compose up -d --build'
ssh srv 'cd ~/prism-agent && docker compose ps'
```

Expected: 五个服务均 `running`，`backend-*` 与 `ui-*` 为 `healthy`；端口 3000/3001/8000/8001 可访问。

- [ ] **Step 5: 双 UI 同镜像 + 契约测试**

```bash
ssh srv 'cd ~/prism-agent && docker compose images | grep prism-agent-ui'
```

Expected: 两行且 **IMAGE ID 相同**（若不同，说明 `ui-java` 被独立构建了，必须改成复用同一 tag）。

```bash
cd tests/contract
PRISM_CONTRACT_BASE_URL=http://192.168.31.90:8000 PRISM_CONTRACT_TOKEN=$(ssh srv 'grep ^PRISM_API_TOKEN ~/prism-agent/.env | cut -d= -f2') uv run --project . pytest -q
PRISM_CONTRACT_BASE_URL=http://192.168.31.90:8001 PRISM_CONTRACT_TOKEN=... uv run --project . pytest -q
PRISM_CONTRACT_UI_BASE_URL=http://192.168.31.90:3000 ... pytest test_ui_proxy.py -q
PRISM_CONTRACT_UI_BASE_URL=http://192.168.31.90:3001 ... pytest test_ui_proxy.py -q
```

Expected: 四组全绿。

- [ ] **Step 6: 隔离验证**

```bash
ssh srv 'cd ~/prism-agent && docker compose stop backend-java && curl -fsS http://127.0.0.1:8000/api/v1/health >/dev/null && echo python-ok && (curl -fsS http://127.0.0.1:8001/api/v1/health >/dev/null || echo java-down) && docker compose start backend-java'
```

Expected: 输出 `python-ok` 与 `java-down`；`start` 后 Java 恢复 healthy。

- [ ] **Step 7: 写部署手册并提交**

`deploy/README.md` 必须包含：端口表、卷表、`docker compose` 常用命令、如何只起一端（`docker compose up -d backend-java mysql-java ui-java`）、如何重建（`up -d --build`）、如何看日志、如何回到宿主机 IDE 调试（`deploy/docker-compose.dev.yml` 暴露 13306）、数据备份（`docker run --rm -v prism-agent_mysql-data:/var/lib/mysql ...`）、以及"不要在本机 Docker 上构建"的说明。

```bash
git add docker-compose.yml deploy/docker-compose.dev.yml deploy/README.md .env.example .dockerignore tests/contract
git commit -m "build: 五服务 Docker Compose 编排与部署手册"
```

---

### Task 6: 契约快照、Parity 与收尾

**Files:**
- Create: `contracts/README.md`
- Create: `contracts/openapi/prism-agent-api.yaml`（导出脚本生成）
- Create: `contracts/events/events.schema.json`（骨架：27 个事件名 + 必填 `type`/`run_id`）
- Create: `scripts/export-openapi.sh`
- Modify: `docs/compatibility/feature-parity.md`
- Modify: `AGENTS.md`

**Interfaces:**
- Consumes: Task 5 运行中的 Python 后端
- Produces: 可 diff 的 OpenAPI 快照；parity 表中的容器化状态

- [ ] **Step 1: 写失败检查**

Run: `test -f contracts/openapi/prism-agent-api.yaml && echo present || echo missing`
Expected: `missing`

- [ ] **Step 2: 导出快照**

`scripts/export-openapi.sh`：

```bash
#!/usr/bin/env bash
set -euo pipefail
# 从运行中的 Python 后端导出 OpenAPI 快照；不启动服务也能用 app.openapi()。
cd "$(dirname "$0")/.."
mkdir -p contracts/openapi
uv run --project backend python - <<'PY'
import json, pathlib, yaml
from prism_agent_kit.main import create_app
spec = create_app().openapi()
path = pathlib.Path("contracts/openapi/prism-agent-api.yaml")
path.write_text(yaml.safe_dump(spec, allow_unicode=True, sort_keys=False), encoding="utf-8")
print(f"wrote {path} ({len(spec.get('paths', {}))} paths)")
PY
```

Run: `bash scripts/export-openapi.sh`
Expected: 打印 `wrote contracts/openapi/prism-agent-api.yaml (35 paths)`（35 个 path、**42 个 operation**；数字不等说明后端路由变化，需先确认是否属于本阶段）。

- [ ] **Step 3: 事件 schema 骨架**

`contracts/events/events.schema.json`：`$defs` 里为 27 个事件名各建一个对象（`type` 常量 + `run_id` 字符串 + `additionalProperties: true`），并写 `x-invariants` 描述：持久事件 `id` 必为数字、`message.delta`/`reasoning.delta` 无 `id`、终态事件后关流。

Run: `python3 -c "import json;d=json.load(open('contracts/events/events.schema.json'));print(len(d['$defs']))"`
Expected: `27`

- [ ] **Step 4: 更新 parity 与 AGENTS**

- `docs/compatibility/feature-parity.md`：Health / Session 行的 `API` 列填 `Contract Passed`（两端契约测试通过），并新增"容器化"小节记录两个 UI 镜像 ID 相同、五服务健康、隔离验证结果。
- `AGENTS.md` 的 Java 段追加：Compose 服务名、端口约定、`deploy/` 职责、"禁止本机 Docker 构建"。

- [ ] **Step 5: 全量验证与提交**

```bash
cd backend-java && ./mvnw -q verify
cd ../backend && uv run pytest -q
cd ../tests/contract && PRISM_CONTRACT_BASE_URL=http://192.168.31.90:8000 PRISM_CONTRACT_TOKEN=... uv run --project . pytest -q
cd ../.. && git add contracts scripts docs AGENTS.md
git commit -m "docs(contracts): Phase 2 契约快照、parity 与部署约束"
```

Expected: Java 全绿；Python 仅剩已知 flake；契约测试两端全绿。

---

## Phase 3 起的后续计划（各自单独成计划）

| Phase | 范围 | 进入条件 |
|---|---|---|
| 3a | Run/Message/ToolCall/SSE/取消/恢复/Provider/本地工具 | Phase 2 五服务健康 + 契约测试绿 |
| 3b | 上下文装配/裁剪/压缩、轨迹、模型档案、标题 | 3a 绿 |
| 4 | Workspace/索引/检索/文件工具/审批 + V1.5 命名工作区（Python 先行） | 3b 绿 |
| 5 | MCP Client | 4 绿 |
| 6 | Skills 与剩余端点 | 5 绿 |
| 7 | 全量契约 + parity + 双 UI E2E + 隔离/恢复 | 1–6 绿 |

---

## 自检记录

- **Spec 覆盖**：§6 拓扑（Task 5）、§9 契约（Task 1/6）、§12 容器与卷（Task 2–5）、§13 契约测试（Task 1/4/5）均有对应任务；SSE 反代配置在 Task 4 Step 5 有探针，但**真正的流式验收属于 Phase 3**（此时还没有 Run 接口），已在文中标注。
- **步骤扫描**：每个 Step 只有一类可检查结果（构建成功 / 断言通过 / 命令输出匹配）；Dockerfile 与 Compose 给出完整可复制内容，因为它们是"精确文案"而非算法。
- **类型一致性**：`PRISM_CONTRACT_BASE_URL`/`PRISM_CONTRACT_UI_BASE_URL`/`PRISM_CONTRACT_TOKEN` 在 Task 1 定义、Task 2–6 复用；服务名与端口在 Task 5 定义、Task 6 引用。
- **Review Focus**：五条分别落在 Task 2（`localhost`）、Task 4（SSE 缓冲、SPA 回退）、Task 5（同镜像、卷权限）。
- **比例**：计划以编排与验证为主，未展开 Phase 3 的运行时实现。
