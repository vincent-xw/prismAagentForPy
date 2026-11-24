# PrismAgentKit MCP Client 设计（迁移第三部分 · V1.2）

- 状态：待评审
- 日期：2026-11-24
- 关联：[Python Agent Core 设计](2026-11-22-python-agent-core-design.md)、[工作区与文件工具设计](2026-11-23-workspace-file-tools-design.md)
- 上游参考：`agent-kit/examples/agent-runtime-bff`（MCP 相关模块 22 个文件，约 6.7k 行；依赖 `@modelcontextprotocol/client`、`@modelcontextprotocol/server` 2.4.0）

## 0. 已确认的结论

- 第三版拆成两期：**V1.2 = MCP Client**，V1.3 = Skills。
- MCP 客户端使用 **MCP 官方 Python SDK**（PyPI `mcp`，当前 2.3.0，MIT，Python ≥ 3.10）。这是一次**有意的依赖约束变更**：`AGENTS.md` 现写"不引入 MCP SDK"，与上游对齐后需改写该条，并说明原因与影响。
- 本项目是"用 Python 重做 Agent Runtime"的实验项目，目标是能力面逐步对齐上游，而不是日常易用性打磨。
- **MCP 工具一律审批**：上游对 MCP 采用固定 `always` 策略，V1.2 对齐，并把现有"仅文件写入"的审批通道泛化为通用工具审批。

## 1. 背景与意图

第二部分让 Agent 能在本地工作区读写文件；但它只能调用我们自己内置的 4 个工具。上游 Runtime 的扩展方式是 **MCP（Model Context Protocol）**：把外部进程/服务声明的工具接进同一个工具循环。V1.2 要让 Python Core 具备同样的能力——**作为 MCP Client**（不是 MCP Server），把用户配置的 MCP 服务的工具接进现有 `ToolRegistry`，与内置工具在同一次 Run 里无差别调用。

这验证的是 Python 版 Runtime 的核心命题：工具边界是否足够通用，能否在不改领域模型与状态机的前提下接入外部能力。

## 2. 目标

### 2.1 功能目标

1. 配置多个 MCP 服务（`stdio` 与 `Streamable HTTP` 两种传输），启用/停用/删除。
2. 应用启动时连接已启用服务；单个服务失败不影响应用启动，也不影响其他服务。
3. 握手后 `tools/list` 拉取工具，注册进 `ToolRegistry`，模型可见、可调用。
4. 调用 `tools/call`，把结果转成 JSON；失败返回稳定错误码，不打断整轮其他工具。
5. 工具名带服务前缀避免冲突；同一服务重连后刷新工具集合。
6. UI 提供 MCP 服务页：列表、状态、工具目录、启停/重连、增删改（不含凭据加密库）。
7. 所有 MCP 工具调用前必须经用户审批（对齐上游 `always`）；文件写入审批行为保持不变。

### 2.2 工程目标

- 只扩展既有接口：`ToolRegistry` 增加运行期注册/注销；引擎"每次 Run 取一次工具 schema"的行为不变。
- 连接/协议细节全部收敛在 `application/mcp/`，不进入 Core 领域模型，不改变 Run 状态机。
- 不新增数据库之外的状态源；配置与状态落 SQLite（结构变更带 Alembic 迁移）。
- 继续满足 `ruff check` / `ruff format --check` / `mypy src` / `pytest` 与 UI 三项门禁。

## 3. 非目标

- **不做 MCP Server**（不对外提供工具），不做 Server 托管。
- 不做 MCP 的 `resources`、`prompts`、`roots`、`sampling`、`elicitation`；V1.2 只做 `tools`。
- 不做 OAuth / 浏览器授权流；HTTP 认证只支持静态 Header（值可用环境变量占位）。
- 不做加密凭据库；不把明文密钥写入数据库（见 §7.3）。
- 不做多用户、远端共享实例、公网部署。
- 不做模型可见的"工具热更新"：Run 进行中不改变其工具集合。
- 不做 MCP 工具的自动重试；失败按工具结果回给模型。
- 不做 Skills（V1.3）。

## 4. 反目标

