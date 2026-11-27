# PrismAgentKit Monorepo 协作说明

## 项目定位与上游关系

- 本仓库是 **PrismAgentKit 的 Python 重构版本**，不是对 Node.js 版本的简单转写。
- Node.js 版本是功能迁移、行为对齐和兼容性验证的上游参考实现。其仓库链接由项目作者确认后在根 `README.md` 中补充；在链接补充前，不要自行猜测或写入上游地址。
- 迁移一个功能前，应先阅读 Node.js 版本对应的实现、测试和文档，再设计 Python 侧接口与实现。无法从上游确认的行为不得凭经验补全。
- 与 Node.js 版本存在刻意差异时，必须在对应变更说明中写清原因、影响范围与兼容策略。
- 新增能力应优先遵循 Python 生态惯例；若为了兼容上游而保留 Node.js 风格，需要说明理由。

## 仓库结构与职责

- `backend/`：Python Agent Core、Runtime、FastAPI BFF、SQLite、迁移与后端测试。
- `ui/`：Vue 3 + TypeScript 客户端，通过 HTTP 与 SSE 接入 `backend/`。
- `docs/superpowers/`：跨前后端的技术设计、实施计划与验证记录。
- 根 `README.md`：Monorepo 总览、启动入口和 Node.js 上游链接位置。
- 修改后端功能时不要顺手重做 UI；修改 UI 时不要绕过既有 HTTP/SSE 契约。跨层协议变更必须同时说明两端影响。

## 迁移边界

- 当前已确认并实现的首个迁移范围是本地 **Python Agent Core**：FastAPI BFF、SQLite 持久化、自研 Agent 循环、工具回填、SSE、取消与恢复。
- UI 已具备首期会话工作台、连接引导、主题和测试体系；除非用户明确要求，不主动扩展新的 UI 业务模块。
- 除非用户明确指定某个新的 Node.js 功能并要求开始迁移，否则只维护当前 Core、基础设施、现有 UI 和文档，不主动扩展上游业务功能。
- 完成用户当前指定的范围后立即停止，不自行进入未获明确授权的迁移阶段（如多 Agent、Workflow 等）。
- 不引入 LangChain、LangGraph、LangSmith、PydanticAI。
- MCP 官方 Python SDK（`mcp`）自 V1.2 起允许使用，但**仅限 MCP Client 与 `tools` 能力**（与上游 Node 版对齐）；扩展到 `resources`/`prompts` 或 Server 端需另立设计。
- Skills 自 V1.3 起支持：只读技能包（`SKILL.md` + references），**不执行 scripts、不做作者化生成、不做技能市场**；脚本执行与项目级目录需另立设计。

## 当前架构约束

- FastAPI 只承担本地 BFF；Agent 循环、事务边界和状态转换位于 Application Service / Core。
- SQLite 是当前唯一数据库；不得在未确认的情况下引入 PostgreSQL、Redis、消息队列或独立 Worker。
- 对外状态事实以 SQLite 中的 Session、Run、Message、ToolCall 和 RunEvent 为准，日志、SSE 和 Trace 不是业务事实源。
- 所有终止 Run 必须闭合 ToolCall；模型可见历史必须能由持久化数据重建。
- 后续 Agent 编排实现通过 `AgentEngine` 接口接入，不改变现有领域模型和 HTTP 协议。
- UI 的 API DTO 与 SSE 解析必须对真实契约做运行时校验，不用 Mock 或对象形状猜测掩盖后端缺口。

## 常用命令

后端命令在 `backend/` 执行：

```bash
cd backend
uv sync
uv run alembic upgrade head
uv run uvicorn prism_agent_kit.main:app --reload
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pytest
```

UI 命令在 `ui/` 执行：

```bash
cd ui
pnpm install --frozen-lockfile
pnpm check
pnpm test
pnpm build
```

若终端环境已安装并约定使用 `rtk`，请按用户全局要求为命令加 `rtk` 前缀。

## 工程约定

