# PrismAgentKit Backend（Python）

本目录是 **PrismAgentKit 的 Python 后端**，也是面向 Python 生态重新设计的本地 Agent Runtime。

它不是 Node.js 版本的逐行转写，也不追求现有 URL、DTO 或 SQLite 表结构兼容。Python 版保留 PrismAgentKit 的核心思想：Session、Run、消息与工具调用历史、可恢复执行、持久事件和明确的工具边界，再按 Python 的类型系统、异步模型和本地运行场景重新设计协议。

当前已完成首个 **Python Agent Core** 迁移：FastAPI BFF、SQLite 持久化、OpenAI-compatible 模型调用、本地/远端工具循环、SSE 事件流、取消与重启恢复。客户端位于 `../ui/`，通过 HTTP 与 SSE 接入本后端。

> **Node.js 原版**：链接由项目作者确认后补充在仓库根 `README.md`，本后端文档不自行预设上游地址。

## 当前能力

- 创建 Session，在 Session 内异步创建和执行 Run。
- 使用 SQLite 保存 Session、Run、Message、ToolCall 和持久化 RunEvent。
- 通过 OpenAI-compatible Chat Completions 接口流式调用模型。
- 聚合文本、reasoning 和多个工具调用增量。
- 支持 Python 进程内本地工具，以及由外部宿主回填结果的远端工具。
- 远端结果校验 `input_digest`，重复提交幂等，冲突结果拒绝覆盖。
- SSE 合并持久事件重放与临时文本增量；终态 Run 可有限重放。
- 支持取消、远端工具超时、进程中断恢复和最大步数限制。
- 在完整 assistant/tool 消息组边界裁剪上下文，不删除 SQLite 历史。
- 非测试环境强制 API Token；模型密钥不写入数据库、日志或 SSE。

当前后端**不包含**：MCP Client、Workspace、RAG、多 Agent、LangChain、LangGraph、LangSmith、独立 Worker、Redis、消息队列或分布式部署。

## 技术栈

