# Phase 5 设计：MCP Client（Java 对齐 + 凭据入库）

- 状态：待评审（等待用户批准后写实施计划）
- 日期：2026-11-27
- 前置：Phase 3（Run/SSE/工具回路）、Phase 4（工作区/文件工具/权限档位）已完成
- 参考实现：`backend/src/prism_agent_kit/application/mcp/*`（Python V1.2 MCP Client）

## 1. 目标

1. Java 实现与 Python 同一套 `/mcp/servers` 契约：配置 CRUD、启停、重连、连接状态、工具清单。
2. 支持两种传输：**STDIO**（SDK 拉起子进程）与 **Streamable HTTP**。
3. MCP 工具接入 Run 工具回路：工具名 `mcp__<server>__<tool>`，模型可调用，Java 侧同步执行。
4. **凭据入库（B）**：`env` / `headers` 的值可在 UI 直接填写并明文入库（数据卷 0600），API 只回键名与掩码；`${ENV_VAR}` 占位仍兼容，用于逐步替换 ENV。
5. `backend-java` 镜像安装 Node 22 LTS，STDIO 同时支持 `npx` 与 `uvx`。

## 2. 非目标

- 不做 MCP Server 端、不做 resources/prompts 能力（仅 tools）。
- 不做 OAuth/动态客户端注册；HTTP 只支持静态 headers。
- 不做工具级审批（延续 K-09：档位即策略，MCP 工具默认免审批）。
- 不做 MCP 工具的流式中间结果。

## 3. 依赖与 API（已用 javap 核实）

- `io.modelcontextprotocol.sdk:mcp-core:2.2.0` + `io.modelcontextprotocol.sdk:mcp-json-jackson2:2.2.0`
  （**不用** `mcp` 聚合包，避免它拉入 Jackson 3 与现有 Jackson 2.21 冲突）。
- 传输：
  - STDIO：`new StdioClientTransport(ServerParameters.builder(command).args(list).env(map).build(), jsonMapper)`
  - HTTP：`HttpClientStreamableHttpTransport.builder(url).requestBuilder(HttpRequest.newBuilder().header(k, v)).build()`
- 客户端：`McpClient.sync(transport).requestTimeout(Duration).initializationTimeout(Duration).build()` → `McpSyncClient`
  - `initialize()`、`listTools()`、`callTool(new McpSchema.CallToolRequest(name, args))`、`close()`
- JSON：`io.modelcontextprotocol.json.jackson2.JacksonMcpJsonMapper`（复用 Spring 的 ObjectMapper）。

## 4. 数据模型（Java Flyway `V6__mcp_servers.sql`）

```sql
CREATE TABLE mcp_servers (
  id CHAR(36) PRIMARY KEY,
  name VARCHAR(128) NOT NULL UNIQUE,
  transport VARCHAR(16) NOT NULL,          -- stdio | http
  command TEXT NULL,
  args_json JSON NULL,
  env_json JSON NULL,                       -- 值可含明文（B）
  url TEXT NULL,
  headers_json JSON NULL,                   -- 值可含明文（B）
  enabled TINYINT(1) NOT NULL DEFAULT 0,
  status VARCHAR(16) NOT NULL DEFAULT 'disabled',  -- disabled|connecting|connected|error
  last_error TEXT NULL,
  created_at DATETIME(6) NOT NULL,
  updated_at DATETIME(6) NOT NULL
);
```

Python 侧改动（同阶段）：
- `config_service` 允许 `env`/`headers` 直接携带真实值（不再要求占位），占位 `${VAR}` 继续解析。
- 读取视图：`env_keys`/`header_keys` + `env`/`headers` 的值一律替换为 `"••••"`；PATCH 时值为 `"••••"` 表示保留原值（与模型档案的掩码语义一致）。

## 5. 契约

沿用 Python 已有端点（不改路径）：

