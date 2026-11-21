# PrismAgentKit（Python）

PrismAgentKit 的 Python 重构版本。本项目在 Python 生态中延续 PrismAgentKit 的 Agent 运行时设计，并逐步迁移原有能力。

当前仓库仅处于初始化阶段，已完成标准 Python 后端骨架、基础配置、数据库迁移基座与质量检查链路。本次初始化**不包含任何 Node.js 功能迁移**；后续功能需逐项明确范围后再启动。

> **Node.js 原版**：链接待项目作者补充。后续会在本节接入 Node.js 实现，作为功能迁移、行为对齐和兼容性比较的上游参考。

## 技术栈

- Python 3.12
- [uv](https://docs.astral.sh/uv/)：依赖与虚拟环境管理
- FastAPI + Uvicorn：HTTP API 服务
- Pydantic Settings：环境配置
- SQLAlchemy 2（异步）+ asyncpg：数据库访问
- Alembic：数据库迁移
- pytest + Ruff + mypy：测试、格式化、静态检查与类型检查

## 快速开始

### 1. 安装 Python 与依赖

```bash
uv python install 3.12
uv sync
```

`pyproject.toml` 已将默认 PyPI 源配置为清华镜像：

```text
https://pypi.tuna.tsinghua.edu.cn/simple
```

如果所在网络无法访问该镜像，可在执行 `uv` 命令时通过 `UV_DEFAULT_INDEX` 临时覆盖，或修改 `pyproject.toml` 中的 `[[tool.uv.index]]`。

### 2. 配置本地环境

```bash
cp .env.example .env
```

按实际环境修改 `.env`。所有应用配置均使用 `PRISM_AGENT_KIT_` 前缀。

### 3. 启动开发服务

```bash
uv run uvicorn prism_agent_kit.main:app --reload
```

- API 文档：<http://127.0.0.1:8000/docs>
- 健康检查：<http://127.0.0.1:8000/api/v1/health>

## 常用命令

```bash
make install      # 安装依赖
make dev          # 启动开发服务
make lint         # Ruff 检查与格式校验
make typecheck    # mypy 类型检查
make test         # pytest
make check        # 一次执行 lint、typecheck、test
```

不使用 `make` 时，可直接运行：

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pytest
```

## 数据库迁移

默认数据库为本地 PostgreSQL。创建或升级数据库结构：

```bash
uv run alembic revision --autogenerate -m "describe change"
uv run alembic upgrade head
```

迁移 URL 从应用配置 `PRISM_AGENT_KIT_DATABASE_URL` 读取，不需要在 `alembic.ini` 中重复维护。

## 目录结构

```text
.
├── AGENTS.md                 # 仓库协作与 Agent 开发约定
├── alembic.ini               # Alembic 配置
├── migrations/               # 数据库迁移脚本
├── pyproject.toml            # 项目元数据、依赖和工具配置
├── src/prism_agent_kit/
│   ├── api/                  # HTTP 路由
│   ├── core/                 # 配置、日志等基础设施
│   ├── db/                   # 数据库引擎、会话与模型基类
│   └── main.py               # FastAPI 应用入口
└── tests/                    # 自动化测试
```

## 与 Node.js 版本的迁移约定

- Python 版本是长期重构目标，Node.js 版本是迁移期的行为参考。
- 功能迁移应同时核对上游实现、测试与边界行为，避免仅根据接口名称推断语义。
- 有意的行为差异必须记录原因与兼容影响。
- Node.js 仓库链接会由项目作者在合适时机补充到本文档顶部；在此之前，仓库内不预设未确认的地址。

## 当前状态

- [x] 建立 `src` 布局与 FastAPI 应用入口
- [x] 配置环境变量、日志、CORS、异步数据库会话
- [x] 接入 Alembic 迁移基座
- [x] 配置国内 PyPI 镜像
- [x] 建立 pytest、Ruff、mypy 质量链路
- [ ] 补充 Node.js 原版仓库链接

具体 Agent 能力迁移尚未开始，将按功能逐项确认范围后推进。