- 后端使用 `src` 布局，业务代码放在 `backend/src/prism_agent_kit/`，测试放在 `backend/tests/`。
- 后端对外 HTTP 接口统一挂在 `PRISM_AGENT_KIT_API_PREFIX` 下；当前默认前缀为 `/api/v1`。
- 后端配置只通过 `pydantic-settings` 从环境变量或 `.env` 读取，不在业务代码中散落读取环境变量。
- 不得提交真实密钥、模型凭据、用户数据或生产连接串；只在 `backend/.env.example` 与 `ui/.env.example` 中维护无敏感信息的示例。
- 数据库模型统一继承 `prism_agent_kit.db.base.Base`，结构变更必须附带 Alembic 迁移。
- 后端 I/O 操作使用异步实现；禁止在异步请求路径中调用阻塞式网络、文件或数据库客户端。
- 后端 API 输入输出使用 Pydantic 模型明确描述，不直接暴露 ORM 对象。
- UI 使用 Vue 3、TypeScript、Vite、pnpm 与现有主题和组件约定；新增依赖前先确认现有组件是否足够。
- 默认不做字段兜底。确需兜底时，必须说明触发条件、默认值来源和可观测性方案。
- 后端函数、变量和复杂业务逻辑使用中文注释；标识符保持符合 Python 命名习惯的英文。

## 质量门槛

- 后端提交前至少通过 `ruff check`、`ruff format --check`、`mypy src` 和 `pytest`。
- UI 提交前至少通过 `pnpm check`、`pnpm test` 和 `pnpm build`；涉及浏览器流程时按需运行 Playwright。
- 新功能需要覆盖正常路径、关键边界和错误路径；仅修改文档或目录结构时可不新增测试，但仍需确认命令示例和路径有效。
- 不修复与当前任务无关的问题；发现后单独记录并告知用户。

## Java 后端（backend-java/）

- 定位：与 `backend/` 对齐同一套 HTTP/SSE 契约的独立实现，**不得**通过 HTTP 调用 Python 后端完成业务；两端数据与运行状态完全隔离。
- 构建：JDK 21 + Maven Wrapper（`./mvnw`）。本机默认 JDK 可能不是 21，命令前显式 `JAVA_HOME`。
- 结构：单 Maven 模块，包内强制依赖方向 `api → application → core`；`core` 不得 import Spring/MyBatis/Jackson 注解。
- 对外契约：JSON 一律 snake_case（全局 `SNAKE_CASE`）、时间 ISO-8601 带 `Z`、错误信封 `{error:{code,message,request_id,details}}`；**禁止** `Result<T>` 包装、禁止 camelCase 泄漏、禁止未经评审改字段名/枚举/状态码。
- 数据：MySQL 8.4 + Flyway；时间以 UTC `DATETIME(6)` 存储；DDL 只能通过 `db/migration/V*.sql` 演进，禁止 `clean`。
- 代码风格：显式构造器注入，不用 Lombok、不滥用反射/AOP；复杂并发与事务边界必须写中文注释。
- 测试：`cd backend-java && ./mvnw verify` 必须全绿；集成测试连接服务器 `192.168.31.90` 上的开发库容器（`127.0.0.1:13306` + SSH 隧道），**禁止**使用本机 Docker Desktop。
- 未实现的路由不注册（不要返回假数据）；兼容性状态以 `docs/compatibility/feature-parity.md` 为准，只有真实通过的测试才能标记为已对齐。

## 容器与部署（Phase 2 起）

- 编排入口是根 `docker-compose.yml`；服务名固定为 `backend-python`、`backend-java`、`ui-python`、`ui-java`、`mysql-java`。
- **禁止在本机 Docker Desktop 上构建或运行**：镜像构建、Compose 启停都在 `192.168.31.90` 执行（仓库同步到 `~/prism-agent`）。
- 镜像必须 `linux/amd64`；UI 只构建一次，两个 UI 容器必须引用同一 image tag（用 `docker compose images` 验证 Image ID 相同）。
- UI 的 API 基址只允许运行时注入（`API_TARGET`），不得写进构建产物；浏览器只访问同源 `/api/v1`。
- 两侧数据卷完全隔离；`skills/` 是唯一只读共享挂载。禁止把 MySQL 发布到公网。
- 契约快照在 `contracts/`，重新导出用 `bash scripts/export-openapi.sh`；跨语言断言在 `tests/contract`，不得 import 后端代码。