- 把 MCP 协议逻辑写进 `core/engine.py` 或 FastAPI 路由。
- 应用启动被一个坏掉的 MCP 服务拖住或拖崩。
- 用工具名直接暴露原始 MCP 名称导致跨服务重名覆盖。
- 把 MCP 调用失败静默为空结果。
- 在数据库里存明文 Token。

## 5. 约束

- Python 3.12；新增运行时依赖：`mcp>=2.3,<3`（需同步更新 `AGENTS.md`、`backend/pyproject.toml`、README 的"不包含 MCP"表述）。
- SQLite 唯一数据库；配置与状态入 SQLite，Alembic 迁移 `20261124_0005_mcp_servers`。
- 单进程 asyncio：stdio 子进程与 HTTP 会话都由本进程管理，关停时必须回收，不留孤儿进程。
- 工具输入/输出必须是 JSON 可序列化并经 Pydantic 校验；工具异常不透传正文。
- 配置只经 `pydantic-settings` 读取"应用级"配置；MCP 服务清单属于用户数据，存数据库而非 `.env`。

## 6. 方案选择

### 6.1 协议实现（已决策）

| 方案 | 取舍 |
|---|---|
| **官方 `mcp` Python SDK（选中）** | 官方组织维护、与上游 Node SDK 同源，握手/分页/传输/错误类型兜底；代价是新增依赖并改写既有约束 |
| 自研 JSON-RPC 最小客户端 | 零依赖，但要自己处理版本协商、stdio 管道、HTTP 流与错误映射，协议演进要自己跟 |

选官方 SDK：这是实验项目，价值在于验证 Python Runtime 的架构，而不是重写协议层；与上游对齐也便于行为对照。

### 6.2 其余取舍

| 决策点 | 选择与理由 |
|---|---|
| 配置存储 | **SQLite `mcp_servers` 表**。项目约定"状态事实以 SQLite 为准"；JSON 文件会多一个需要加锁/热加载的状态源 |
| 连接时机 | **启动时连接已启用服务 + 手动重连**；不在每次工具调用时懒连接（延迟可预期、错误更早暴露）。失败只记录状态 |
| 工具注册 | `ToolRegistry` 增加 `register`（已有）/`unregister_by_prefix`；服务重连后先注销旧前缀再注册新集合 |
| 工具命名 | `mcp__<server_slug>__<tool_name>`，只保留 `[a-zA-Z0-9_-]`，超长截断并附 6 位哈希；冲突时追加哈希 |
| 审批 | **一律 `always`**（对齐上游）：所有 MCP 工具 `requires_approval=True`，泛化现有审批通道 |
| 结果大小 | 单次 `tools/call` 结果文本上限 200 KB，超出截断并标记；图片/资源内容转元数据，不落正文 |
| 传输范围 | `stdio` + `Streamable HTTP`；SSE 旧传输不做 |

## 7. 总体设计

```text
UI MCP 页
  │ HTTP（同一 API Token）
api/routes/mcp.py（服务 CRUD、状态、工具目录、重连）
  │
application/mcp/
  ├── config_service.py     配置读写（SQLite）、启停、校验
  ├── manager.py            McpServerManager：每个启用的服务一个会话/子进程
  ├── adapter.py            官方 SDK ClientSession → 我们的 ToolDefinition / 结果转换
  ├── naming.py             工具名生成、前缀注销、冲突处理
  └── supervisor.py         启动连接、关停回收、失败状态与重连
db: mcp_servers（迁移 20261123_0005）
tools/registry.py：运行期注册/按前缀注销
core/engine.py：不变（每次 Run 取一次 schema）
```

边界：协议与生命周期只在 `application/mcp/`；路由只做 DTO；`ToolRegistry` 只增加注册/注销能力。

### 7.1 启动与关停

- `ApplicationContainer.start()`：迁移完成后读取 `mcp_servers` 中 `enabled=1` 的行，**并发**连接，每个连接超时 10s；结果写回 `status`（`connected|error|disabled`）与 `last_error`（脱敏）。
- `stop()`：先关闭全部 MCP 会话，再停 Worker/数据库；`stdio` 子进程必须 await 退出，超时则 terminate。
- 启动连接失败**不抛异常**，只记状态与日志（避免一个坏配置让整个应用起不来）。

### 7.2 工具发现与调用