| Method | Path |
|---|---|
| GET | `/mcp/servers` |
| POST | `/mcp/servers` |
| PATCH | `/mcp/servers/{id}` |
| DELETE | `/mcp/servers/{id}` (204) |
| POST | `/mcp/servers/{id}/enable` |
| POST | `/mcp/servers/{id}/disable` |
| POST | `/mcp/servers/{id}/reconnect` |
| GET | `/mcp/servers/{id}/tools` |

`McpServerView` 字段：`id, name, transport, command, args, url, enabled, status, last_error, tool_count, env_keys, header_keys, env, headers`（`env`/`headers` 的值为掩码）。错误码复用：`MCP_SERVER_NOT_FOUND(404)`、`MCP_CONFIG_INVALID(422)`、`MCP_SERVER_UNAVAILABLE(502)`、`MCP_SERVER_BUSY(409)`、`MCP_PROTOCOL_ERROR(502)`、`MCP_TOOL_TIMEOUT(504)`、`MCP_TOOL_ERROR(502)`、`MCP_DISABLED(409)`、`MCP_TOOL_NAME_CONFLICT(409)`。

## 6. 连接生命周期（方案 A）

- `McpServerManager`：`@PostConstruct` 连接所有 `enabled=true` 的服务；`enable` → connecting → connected/error；`disable` → 断开并置 disabled；`reconnect` → 先断后连。
- 每个服务一个 `McpSyncClient`（同步 API 跑在专用虚拟线程上，避免阻塞 Tomcat 线程），工具清单在连接成功后缓存并注册到 `ToolRegistry`。
- 失败策略：连接失败置 `error` 并写 `last_error`（只存异常类型与简短消息，不含密钥）；不自动无限重试，`enable/reconnect` 显式重试。
- 应用关闭时 `close()` 所有客户端；stdio 子进程随 transport 关闭。

## 7. 工具执行

- `ToolRegistry` 注册 `mcp__<server>__<tool>`（`ExecutionMode.LOCAL`，`requiresApproval=false`）。
- 命名：`slugify(server.name)` + `mcp__` 前缀，超过 64 字符追加 6 位 sha256 前缀（与 Python `naming.py` 逐字一致）。
- 调用：引擎现有 LOCAL 工具路径 → `McpToolInvoker` → `client.callTool(...)`，超时 30s（`MCP_TOOL_TIMEOUT`）；结果规范化：拼接 text、图片只留 `{type,mimeType,size}`、`isError` → `MCP_TOOL_ERROR`；文本上限 200KB。
- 服务被禁用后若模型仍调用 → `MCP_DISABLED`。
- Python 侧同步调整：`to_tool_definition(..., requires_approval=False)`（K-09），其余不变。

## 8. 镜像与运行时

- `backend-java/Dockerfile`：安装 Node 22 LTS（NodeSource 或官方 tarball），保留 python3 + uv；`npx`/`uvx` 均可用。
- 容器内 `$HOME` 与 `PATH` 需包含 node、npx、uvx；MCP stdio 子进程继承精简环境 + 配置的 env。

## 9. 测试

- Java 单元/集成：配置 CRUD + 掩码回显 + 非法 transport 422；STDIO 连接一个**仓库内自带的最小 MCP stdio 服务器**（Python 编写，输出 JSON-RPC：initialize/tools/list/tools/call），断言 listTools 与 callTool；HTTP 用 JDK `HttpServer` 模拟 Streamable HTTP 的最小交互。
- Python：把现有 MCP 测试更新为“允许明文、掩码回显”；新增 `test_mcp_credentials.py`。
- 契约：`tests/contract/test_mcp.py`（双端 CRUD + 掩码 + tools 列表；默认不真连外部服务）。
- UI：MCP 页增加 env/header 值输入（密码框）与掩码显示。

## 10. 待你确认

1. `env`/`headers` 的掩码值用 `"••••"`（PATCH 时原样回传表示“不修改”）是否可以？
2. MCP 工具延续 K-09 **默认免审批**（Python 也一起改），是否需要保留一个可配置开关？
3. 连接失败不自动重试、只由 `enable/reconnect` 触发，是否接受？
