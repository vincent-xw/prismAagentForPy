# Phase 5 实施计划：MCP Client（Java 对齐 + 凭据入库）

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Java 端补齐 `/mcp/servers` 全契约（stdio + Streamable HTTP、常驻连接、工具接入 Run），并把 MCP 的 env/header 值改为可入库（掩码回显），Python 同步放开明文并保持 `***` 语义。

**Architecture:** 每个已启用服务一个 `McpSyncClient`（官方 SDK 2.2.0），连接成功后把 `mcp__<server>__<tool>` 注册进 ToolRegistry；引擎本地工具派发按前缀分流（workspace / mcp）。配置与状态落 MySQL `mcp_servers`。

**Tech Stack:** Spring Boot 3.5 / JDK 21、`io.modelcontextprotocol.sdk:mcp-core:2.2.0` + `mcp-json-jackson2:2.2.0`、MyBatis-Plus、Flyway；Python FastAPI + 官方 `mcp>=2.3`；契约 pytest+httpx。

**Spec:** `docs/superpowers/specs/2026-11-27-phase5-mcp-client-design.md`

## Global Constraints

- 错误码/状态码**以 Python 为准**：`MCP_CONFIG_INVALID(400)`、`MCP_SERVER_UNAVAILABLE(503)`、`MCP_SERVER_BUSY(409)`、`MCP_TOOL_ERROR(400)`、`MCP_TOOL_TIMEOUT(504)`、`MCP_PROTOCOL_ERROR(502)`、`MCP_DISABLED(409)`、`MCP_SERVER_NOT_FOUND(404)`；工具名冲突用 `INVALID_TOOL_DEFINITION(400)`。
- 掩码固定 `***`；PATCH 整包替换；`***` 表示保留原值；`${VAR}` 占位明文回显。
- 工具名 `mcp__<slug(server)>__<sanitized tool>`，>64 字符追加 6 位 sha256（与 `naming.py` 逐字一致）。
- 有活动 Run（queued/running/waiting_*）时 enable/disable/reconnect/update/delete → 409 `MCP_SERVER_BUSY`。
- MCP 工具默认免审批（K-09）；超时 30s；结果规范化逐字复刻 `adapter.normalize_result`。
- stdio 环境只透传白名单（PATH/HOME/LANG/LC_ALL/TMPDIR）+ 配置 env。
- 依赖只用 `mcp-core` + `mcp-json-jackson2`，不得引入 Jackson 3。

## Review Focus

1. **密钥泄漏**：视图/日志/错误消息出现明文 env/header —— Task 1/2 断言。
2. **掩码误当真实值**：PATCH 回传 `***` 被写成字面量，导致服务认证失效 —— Task 1/2。
3. **子进程泄漏**：禁用/重连/进程退出后 stdio 子进程残留 —— Task 3 断言。
4. **工具名漂移**：Java 与 Python 生成的 `mcp__` 名不一致，模型侧工具对不上 —— Task 3/5 用同一组用例比对命名。
5. **分发错路**：MCP 工具被工作区执行器接走（404 `TOOL_NOT_FOUND`）或工作区工具被 MCP 接走 —— Task 4。

---

## 文件结构

```text
backend/src/prism_agent_kit/application/mcp/{config_service,manager,adapter}.py   # 允许明文、掩码/免审批
backend/tests/application/mcp/test_mcp_credentials.py                              # 新增

backend-java/src/main/resources/db/migration/V6__mcp_servers.sql
backend-java/src/main/java/com/prism/agent/
├── core/domain/{McpServer.java,McpStatus.java}
├── persistence/{entity/McpServerEntity,mapper/McpServerMapper,repository/{McpServerRepository,MyBatisMcpServerRepository}}
├── application/mcp/{McpConfigService.java,McpConnectionManager.java,McpToolInvoker.java,McpToolNaming.java}
├── tools/LocalToolInvoker.java（新增，替换 engine 里硬编码）
├── api/dto/McpViews.java、api/controller/McpController.java
└── engine/SimpleAgentEngine.java（dispatchLocalTools 改成分发）

tests/contract/test_mcp.py
docs/compatibility/feature-parity.md、AGENTS.md
```

---