- 握手：`initialize`（clientInfo 名称/版本）、校验 `protocolVersion`；`notifications/initialized`。
- 发现：`tools/list` 按 cursor 翻页直到结束；为每个工具生成 `ToolDefinition`（`execution_mode=LOCAL`，handler 走 manager 的调用桥）。
- 调用：`tools/call`，参数原样传递；把 MCP `content[]` 规范化为 JSON：
  - `text` → 字符串；
  - `image`/`audio`/`resource` → `{type, mimeType, size}` 元数据，不内联二进制；
  - `structuredContent` → 原样 JSON。
- 超时：连接 10s；单工具实际生效超时 = `min(工具声明 timeoutMs, MCP_TOOL_TIMEOUT_SECONDS, 全局 TOOL_TIMEOUT_SECONDS)`。MCP 默认 `MCP_TOOL_TIMEOUT_SECONDS=30`，与全局默认一致；想放宽需同时抬高全局上限（引擎现有的 `min(definition, tool_timeout_seconds)` 语义不变）。
- 取消：Run 取消时通过 SDK 的请求取消与上下文传播中断调用。

### 7.3 配置与密钥

`mcp_servers` 列：`id, name(slug 唯一), transport(stdio|http), command, args_json, env_json, url, headers_json, enabled, status, last_error, created_at, updated_at`。

- `env_json` / `headers_json` 的**值支持 `${VAR}` 占位**，连接时从父进程环境解析；未解析的占位直接报配置错误。
- `stdio` 子进程环境 = 必要父环境白名单（`PATH`、`HOME`、`LANG`、`LC_*`、`TMPDIR`，Windows 另含 `SYSTEMROOT`/`PATHEXT`）+ 配置 `env_json` 覆盖；不继承父进程全部环境，避免误带密钥。
- 允许字面量值，但命中密钥形态（`sk-`、长 base64/hex、`Bearer ...`）时拒绝保存。
- 数据库里**不允许存明文密钥**：保存前校验，若值不像 `${VAR}` 且命中常见密钥形态（`sk-`、长 base64 等）则拒绝并提示改用环境变量。
- `last_error` 脱敏（去 Header/Token）。

### 7.4 工具命名与冲突

- slug 由 name 规范化（小写、非字母数字转 `-`）。
- 最终名 `mcp__<slug>__<tool>`；总长 > 64 时截断原名并追加 `__<sha256[:6]>`。
- 同一 slug 下重名（异常情况）追加哈希；注册冲突抛稳定错误，记录日志而非覆盖。

### 7.5 审批（MCP 一律审批，泛化现有通道）

上游对 MCP 工具固定 `always`，V1.2 对齐：**所有 MCP 工具 `requires_approval=True`**，调用前必须用户确认。为此把现有"仅文件写入"的审批通道泛化：

- **引擎判定**：`SimpleAgentEngine` 的挂起条件改为只看 `definition.requires_approval`；全局 `workspace_require_write_approval` 下移到容器构建 `file_write` 时决定其 `requires_approval`，引擎不再读该配置。
- **预览**：`ToolApprovalService.preview` 按工具分支——`file_*` 走原有路径/模式/diff；其他工具返回 `kind="generic"` + 输入 JSON 摘要（限 4 KB），不要求 Run 绑定工作区。
- **执行**：`decide(approve)` 执行后，仅当工具是文件写入且成功时才触发单文件重索引；其他工具只落结果与事件。
- **事件**：`tool.approval_required` 泛化为 `{call_id, tool_name, kind, path?, mode?, bytes?, input_preview?}`；`tool.requested` 对 `requires_approval` 工具一律脱敏为摘要。
- **UI**：审批卡片按 `kind` 渲染——文件显示 diff，通用工具显示格式化输入 JSON；`GET /runs/{id}/tool-calls/{id}/preview` 返回体增加 `kind` 与 `input_preview`。
- 不做服务级/工具级"关闭审批"的配置（与上游一致）。

### 7.6 MCP 工具 Schema 与输入校验

