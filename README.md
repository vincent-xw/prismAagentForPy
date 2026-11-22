# PrismAgentKit（Python + UI）

本仓库是 **PrismAgentKit 的 Python 重构版本**，也是面向 Python 生态与本地运行场景重新设计的 Agent Runtime 与客户端工作台。

它不是 Node.js 版本的逐行转写，也不追求现有 URL、DTO 或 SQLite 表结构兼容。Python 版保留 PrismAgentKit 的核心思想：Session、Run、消息与工具调用历史、可恢复执行、持久事件和明确的工具边界，再按 Python 的类型系统、异步模型重新设计协议。Vue UI 则作为独立客户端，通过 HTTP 与 SSE 接入本地 Core。

> **Node.js 原版**：链接待项目作者补充。后续会在本节嵌入 Node.js 仓库，作为功能迁移、行为对齐和兼容性比较的上游参考。

## 仓库结构

```text
.
├── scripts/dev.sh         # 本地前后端 DEV 启动器
├── backend/               # Python Agent Core、Runtime、API、SQLite
├── ui/                    # Vue 3 会话工作台与 API/SSE 客户端
├── docs/superpowers/      # 技术设计、实施计划与验证记录
├── AGENTS.md              # 全仓库协作与迁移边界
└── README.md              # Monorepo 总览
```

## 当前能力

**Python Backend**

- FastAPI BFF、SQLite 持久化、Alembic Schema 管理。
- Session / Run / Message / ToolCall / RunEvent 领域与 API。
- 自研 `SimpleAgentEngine`，支持 OpenAI-compatible 流式模型调用。
- 进程内本地工具、外部宿主回填的远端工具、多工具循环。
- SSE 持久事件重放与临时增量、取消、超时、进程恢复。

**Vue UI**

- 会话工作台、连续对话、Run 与 ToolCall 执行详情。
- 三步连接引导、API Token 会话级保存、只读工具目录。
- 浅色 / 深色 / 跟随系统主题与响应式侧边说明面板。
- 基于真实 HTTP 契约与 SSE 事件，不以 Mock 冒充后端能力。

当前**不包含**：MCP Client、Workspace、RAG、多 Agent、LangChain、LangGraph、LangSmith、独立 Worker、Redis、消息队列或分布式部署。

## 快速开始

### 一键启动 DEV

先安装 [uv](https://docs.astral.sh/uv/)、Node.js `^22.13.0 || >=24.0.0` 与 pnpm `11.9.0`，然后在仓库根目录执行：

```bash
./scripts/dev.sh
```

首次运行会自动从示例创建 `backend/.env` 与 `ui/.env`。请先在 `backend/.env` 中填写 API Token 和模型配置，记住该 Token 供 UI 首次连接时使用，再次运行脚本；脚本会同步依赖、执行 SQLite 迁移、等待 Backend 健康后启动 UI。UI 默认连接 `http://127.0.0.1:8000`，开发页面为 `http://127.0.0.1:3000`，按 `Ctrl+C` 会同时停止两端。

可使用 `BACKEND_PORT`、`UI_PORT` 覆盖默认端口；依赖已准备好时可用 `SKIP_DEPENDENCY_INSTALL=1` 跳过安装检查。完整参数见 `./scripts/dev.sh --help`。

### Backend

```bash
cd backend
uv python install 3.12
uv sync
cp .env.example .env
uv run alembic upgrade head
uv run uvicorn prism_agent_kit.main:app --host 127.0.0.1 --port 8000 --reload
```

至少需要在 `backend/.env` 中配置 API Token、模型名、模型 API Key、上下文窗口、输出预算与 tiktoken encoding。完整配置、HTTP 接口和质量命令见 `backend/README.md`。

### UI

```bash
cd ui
pnpm install --frozen-lockfile
cp .env.example .env
pnpm dev
```

`ui/.env` 默认连接 `http://127.0.0.1:8000`，开发服务运行在 `http://127.0.0.1:3000`。完整使用范围、测试与部署说明见 `ui/README.md`。

## 文档

- `backend/README.md`：后端配置、接口、数据库与命令。
- `ui/README.md`：UI 启动、联调、测试与部署边界。
- `docs/superpowers/specs/`：Core 与 UI 技术设计。
- `docs/superpowers/plans/`：实施计划。
- `docs/superpowers/references/`：验证记录。

## 与 Node.js 版本的关系

- Python Backend 是长期重构目标；Node.js 版本是迁移期的功能、测试和行为参考。
- Vue UI 按新客户端设计实现，不承诺复用 Node.js 版本的页面结构或前端组件。
- 迁移功能前先核对 Node.js 对应实现、测试与文档，不根据接口名称猜测语义。
- 与 Node.js 版本有意的行为差异，需要记录原因、影响范围和兼容策略。
- Node.js 仓库地址由项目作者确认后补充到本文档顶部；在此之前不预设未确认链接。

## 当前状态

- [x] Python 标准后端骨架、Core、SQLite、SSE、工具与恢复机制
- [x] Vue 3 会话工作台、连接引导、主题与测试体系
- [x] 前后端分目录的 Monorepo 结构
- [x] Core 与 UI 技术设计、实施计划及验证记录
- [ ] 补充 Node.js 原版仓库链接
- [ ] 后续按明确范围迁移 MCP、Workspace 等能力