### Task 1: Python 允许明文凭据（契约先行）

**Files:** `backend/src/prism_agent_kit/application/mcp/config_service.py`、`backend/tests/application/mcp/test_mcp_credentials.py`

**Interfaces:**
- `McpConfigService.create/update` 接受 `env`/`headers` 的明文值（不再因“非占位”拒绝）；`${VAR}` 照旧解析为环境值。
- 视图：`env`/`headers` 中非占位值统一显示 `***`；占位符原样显示。

- [ ] **Step 1: 写失败测试**

```python
async def test_plain_secret_is_stored_and_masked(service, client):
    created = await client.post("/api/v1/mcp/servers", json={..., "transport": "http",
        "url": "https://mcp.example.com/mcp", "headers": {"Authorization": "Bearer sk-demo"}})
    assert created.json()["headers"] == {"Authorization": "***"}
    assert "sk-demo" not in created.text

async def test_patch_masked_value_keeps_original(service, client):
    ... # PATCH headers {"Authorization": "***"} 后再次 GET 仍为 ***，且内部值未变
```

- [ ] **Step 2: 运行确认失败**：`cd backend && uv run pytest -q tests/application/mcp/test_mcp_credentials.py`
- [ ] **Step 3: 实现**：移除对明文值的拒绝；`_mask` 仅对非 `${...}` 值替换为 `***`；还原逻辑把 `***` 映射回旧值。
- [ ] **Step 4: 运行确认通过** + `uv run pytest -q tests/application/mcp`
- [ ] **Step 5: 提交** `git commit -am "feat(backend): MCP env/header 允许明文入库并掩码回显"`

---

### Task 2: Java V6 表与配置 API

**Files:** `V6__mcp_servers.sql`、`core/domain/{McpServer,McpStatus}.java`、entity/mapper/repository、`application/mcp/McpConfigService.java`、`api/dto/McpViews.java`、`api/controller/McpController.java`、`src/test/java/com/prism/agent/api/McpConfigApiTest.java`

**Interfaces:**
- `McpServer(id, name, transport, command, args, url, enabled, status, lastError, toolCount, env, headers, createdAt, updatedAt)`
- `McpViews.Server` 输出见设计 §5；`env`/`headers` 掩码 `***`
- 端点与错误码同设计 §5；活动 Run 时 409

- [ ] **Step 1: 写失败测试**：CRUD、掩码回显、`***` 保留、非法 transport 400、重名 400、活动 Run 409
- [ ] **Step 2: 运行确认失败（404）**
- [ ] **Step 3: 实现**：Flyway `V6`（name UNIQUE、slug 由服务端计算并校验唯一）；PATCH 整包替换；密钥值不写日志
- [ ] **Step 4: 运行确认通过**：`./mvnw -Dtest=McpConfigApiTest test`
- [ ] **Step 5: 提交** `git commit -am "feat(java): MCP 配置表与 /mcp/servers API"`

---

### Task 3: Java 连接管理与工具注册

**Files:** `application/mcp/{McpConnectionManager,McpToolNaming,McpToolInvoker}.java`、`tools/ToolRegistry.java`（重名报错）、`src/test/java/com/prism/agent/application/McpConnectionTest.java`

**Interfaces:**
- `McpConnectionManager.enable(id)/disable(id)/reconnect(id)/toolsOf(id)`；状态机 disabled→connecting→connected|error
- `McpToolNaming.fullName(serverName, toolName)`（逐字复刻 Python）
- `McpToolInvoker.invoke(serverId, toolName, args)` → 规范化 JSON
- `ToolRegistry.register` 重名抛 `ApiException(INVALID_TOOL_DEFINITION, 400)`

- [ ] **Step 1: 写失败测试**：用 `backend/tests/support/mcp_stdio_server.py`（`uv run python` 启动）断言 listTools 含 echo/slow/boom、callTool echo 返回文本、命名与 Python 一致；HTTP 用 `tests/support/mcp_http_server.py` 起本地服务断言连接与工具
- [ ] **Step 2: 运行确认失败**
- [ ] **Step 3: 实现**：`StdioClientTransport(ServerParameters.builder(cmd)...)`、`HttpClientStreamableHttpTransport.builder(url).requestBuilder(...)`；`McpClient.sync(...).build()`；`initialize()` 在虚拟线程执行；禁用/关闭时 `close()` 并确认子进程退出
- [ ] **Step 4: 运行确认通过**：`./mvnw -Dtest=McpConnectionTest test`
- [ ] **Step 5: 提交** `git commit -am "feat(java): MCP 连接管理器与工具注册"`