- 不把 MCP 的 JSON Schema 转成 Pydantic 模型（会丢失 `$ref/oneOf/format` 等）：`ToolDefinition` 增加 `input_schema_override: dict[str, JsonValue] | None`，`to_model_schema()` 与 `ToolView` 优先使用它，模型看到的 schema 与服务端声明一致。
- MCP 工具使用 `McpToolInput`（`extra="allow"` 的通用模型）承接参数，适配层按原 dict 转发；我方只校验"顶层是 JSON 对象"，**参数合法性由 MCP 服务端最终裁定**（服务端错误映射为 `MCP_TOOL_ERROR`）。
- 输出统一规范化为 JSON；`output_model` 为空时不额外结构校验（与现有本地工具一致）。

## 8. 数据模型与迁移

```sql
CREATE TABLE mcp_servers (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL UNIQUE,
  transport TEXT NOT NULL,          -- stdio | http
  command TEXT,                     -- stdio
  args_json JSON,                   -- stdio
  env_json JSON,                    -- stdio，值可含 ${VAR}
  url TEXT,                         -- http
  headers_json JSON,                -- http，值可含 ${VAR}
  enabled INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'disabled',  -- disabled|connected|error
  last_error TEXT,
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL
);
```

迁移 `20261124_0005_mcp_servers`；`downgrade` 删表。工具集合不落库（连接时从服务拉取，进程内缓存），避免缓存与服务真实能力不一致。