- Python 3.12
- [uv](https://docs.astral.sh/uv/)：Python、依赖与虚拟环境管理
- FastAPI + Uvicorn：本地 HTTP API 与 SSE
- Pydantic v2 + pydantic-settings：协议模型与配置
- SQLAlchemy 2 Async + `aiosqlite`：异步 SQLite 访问
- Alembic：数据库迁移
- OpenAI Python SDK：OpenAI-compatible 模型接入
- `sse-starlette`：SSE 输出
- `tiktoken`：显式 token 预算估算
- pytest + Ruff + mypy：测试、格式和静态类型检查

## 架构

```text
FastAPI Routes
    -> Application Services / Unit of Work
    -> RunWorker
    -> SimpleAgentEngine
    -> ModelProvider / ToolRegistry
    -> SQLAlchemy Async -> SQLite
```

FastAPI 只承担本地 BFF；事务由 Application Service / Unit of Work 管理，路由不直接实现 Agent 循环或数据库事务。`SimpleAgentEngine` 通过 `AgentEngine` 接口隔离，后续可按需接入 LangGraph 等实现，而不改变 Session、Run、Message、ToolCall 和事件协议。

## 快速开始

### 1. 安装依赖

```bash
uv python install 3.12
uv sync
```

`pyproject.toml` 默认使用清华 PyPI 镜像：

```text
https://pypi.tuna.tsinghua.edu.cn/simple
```

如需临时覆盖镜像，可设置 `UV_DEFAULT_INDEX`，或修改 `pyproject.toml` 中的 `[[tool.uv.index]]`。

### 2. 配置本地环境

```bash
cp .env.example .env
```

然后编辑 `.env`，至少补齐：

- `PRISM_AGENT_KIT_API_TOKEN`：非 `test` 环境必填；健康检查不要求鉴权。
- `PRISM_AGENT_KIT_MODEL_NAME`
- `PRISM_AGENT_KIT_MODEL_API_KEY`
- `PRISM_AGENT_KIT_MODEL_CONTEXT_WINDOW`
- `PRISM_AGENT_KIT_MODEL_MAX_OUTPUT_TOKENS`
- `PRISM_AGENT_KIT_MODEL_TOKEN_ENCODING`

对接 DeepSeek 或其他 OpenAI-compatible 服务时，同时配置 `PRISM_AGENT_KIT_MODEL_BASE_URL`。上下文窗口必须大于最大输出 token 与 `PRISM_AGENT_KIT_CONTEXT_SAFETY_MARGIN_TOKENS` 之和；缺失或非法配置会直接导致启动失败，不会静默兜底。

模型 HTTP 客户端遵循 `HTTP_PROXY`、`HTTPS_PROXY` 与 `ALL_PROXY` 环境变量；依赖已包含 `httpx[socks]`，可直接使用 `socks5://` 代理。

模型密钥只从环境变量读取，不写入 SQLite、日志、SSE 或错误响应。`.env` 不应提交到 Git。

### 3. 初始化数据库

```bash
uv run alembic upgrade head
```

默认数据库位于平台用户数据目录下的 `prism-agent-kit/agent.db`。可通过 `PRISM_AGENT_KIT_DATABASE_PATH` 指定绝对路径。SQLite 启用 WAL、外键和 busy timeout，并通过数据库文件进程锁限制同一路径只运行一个实例。

### 4. 启动服务

```bash
uv run uvicorn prism_agent_kit.main:app --host 127.0.0.1 --port 8000 --reload
```

- API 文档：<http://127.0.0.1:8000/docs>
- 健康检查：<http://127.0.0.1:8000/api/v1/health>

除健康检查外，请求需携带：

```http
Authorization: Bearer <PRISM_AGENT_KIT_API_TOKEN>
```

内置系统 Prompt 为 `default@1`。创建 Run 时可省略 `prompt_ref`，此时使用 `PRISM_AGENT_KIT_DEFAULT_PROMPT_REF`；显式指定时必须使用 `name@version`。

## HTTP 接口

统一前缀为 `/api/v1`：

| Method | Path | 说明 |
|---|---|---|
| `GET` | `/health` | 健康检查 |
| `POST` | `/sessions` | 创建 Session |
| `GET` | `/sessions` | 列出 Session |
| `GET` | `/sessions/{session_id}` | 获取 Session |
| `GET` | `/sessions/{session_id}/messages` | 获取会话消息 |
| `POST` | `/sessions/{session_id}/runs` | 创建并异步启动 Run |
| `GET` | `/runs/{run_id}` | 获取 Run |
| `GET` | `/runs/{run_id}/events` | 订阅 SSE 事件流 |
| `POST` | `/runs/{run_id}/tool-calls/{call_id}/result` | 回填远端工具结果 |
| `POST` | `/runs/{run_id}/cancel` | 取消 Run |
| `GET` | `/tools` | 列出已注册工具及 Schema |

在 `test` 环境中，`GET /runs/{run_id}/events?once=true` 可用于有界重放已有事件；非测试环境不接受 `once`。

## 常用命令

```bash
make install      # 安装依赖
make dev          # 启动开发服务
make lint         # Ruff 检查与格式校验
make typecheck    # mypy 类型检查
make test         # pytest
make check        # lint、typecheck、test
```

不使用 `make` 时：

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pytest
```

数据库结构由 Alembic 管理：

```bash
uv run alembic revision --autogenerate -m "describe change"
uv run alembic upgrade head
```

迁移 URL 从 `PRISM_AGENT_KIT_DATABASE_PATH` 解析，不需要在 `alembic.ini` 中重复维护。

## 目录结构

```text
.
├── backend/
│   ├── alembic.ini           # Alembic 配置
│   ├── migrations/           # 数据库迁移脚本
│   ├── pyproject.toml        # Python 项目元数据、依赖和工具配置
│   ├── src/prism_agent_kit/
│   │   ├── api/              # FastAPI 路由、鉴权、错误映射
│   │   ├── application/      # 应用服务、事件总线、Worker、容器
│   │   ├── core/             # 领域模型、Agent 循环、Prompt、上下文
│   │   ├── db/               # ORM、Repository、Unit of Work
│   │   ├── providers/        # OpenAI-compatible 模型适配
│   │   ├── tools/            # 工具契约、注册、执行
│   │   └── main.py           # FastAPI 应用入口
│   └── tests/                # 单元、集成和端到端测试
├── ui/                       # Vue 3 客户端
└── docs/superpowers/         # Core 与 UI 技术设计、计划和验证
```

## 与 Node.js 版本的关系

- Python 版本是长期重构目标；Node.js 版本是迁移期的功能、测试和行为参考。
- 迁移功能前先核对 Node.js 对应实现、测试与文档，不根据接口名称猜测语义。
- 与 Node.js 版本有意的行为差异，需要记录原因、影响范围和兼容策略。
- Node.js 仓库地址由项目作者确认后补充到仓库根 `README.md`；在此之前不预设未确认链接。

## 当前状态

- [x] 标准 Python 后端骨架、配置、日志、CORS 和质量链路
- [x] SQLite 数据模型、Alembic 迁移、Repository 和原子事务
- [x] Session / Run / Message / ToolCall / RunEvent API
- [x] 自研 Agent 循环、OpenAI-compatible 流式模型接入
- [x] 本地工具、远端工具、取消、超时和重启恢复
- [x] SSE 实时输出、持久事件重放、API 鉴权和错误边界
- [x] Python Agent Core 技术设计与实施计划
- [ ] 补充 Node.js 原版仓库链接
- [ ] 后续按明确范围迁移 UI、MCP、Workspace 等能力