---

### Task 4: 引擎本地工具分发

**Files:** `tools/LocalToolInvoker.java`、`core/engine/SimpleAgentEngine.java`、`src/test/java/com/prism/agent/application/LocalToolDispatchTest.java`

**Interfaces:**
- `LocalToolInvoker.invoke(Run run, ToolCall call, Workspace workspace)`：`mcp__` 前缀 → `McpToolInvoker`；其余 → `WorkspaceToolExecutor`
- 引擎 `dispatchLocalTools` 改调 `LocalToolInvoker`

- [ ] **Step 1: 写失败测试**：注册一个假的 `mcp__demo__echo` 工具，引擎执行后 tool 消息内容来自 MCP invoker；工作区 `file_write` 仍走工作区执行器；未知工具 → 404
- [ ] **Step 2: 运行确认失败**
- [ ] **Step 3: 实现**：分发按前缀；MCP 调用异常映射错误码；保持 Run 回队语义
- [ ] **Step 4: 运行确认通过**：`./mvnw verify`
- [ ] **Step 5: 提交** `git commit -am "feat(java): 本地工具按前缀分发（workspace/mcp）"`

---

### Task 5: 契约与 UI 验证

**Files:** `tests/contract/test_mcp.py`、`contracts/openapi/prism-agent-api.yaml`（重导出）、`ui/src/features/mcp/McpPage.vue`（确认已有输入即可）

**Interfaces:**
- 契约用例：CRUD + 掩码（`***`）+ `tools` 列表 + 非法 transport 400 + 重名 400
- UI 已支持 env/headers 多行输入与“*** 保持原值”，只补一条 `save` 透传测试

- [ ] **Step 1: 写用例**；**Step 2: 对 Python 红/绿**；**Step 3: 导出快照**；**Step 4: 双端跑** `pytest test_mcp.py -q`（8000/8001）；**Step 5: 提交**

---

### Task 6: 部署与 E2E

**Files:** `docs/compatibility/feature-parity.md`、`AGENTS.md`

- [ ] **Step 1: 重建镜像** `docker compose build backend-python backend-java`（Java 已含 Node/uvx，验证 `npx --version`、`uvx --version`）
- [ ] **Step 2: E2E（Python 与 Java 各一遍）**
  - stdio：用仓库自带测试服务（command=`python`/`uv`，args=`backend/tests/support/mcp_stdio_server.py`，不依赖公网），enable → `tools` 非空 → 建会话绑定工作区 → 让模型调用 `mcp__<server>__echo` → tool 消息返回文本；
  - http：指向 `tests/support/mcp_http_server.py` 的 URL，同样走一遍。
- [ ] **Step 3: 全量门槛**：Python `pytest/ruff/mypy`；Java `verify`；UI `check/test/build`
- [ ] **Step 4: parity 更新** MCP Client 行 → Contract Passed；AGENTS 记录“MCP 凭据可入库、掩码 ***”
- [ ] **Step 5: 提交** `git commit -am "docs: Phase 5 MCP 收尾与 parity"`

---

## 自检记录

- **Spec 覆盖**：§4 数据/凭据 → Task 1/2；§6 生命周期 → Task 3；§7 执行/命名 → Task 3/4；§9 测试 → Task 1–5；§8 镜像已在 Phase 2 具备 → Task 6 仅验证。
- **Review Focus**：泄漏与掩码 → Task 1/2；子进程 → Task 3；命名 → Task 3/5；分发 → Task 4。
- **类型一致**：`McpServer` 字段两端同名；掩码常量 `"***"` 两处一致；工具名前缀 `mcp__` 一致。
- **比例**：6 个任务，未展开实现体；SDK 类名已用 javap 核实（`McpClient.sync`/`StdioClientTransport`/`HttpClientStreamableHttpTransport`）。