## 9. HTTP 接口

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/mcp/servers` | 服务列表 + 状态 + 工具数 |
| POST | `/mcp/servers` | 新增服务（校验 transport 必填项、名称唯一、密钥形态） |
| PATCH | `/mcp/servers/{id}` | 更新配置；变更连接参数时自动重连 |
| DELETE | `/mcp/servers/{id}` | 删除并断开 |
| POST | `/mcp/servers/{id}/enable` / `disable` | 启停（disable 断开并注销工具） |
| POST | `/mcp/servers/{id}/reconnect` | 手动重连并刷新工具 |
| GET | `/mcp/servers/{id}/tools` | 该服务的工具目录（名称、描述、输入 schema 摘要） |

`McpServerView`：`{id, name, transport, enabled, status, last_error, tool_count}`；密钥字段永不回显（只回显 `${VAR}` 占位或掩码）。

## 10. UI

- 顶部导航新增「MCP」页（与工作区/设置同级）。
- 服务列表：名称、传输、状态点（已连接/错误/停用）、工具数、`重连` `启停` `删除`。
- 「添加服务」表单：名称、传输（stdio/http）、按传输显示 command/args/env 或 url/headers、审批模式。
- 工具目录：点击服务展开工具列表与输入 schema 摘要（只读）。
- 错误展示：`last_error` 以可复制文本展示；不回显密钥。
- 契约：`zod` 严格校验新 DTO；不补造字段。

## 11. 错误码

新增：`MCP_SERVER_NOT_FOUND`、`MCP_SERVER_UNAVAILABLE`、`MCP_SERVER_BUSY`、`MCP_CONFIG_INVALID`、`MCP_PROTOCOL_ERROR`、`MCP_TOOL_TIMEOUT`、`MCP_TOOL_ERROR`、`MCP_TOOL_NAME_CONFLICT`、`MCP_DISABLED`。
工具调用失败统一走既有 `ToolExecutionResult.failure(code, message)`，不会打断同轮其他工具。

## 12. 测试

- 单元：命名/截断/冲突、配置校验（transport 必填、密钥形态拒绝）、`${VAR}` 解析与缺失报错。
- 集成（真实 SDK）：用官方 `mcp` SDK 在测试里起一个 **stdio 测试服务**（`tools/list` 两个工具 + 一个慢工具 + 一个报错工具），断言：工具注册、调用结果规范化、超时、错误码、按前缀注销、重连刷新。
- 集成（HTTP）：本地起一个 minimal Streamable HTTP 服务，验证握手 + 一次调用；不可用时状态为 `error` 且应用仍启动。
- 生命周期：关停后无子进程残留（检查 pid 退出）；坏配置服务不影响其他服务连接；**有活动 Run 时禁用/重连返回 `MCP_SERVER_BUSY`**。
- 审批：MCP 调用进入 `waiting_for_approval`，批准后执行、拒绝落 `TOOL_REJECTED`；通用预览不含 diff；文件写入审批回归不受影响。
- 取消：取消发生在 MCP 调用执行中时，允许等到工具超时再收敛（记录为已知语义，不做即时中断）。
- API/UI：服务 CRUD、启停、重连、工具目录；UI 契约解析与表单校验。

## 13. 阶段与规模

项目级变更，预计 5 个阶段：

1. **数据与配置**：迁移、仓储、config service、DTO/错误码、`AGENTS.md`/依赖更新。
2. **审批通道泛化**：引擎判定、`ToolApprovalService` 预览/执行/事件、审批 UI 通用卡片（先独立完成，文件写入回归通过）。
3. **协议接入**：`mcp` SDK 适配器（stdio/HTTP）、管理器、命名、生命周期、工具注册/注销、schema 透传。
4. **HTTP + UI**：7 个接口、MCP 页、契约。
5. **测试与验收**：stdio/HTTP 测试服务、生命周期与审批测试、文档与验收脚本。

工作量估计：后端约 1,200–1,600 行（含测试），UI 约 600–800 行。

## 14. 留待构建者决定

- 测试用 stdio 服务的实现方式（官方 SDK `FastMCP` vs 手写 server loop）。
- HTTP 传输的重连退避策略（建议指数退避上限 30s，仅手动重连时重置）。
- 工具目录里 schema 展示的折叠粒度。
- 是否在工具调用结果中保留 MCP 的 `_meta`（建议丢弃，除非 debug）。

## 15. 风险

- SDK 版本演进（2.x）带来 API 变化：锁定 `>=2.3,<3`，适配层集中在一个文件。
- stdio 子进程泄漏：关停与异常路径都要 await 回收，测试覆盖。
- 工具名长度限制：命名函数负责截断与哈希，单测覆盖。
- 大结果/二进制：结果规范化阶段截断，避免撑爆上下文与数据库。
- 一个服务卡住握手：并发连接 + 超时，不阻塞启动。
- 审批泛化触及引擎的挂起条件：必须保证文件写入审批行为完全不变（回归测试覆盖），否则会破坏已上线的写入确认。

---

## 附：改动清单

- `backend/pyproject.toml`：新增 `mcp>=2.3,<3`。
- `AGENTS.md`：改写"不引入 MCP SDK"条目，说明与上游对齐的原因与边界（仅 Client、仅 tools）。
- `README.md` / `backend/README.md`：更新"不包含 MCP"表述与能力清单。
- `backend/src/prism_agent_kit/core/errors.py`、`core/config.py`（`mcp_connect_timeout_seconds`、`mcp_tool_timeout_seconds`、`mcp_max_result_bytes`）。
- `backend/src/prism_agent_kit/db/models.py` + `migrations/versions/20261124_0005_mcp_servers.py`。
- `backend/src/prism_agent_kit/db/repositories/mcp_servers.py` + `db/uow.py`。
- `backend/src/prism_agent_kit/application/mcp/{config_service,manager,adapter,naming,supervisor}.py`。
- `backend/src/prism_agent_kit/tools/registry.py`：运行期注册与按前缀注销。
- `backend/src/prism_agent_kit/tools/contracts.py`：`ToolDefinition.input_schema_override`。
- `backend/src/prism_agent_kit/core/engine.py`：挂起条件改为只看 `requires_approval`（去掉全局写审批开关判断）。
- `backend/src/prism_agent_kit/application/tool_approval_service.py`：预览/执行/事件按工具类型泛化。
- `backend/src/prism_agent_kit/api/schemas.py` / `routes/runs.py`：审批预览 DTO 增加 `kind`、`input_preview`。
- `ui/src/features/runs/RunInspector.vue`、`ui/src/lib/api/{contracts,client}.ts`：通用审批卡片与契约。
- `backend/src/prism_agent_kit/api/routes/mcp.py`、`api/schemas.py`、`api/dependencies.py`、`application/container.py`、`api/router.py`。
- `ui/src/lib/api/{contracts,client}.ts`、`ui/src/features/mcp/*`、`ui/src/app/{modules,router,AppShell}.vue/ts`。
- 测试：`backend/tests/application/mcp/*`、`backend/tests/api/test_mcp.py`、`ui/tests/unit/mcp*.test.ts`。
