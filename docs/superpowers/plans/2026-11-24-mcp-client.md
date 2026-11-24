# MCP Client (V1.2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 Python Core 作为 MCP Client 连接用户配置的 MCP 服务，把 `tools` 接进现有工具循环；所有 MCP 工具调用前必须经用户审批。

**Architecture:** 官方 `mcp` Python SDK（v2 高层 `Client`）负责协议；`application/mcp/` 负责配置、连接生命周期、工具适配与命名；配置存 SQLite（`mcp_servers`）；审批通道从"仅文件写入"泛化为按工具类型分支，MCP 工具一律 `requires_approval=True`。

**Tech Stack:** Python 3.12、`mcp>=2.3,<3`、FastAPI、SQLAlchemy 2 Async + aiosqlite、Alembic、Pydantic v2；Vue 3 + zod + Vitest。

**Spec:** `docs/superpowers/specs/2026-11-24-mcp-client-design.md`

## Global Constraints

- 新增运行时依赖仅 `mcp>=2.3,<3`；同步改写 `AGENTS.md` 的"不引入 MCP SDK"条目并说明边界（仅 Client、仅 tools）。
- SQLite 是唯一数据库；结构变更必须带 Alembic 迁移（`20261124_0005_mcp_servers`）。
- 单进程 asyncio；stdio 子进程与 HTTP 会话必须可回收，关停后无孤儿进程。
- 工具输入输出必须 JSON 可序列化；工具异常不透传正文；单次 MCP 结果上限 200 KB。
- 配置只经 `pydantic-settings`；MCP 服务清单属用户数据，存 SQLite。
- 不预置字段兜底；密钥不得明文入库（只支持 `${VAR}`）。
- 质量门槛：`ruff check`、`ruff format --check`、`mypy src`、`pytest`；UI `pnpm check`、`pnpm test`、`pnpm build`。
- 终端约定：后端命令在 `backend/` 下用 `uv run`；UI 在 `ui/` 下用 `pnpm`。

## Review Focus

1. **坏服务不拖垮启动**：一个 MCP 服务握手失败时，应用仍能启动，其他服务仍可用，状态显示 `error`（Task 8、12）。
2. **活动 Run 期间禁用/重连被拒**：否则工具被中途注销会让 Run 随机失败，必须返回 `MCP_SERVER_BUSY`（Task 8、12）。
3. **MCP 工具始终审批**：每次调用进入 `waiting_for_approval`；拒绝则工具失败且不派发；文件写入审批行为不得回退（Task 4、5、12）。
4. **大输出/二进制**：MCP 结果超 200 KB 截断、图片/资源只保留元数据，不把二进制写进历史（Task 6、12）。
5. **关停无孤儿**：容器 stop 后 stdio 子进程必须退出（Task 8、12）。

---

### Task 1: 依赖、配置项与错误码

**Files:**
- Modify: `AGENTS.md`（约束条目）
- Modify: `backend/pyproject.toml`
- Modify: `backend/src/prism_agent_kit/core/config.py`
- Modify: `backend/src/prism_agent_kit/core/errors.py`
- Test: `backend/tests/core/test_config.py`

**Interfaces:**
- Produces: `Settings.mcp_connect_timeout_seconds=10.0`、`Settings.mcp_tool_timeout_seconds=30.0`、`Settings.mcp_max_result_bytes=204_800`；错误码 `MCP_SERVER_NOT_FOUND / MCP_SERVER_UNAVAILABLE / MCP_SERVER_BUSY / MCP_CONFIG_INVALID / MCP_PROTOCOL_ERROR / MCP_TOOL_TIMEOUT / MCP_TOOL_ERROR / MCP_TOOL_NAME_CONFLICT / MCP_DISABLED`。

- [ ] **Step 1: 写失败测试**

```python
def test_mcp_defaults() -> None:
    settings = Settings()
    assert settings.mcp_connect_timeout_seconds == 10.0
    assert settings.mcp_tool_timeout_seconds == 30.0
    assert settings.mcp_max_result_bytes == 204_800
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && uv run pytest tests/core/test_config.py::test_mcp_defaults -q`
Expected: FAIL（无该字段）

- [ ] **Step 3: 实现**

- `pyproject.toml` dependencies 加 `"mcp>=2.3,<3"`，执行 `uv lock`（会新增若干传递依赖）。
- `config.py` 加三个字段（float/float/int）。
- `errors.py` 加 9 个错误码。
- `AGENTS.md` 把"当前不引入 ... MCP SDK 运行时依赖"改为：允许 `mcp` 官方 Python SDK，**仅作为 MCP Client、仅接入 tools**；其余（LangChain 等）仍不引入，并写明与上游对齐的理由。

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && uv run pytest tests/core/test_config.py -q && uv run python -c "import mcp; print(mcp.__name__)"`
Expected: PASS 且能 import `mcp`

- [ ] **Step 5: Commit**

```bash
git add AGENTS.md backend/pyproject.toml backend/uv.lock backend/src/prism_agent_kit/core/config.py backend/src/prism_agent_kit/core/errors.py backend/tests/core/test_config.py
git commit -m "feat(mcp): 引入官方 MCP SDK 与配置项/错误码"
```

---

### Task 2: MCP 服务表、迁移与仓储

**Files:**
- Modify: `backend/src/prism_agent_kit/db/models.py`
- Create: `backend/migrations/versions/20261124_0005_mcp_servers.py`
- Create: `backend/src/prism_agent_kit/core/mcp.py`（领域模型 `McpServer`）
- Create: `backend/src/prism_agent_kit/db/repositories/mcp_servers.py`
- Modify: `backend/src/prism_agent_kit/db/mappers.py`、`db/uow.py`
- Test: `backend/tests/db/test_mcp_servers_repository.py`、`backend/tests/db/test_migration.py`

**Interfaces:**
- Produces: `McpServer(id, name, transport: Literal["stdio","http"], command, args: list[str], env: dict[str,str], url, headers: dict[str,str], enabled: bool, status: McpStatus, last_error, created_at, updated_at)`；`McpStatus{disabled,connected,error}`；`McpServerRepository`：`create/get/list_all/list_enabled/update/delete/set_status(id, status, error=None)`；`UnitOfWork.mcp_servers`。

- [ ] **Step 1: 写失败测试**

```python
async def test_mcp_server_crud(uow_factory) -> None:
    async with uow_factory() as uow:
        server = await uow.mcp_servers.create(
            McpServer(name="demo", transport="stdio", command="python", args=["s.py"], env={})
        )
        await uow.commit()
    async with uow_factory() as uow:
        loaded = await uow.mcp_servers.get(server.id)
        assert loaded.name == "demo" and loaded.status is McpStatus.DISABLED
        updated = await uow.mcp_servers.set_status(server.id, McpStatus.ERROR, "boom")
        await uow.commit()
        assert updated.last_error == "boom"

def test_mcp_servers_table(migrated_database_path) -> None:
    with sqlite3.connect(migrated_database_path) as conn:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(mcp_servers)")}
    assert {"id","name","transport","command","args_json","env_json","url","headers_json","enabled","status","last_error"} <= cols
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && uv run pytest tests/db/test_mcp_servers_repository.py tests/db/test_migration.py -q`
Expected: FAIL

- [ ] **Step 3: 实现**

- `McpServerRow`（列按 spec §8；`args_json/env_json/headers_json` 用 `JSON`；`name` 唯一索引）。
- 迁移 `20261124_0005_mcp_servers`（upgrade 建表 + `ux_mcp_servers_name`；downgrade 删表）。
- `core/mcp.py` 领域模型 + 枚举；mappers；`uow.mcp_servers`。

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && uv run pytest tests/db/test_mcp_servers_repository.py tests/db/test_migration.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/prism_agent_kit/db backend/migrations/versions/20261124_0005_mcp_servers.py backend/src/prism_agent_kit/core/mcp.py backend/tests/db
git commit -m "feat(mcp): 服务表、迁移与仓储"
```

---

### Task 3: MCP 配置服务（校验、`${VAR}`、密钥拒绝）

**Files:**
- Create: `backend/src/prism_agent_kit/application/mcp/__init__.py`
- Create: `backend/src/prism_agent_kit/application/mcp/config_service.py`
- Test: `backend/tests/application/mcp/test_config_service.py`

**Interfaces:**
- Produces: `McpConfigService(uow_factory)`：`list_servers()`、`create(payload) -> McpServer`、`update(id, payload)`、`delete(id)`、`set_enabled(id, enabled)`、`build_connection(server) -> McpConnection`；`McpConnection(transport, params: StdioServerParameters | dict)`；`resolve_placeholders(mapping) -> dict`。

- [ ] **Step 1: 写失败测试**

```python
async def test_rejects_plaintext_secret(config_service) -> None:
    with pytest.raises(AgentKitError) as error:
        await config_service.create(
            McpServerInput(name="x", transport="stdio", command="python",
                           env={"API_KEY": "sk-1234567890abcdef"})
        )
    assert error.value.code is ErrorCode.MCP_CONFIG_INVALID

async def test_resolves_env_placeholder(config_service, monkeypatch) -> None:
    monkeypatch.setenv("MY_TOKEN", "abc")
    conn = await config_service.create_then_build(
        McpServerInput(name="x", transport="http", url="https://mcp.example/mcp",
                       headers={"Authorization": "Bearer ${MY_TOKEN}"})
    )
    assert conn.params["headers"]["Authorization"] == "Bearer abc"

async def test_missing_placeholder_rejected(config_service) -> None:
    with pytest.raises(AgentKitError) as error:
        await config_service.create_then_build(
            McpServerInput(name="x", transport="http", url="https://e/mcp",
                           headers={"X": "${MISSING_VAR}"})
        )
    assert error.value.code is ErrorCode.MCP_CONFIG_INVALID
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && uv run pytest tests/application/mcp/test_config_service.py -q`
Expected: FAIL

- [ ] **Step 3: 实现**

- 名称 slug 校验（`^[a-z0-9]+(?:-[a-z0-9]+)*$`）；`stdio` 必须有 `command`，`http` 必须有 `url`。
- 密钥形态检测：值不以 `${...}` 开头且匹配 `^sk-`、`^Bearer `、长度 ≥ 32 的 base64/hex → `MCP_CONFIG_INVALID`。
- `resolve_placeholders`：仅替换形如 `${VAR}` 的整值或片段；缺失变量报错。
- `build_connection`：stdio → `StdioServerParameters(command=..., args=[...], env=白名单+叠加)`；http → `{"url":..., "headers":...}`。

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && uv run pytest tests/application/mcp/test_config_service.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/prism_agent_kit/application/mcp backend/tests/application/mcp
git commit -m "feat(mcp): 配置服务与占位符解析"
```

---

### Task 4: 审批通道泛化（后端）

**Files:**
- Modify: `backend/src/prism_agent_kit/tools/contracts.py`（`input_schema_override`）
- Modify: `backend/src/prism_agent_kit/core/engine.py`（挂起条件只看 `requires_approval`；`TOOL_REQUESTED` 脱敏按 `requires_approval`）
- Modify: `backend/src/prism_agent_kit/application/tool_approval_service.py`（按工具类型分支）
- Modify: `backend/src/prism_agent_kit/api/schemas.py`、`api/routes/runs.py`（预览 DTO 加 `kind`、`input_preview`）
- Modify: `backend/src/prism_agent_kit/application/container.py`（file_write 的 `requires_approval` 由 `workspace_require_write_approval` 决定）
- Test: `backend/tests/application/test_tool_approval_service.py`、`backend/tests/core/test_engine_approval.py`、`backend/tests/tools/test_registry.py`

**Interfaces:**
- Produces: `ToolDefinition.input_schema_override: dict[str, JsonValue] | None = None`；`ApprovalPreview(kind: Literal["file","generic"], path, mode, bytes, exists, diff, truncated, input_preview: JsonValue | None)`。

- [ ] **Step 1: 写失败测试**

```python
async def test_generic_tool_approval_has_no_file_fields(approval_ctx_generic) -> None:
    preview = await approval_ctx_generic.service.preview(run_id, call_id)
    assert preview.kind == "generic"
    assert preview.input_preview == {"query": "订单 123"}
    call, run = await approval_ctx_generic.service.decide(run_id, call_id, "approve")
    assert call.status is ToolCallStatus.SUCCEEDED and run.status is RunStatus.QUEUED

async def test_file_write_approval_unchanged(file_approval_ctx) -> None:
    preview = await file_approval_ctx.service.preview(run_id, call_id)
    assert preview.kind == "file" and preview.mode == "overwrite"
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && uv run pytest tests/application/test_tool_approval_service.py -q`
Expected: FAIL

- [ ] **Step 3: 实现**

- `contracts.py`：加 `input_schema_override`，`to_model_schema()` 用它优先。
- `engine.py`：`if definition.requires_approval:`（去掉 `and self._require_write_approval`）；`_wait_for_approval` 的 `TOOL_REQUESTED`/`TOOL_APPROVAL_REQUIRED` payload 按工具是否 file 系生成 `kind` 与 `input_preview`。
- `tool_approval_service.py`：`preview` 先看 `tool_name.startswith("file_")`，否则 generic（输入 JSON 截断 4 KB）；`decide` 只在 file 工具且成功时触发 `index_tasks.submit(mode="file")`；generic 不要求 `workspace_root`。
- `container.py`：构造 `file_write` 时把 `requires_approval=settings.workspace_require_write_approval`（用 `build_workspace_tools(require_approval=...)` 参数）。
- `api/schemas.py` 的 `ApprovalPreviewView` 加 `kind`、`input_preview`。

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && uv run pytest tests/application/test_tool_approval_service.py tests/core/test_engine_approval.py tests/tools -q`
Expected: PASS（文件写入审批回归不破）

- [ ] **Step 5: Commit**

```bash
git add backend/src/prism_agent_kit backend/tests
git commit -m "feat(approval): 审批通道泛化为通用工具审批"
```

---

### Task 5: 审批卡片泛化（UI）

**Files:**
- Modify: `ui/src/lib/api/contracts.ts`、`client.ts`
- Modify: `ui/src/features/runs/RunInspector.vue`
- Test: `ui/tests/unit/approval-card.test.ts`、`ui/tests/unit/contracts.test.ts`

**Interfaces:**
- Produces: `approvalPreviewSchema` 增加 `kind: 'file' | 'generic'`、`input_preview: z.json().nullable()`；卡片按 `kind` 渲染 diff 或 `<pre>` 输入。

- [ ] **Step 1: 写失败测试**

```typescript
it('generic 审批展示输入 JSON 而不是 diff', () => {
  const wrapper = mount(RunInspector, { props: { projection: projectionWithGenericApproval() } , global: ctx })
  expect(wrapper.text()).toContain('mcp__demo__search')
  expect(wrapper.find('pre').text()).toContain('订单 123')
})
```

- [ ] **Step 2: 运行确认失败**

Run: `cd ui && pnpm vitest run tests/unit/approval-card.test.ts`
Expected: FAIL

- [ ] **Step 3: 实现**

- 契约/客户端 `getApprovalPreview` 返回新字段。
- 卡片：`kind === 'file'` 保持路径/模式/字节 + diff；`generic` 显示工具名 + 输入 JSON（截断），按钮文案不变。

- [ ] **Step 4: 运行确认通过**

Run: `cd ui && pnpm vitest run tests/unit/approval-card.test.ts tests/unit/contracts.test.ts && pnpm typecheck`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add ui/src ui/tests
git commit -m "feat(ui): 通用工具审批卡片"
```

---

### Task 6: 工具命名与 MCP 工具适配

**Files:**
- Create: `backend/src/prism_agent_kit/application/mcp/naming.py`
- Create: `backend/src/prism_agent_kit/application/mcp/adapter.py`
- Test: `backend/tests/application/mcp/test_naming.py`、`test_adapter.py`

**Interfaces:**
- Produces：`tool_name_for(server_slug: str, tool_name: str) -> str`；`McpToolInput(BaseModel)`（`extra="allow"`）；`to_tool_definition(server: McpServer, tool: McpToolInfo, invoke: Callable[[str, dict], Awaitable[CallToolResult]]) -> ToolDefinition`；`normalize_result(result, max_bytes) -> JsonValue`。

- [ ] **Step 1: 写失败测试**

```python
def test_tool_name_prefix_and_truncate() -> None:
    assert tool_name_for("demo", "search") == "mcp__demo__search"
    name = tool_name_for("demo", "x" * 100)
    assert len(name) <= 64 and name.startswith("mcp__demo__")

def test_schema_is_passed_through() -> None:
    definition = to_tool_definition(server, McpToolInfo(name="search", description="d",
        input_schema={"type": "object", "properties": {"q": {"type": "string"}}, "$defs": {}}), invoke)
    assert definition.to_model_schema()["function"]["parameters"]["$defs"] == {}
    assert definition.requires_approval is True

async def test_normalize_result_truncates_and_drops_binary() -> None:
    result = fake_result([TextContent(type="text", text="x" * 300_000), ImageContent(type="image", data="...", mimeType="image/png")])
    value = normalize_result(result, 204_800)
    assert len(value["text"]) <= 204_800 and value["images"][0] == {"type": "image", "mimeType": "image/png"}
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && uv run pytest tests/application/mcp/test_naming.py tests/application/mcp/test_adapter.py -q`
Expected: FAIL

- [ ] **Step 3: 实现**

- 命名：slug 规范化 + `mcp__<slug>__<tool>`，总长 64 截断 + `__<sha6>`。
- 定义：`execution_mode=LOCAL`、`requires_approval=True`、`timeout_seconds=mcp_tool_timeout_seconds`、`input_model=McpToolInput`、`input_schema_override=tool.input_schema`。
- `normalize_result`：text 合并并截断；image/audio/resource 只留 `{type,mimeType,size}`；`structured_content` 原样；`is_error` → 抛 `MCP_TOOL_ERROR`。

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && uv run pytest tests/application/mcp/test_naming.py tests/application/mcp/test_adapter.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/prism_agent_kit/application/mcp backend/tests/application/mcp
git commit -m "feat(mcp): 工具命名与 SDK 适配"
```

---

### Task 7: ToolRegistry 运行期注册与按前缀注销

**Files:**
- Modify: `backend/src/prism_agent_kit/tools/registry.py`
- Test: `backend/tests/tools/test_registry.py`

**Interfaces:**
- Produces: `unregister_by_prefix(prefix: str) -> list[str]`；`register` 冲突时报 `MCP_TOOL_NAME_CONFLICT`。

- [ ] **Step 1: 写失败测试**

```python
def test_unregister_by_prefix() -> None:
    registry = ToolRegistry(); registry.register(_tool("mcp__a__x")); registry.register(_tool("mcp__a__y")); registry.register(_tool("echo"))
    removed = registry.unregister_by_prefix("mcp__a__")
    assert sorted(removed) == ["mcp__a__x", "mcp__a__y"] and [t.name for t in registry.list_tools()] == ["echo"]
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && uv run pytest tests/tools/test_registry.py -q`
Expected: FAIL

- [ ] **Step 3: 实现**

`registry.py`：`_tools` 用 dict；`unregister_by_prefix`；`register` 重名抛 `MCP_TOOL_NAME_CONFLICT`（保留原有行为对非 MCP 名也一致，改为统一冲突码）。

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && uv run pytest tests/tools -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/prism_agent_kit/tools/registry.py backend/tests/tools/test_registry.py
git commit -m "feat(tools): 运行期注销与冲突码"
```

---

### Task 8: MCP 连接管理器与生命周期

**Files:**
- Create: `backend/src/prism_agent_kit/application/mcp/manager.py`
- Create: `backend/src/prism_agent_kit/application/mcp/supervisor.py`
- Test: `backend/tests/application/mcp/test_manager.py`（用注入的 fake client，不启真进程）

**Interfaces:**
- Produces：`McpServerManager(uow_factory, config_service, tool_registry, client_factory=...)`：`start_all()`、`connect(server_id)`、`disconnect(server_id)`、`reconnect(server_id)`、`set_enabled(server_id, enabled)`、`call_tool(full_name, arguments, timeout)`、`stop()`；内部 `McpWorker` 每个服务一个任务（独占 `async with mcp.Client(...)` 上下文）+ 请求队列。
- `client_factory` 可注入 `async with Client(params)` 的对象，测试用 fake。

- [ ] **Step 1: 写失败测试**

```python
async def test_failed_server_does_not_block_others(manager, fake_clients) -> None:
    fake_clients.fail("bad")
    await manager.start_all()   # 不抛
    assert manager.status("bad") == McpStatus.ERROR
    assert manager.status("good") == McpStatus.CONNECTED
    assert any(t.name.startswith("mcp__good__") for t in manager.tools)

async def test_disable_blocked_while_run_active(manager, uow_factory) -> None:
    await seed_active_run(uow_factory)
    with pytest.raises(AgentKitError) as error:
        await manager.set_enabled(server_id, False)
    assert error.value.code is ErrorCode.MCP_SERVER_BUSY

async def test_stop_reclaims_workers(manager, fake_clients) -> None:
    await manager.start_all(); await manager.stop()
    assert fake_clients.closed_all()
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && uv run pytest tests/application/mcp/test_manager.py -q`
Expected: FAIL

- [ ] **Step 3: 实现**

- 每个 server 一个 `McpWorker`：任务内 `async with client` 初始化、`list_tools`、注册工具；循环消费队列执行 `call_tool`；退出时注销前缀并关闭。
- `start_all` 并发（`asyncio.gather`），单服务异常只 `set_status(ERROR, 脱敏错误)`。
- `set_enabled/disable/reconnect` 先检查是否有活动 Run（`runs` 表 status in running/waiting_for_tool/waiting_for_approval）→ `MCP_SERVER_BUSY`。
- 停用：disconnect + `unregister_by_prefix` + `set_status(DISABLED)`。
- `stop()`：`cancel` 全部 worker 并 await，子进程由 SDK 上下文回收。

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && uv run pytest tests/application/mcp/test_manager.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/prism_agent_kit/application/mcp backend/tests/application/mcp
git commit -m "feat(mcp): 连接管理器与生命周期"
```

---

### Task 9: MCP HTTP 接口与容器装配

**Files:**
- Create: `backend/src/prism_agent_kit/api/routes/mcp.py`
- Modify: `backend/src/prism_agent_kit/api/schemas.py`、`api/dependencies.py`、`api/router.py`
- Modify: `backend/src/prism_agent_kit/application/container.py`
- Test: `backend/tests/api/test_mcp.py`、`backend/tests/api/conftest.py`

**Interfaces:**
- Produces：`McpServerView`、`McpServerCreate`、`McpToolsView`；依赖 `McpConfigServiceDependency`、`McpManagerDependency`；容器启动 `await manager.start_all()`，停止 `await manager.stop()`。

- [ ] **Step 1: 写失败测试**

```python
def test_mcp_server_crud_and_tools(api_client) -> None:
    created = api_client.post("/api/v1/mcp/servers", json={"name":"demo","transport":"stdio","command":"python","args":[]})
    assert created.status_code == 200 and created.json()["status"] == "disabled"
    assert api_client.get(f"/api/v1/mcp/servers/{created.json()['id']}/tools").status_code == 200

def test_mcp_secret_rejected(api_client) -> None:
    response = api_client.post("/api/v1/mcp/servers", json={"name":"x","transport":"stdio","command":"p","env":{"K":"sk-abcdefghijklmnopqrstuvwxyz"}})
    assert response.status_code == 400 and response.json()["error"]["code"] == "MCP_CONFIG_INVALID"
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && uv run pytest tests/api/test_mcp.py -q`
Expected: FAIL（404）

- [ ] **Step 3: 实现**

- 7 个接口（spec §9）；密钥字段只回显占位/掩码。
- 容器：构造 `McpConfigService`、`McpServerManager`（client_factory 默认真实 `mcp.Client`），start 时 `await manager.start_all()`，stop 时先 `manager.stop()`。
- `tests/api/conftest.py` 的 `ApiTestContainer` 增加 `mcp_config_service`、`mcp_manager`（fake client）。

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && uv run pytest tests/api -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/prism_agent_kit/api backend/src/prism_agent_kit/application/container.py backend/tests/api
git commit -m "feat(api): MCP 服务接口与容器装配"
```

---

### Task 10: MCP 页面与前端契约

**Files:**
- Create: `ui/src/features/mcp/McpPage.vue`、`ui/src/features/mcp/mcp.ts`
- Modify: `ui/src/lib/api/contracts.ts`、`client.ts`、`ui/src/app/{modules,router,AppShell}`
- Test: `ui/tests/unit/mcp.test.ts`

**Interfaces:**
- Produces：`mcpServerSchema`、`mcpServersSchema`、`mcpToolsSchema`；客户端 `listMcpServers/createMcpServer/updateMcpServer/deleteMcpServer/setMcpEnabled/reconnectMcp/getMcpTools`；控制器 `createMcpController({client})`。

- [ ] **Step 1: 写失败测试**

```typescript
it('服务状态与工具数渲染', async () => {
  const controller = createMcpController({ client: fakeClient })
  await controller.load()
  expect(controller.state.servers[0].status).toBe('connected')
})
```

- [ ] **Step 2: 运行确认失败**

Run: `cd ui && pnpm vitest run tests/unit/mcp.test.ts`
Expected: FAIL

- [ ] **Step 3: 实现**

页面：服务器列表（状态点、工具数、重连/启停/删除）、添加表单（按 transport 切换字段）、工具目录抽屉；错误 `last_error` 可复制、不回显密钥。路由 `/mcp` + 顶部导航「MCP」。

- [ ] **Step 4: 运行确认通过**

Run: `cd ui && pnpm vitest run tests/unit/mcp.test.ts && pnpm check`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add ui/src ui/tests
git commit -m "feat(ui): MCP 服务页"
```

---

### Task 11: stdio 测试服务与集成测试

**Files:**
- Create: `backend/tests/support/mcp_stdio_server.py`（用官方 `MCPServer` 定义 `echo` / `slow` / `boom` 三个工具）
- Test: `backend/tests/application/mcp/test_stdio_integration.py`

**Interfaces:**
- Consumes：Task 8 的管理器（真实 `mcp.Client`）。

- [ ] **Step 1: 写失败测试**

```python
async def test_stdio_server_tools_and_calls(manager_with_stdio) -> None:
    names = {t.name for t in manager_with_stdio.tools}
    assert {"mcp__demo__echo", "mcp__demo__slow", "mcp__demo__boom"} <= names
    result = await manager_with_stdio.call_tool("mcp__demo__echo", {"text": "hi"}, timeout=5)
    assert result["text"] == "hi"

async def test_stdio_tool_timeout(manager_with_stdio) -> None:
    with pytest.raises(AgentKitError) as error:
        await manager_with_stdio.call_tool("mcp__demo__slow", {"seconds": 5}, timeout=0.2)
    assert error.value.code is ErrorCode.MCP_TOOL_TIMEOUT
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && uv run pytest tests/application/mcp/test_stdio_integration.py -q`
Expected: FAIL

- [ ] **Step 3: 实现**

测试服务脚本用 `MCPServer` 定义工具；fixture 用 `sys.executable` + 脚本路径配置一个临时 `mcp_servers` 行，启管理器；断言工具注册、调用、超时、错误码。

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && uv run pytest tests/application/mcp -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/tests
git commit -m "test(mcp): stdio 集成测试"
```

---

### Task 12: HTTP 传输、审批与生命周期验收

**Files:**
- Test: `backend/tests/application/mcp/test_http_integration.py`、`backend/tests/application/mcp/test_lifecycle.py`、`backend/tests/application/mcp/test_approval_flow.py`

**Interfaces:**
- Consumes：Task 8/9。

- [ ] **Step 1: 写失败测试**

```python
async def test_http_server_handshake_and_call(http_manager) -> None:  # 本地起 MCPServer streamable-http
    assert await http_manager.call_tool("mcp__web__echo", {"text": "ok"}, timeout=5) == {"text": "ok"}

async def test_bad_http_server_marks_error_but_app_starts(http_manager, uow_factory) -> None: ...

async def test_mcp_tool_requires_approval(container_with_mcp, ...) -> None:
    # Run 调 MCP 工具 → waiting_for_approval → approve → succeeded；reject → TOOL_REJECTED

async def test_stop_leaves_no_child(manager_with_stdio) -> None:
    pid = manager_with_stdio.child_pid()
    await manager_with_stdio.stop()
    assert not psutil.pid_exists(pid) or 已退出
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && uv run pytest tests/application/mcp -q -k "http or lifecycle or approval"`
Expected: FAIL

- [ ] **Step 3: 实现**

HTTP 测试服务用 `MCPServer` 以 `streamable-http` 起在随机端口（`uvicorn` 于线程或子进程），fixture 等待健康；审批用 `ScriptedModelProvider` 触发 MCP 工具调用；进程检查用 `os.kill(pid, 0)`（不引入 psutil）。

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && uv run pytest -q`
Expected: PASS（全量）

- [ ] **Step 5: Commit**

```bash
git add backend/tests
git commit -m "test(mcp): HTTP 传输、审批与生命周期验收"
```

---

### Task 13: 文档、版本与验收

**Files:**
- Modify: `README.md`、`backend/README.md`、`ui/README.md`、`backend/.env.example`
- Modify: `backend/pyproject.toml`、`backend/src/prism_agent_kit/__init__.py`、`ui/package.json`（1.2.0）
- Test: `backend/tests/test_agent_e2e.py`（追加 MCP 审批闭环用例）

- [ ] **Step 1: 写失败测试**

```python
def test_e2e_mcp_tool_requires_approval(migrated_database_path, tmp_path) -> None:
    # 起 stdio 测试服务 → 配置服务 → 模型请求 mcp 工具 → waiting_for_approval → approve → succeeded
    ...
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && uv run pytest tests/test_agent_e2e.py -q -k mcp`
Expected: FAIL

- [ ] **Step 3: 实现**

- `.env.example` 加 `MCP_CONNECT_TIMEOUT_SECONDS` / `MCP_TOOL_TIMEOUT_SECONDS` / `MCP_MAX_RESULT_BYTES`。
- README 去掉"不包含 MCP Client"，加 MCP 能力与配置说明；`AGENTS.md` 已在 Task 1 更新。
- 版本号 1.2.0（pyproject/`__version__`/package.json + `uv lock`）。

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && uv run pytest -q && uv run ruff check . && uv run ruff format --check . && uv run mypy src`
Expected: 全 PASS

Run: `cd ui && pnpm check && pnpm test && pnpm build`
Expected: 全 PASS

- [ ] **Step 5: Commit**

```bash
git add README.md backend/README.md ui/README.md backend/.env.example backend/pyproject.toml backend/uv.lock backend/src/prism_agent_kit/__init__.py ui/package.json backend/tests/test_agent_e2e.py
git commit -m "docs(mcp): V1.2 使用说明与版本 1.2.0"
```

---

## Self-Review

**Spec coverage**

| 设计要求 | 任务 |
|---|---|
| 依赖/约束/配置/错误码 | 1 |
| mcp_servers 表与迁移 | 2 |
| 配置校验、`${VAR}`、密钥拒绝、环境白名单 | 3 |
| 审批泛化（引擎/预览/事件/执行） | 4、5 |
| schema 透传与工具命名 | 6 |
| 运行期注册/注销 | 7 |
| 生命周期、失败隔离、BUSY 保护、关停回收 | 8、12 |
| HTTP 接口与容器 | 9 |
| MCP 页 | 10 |
| stdio/HTTP 集成、审批闭环、无孤儿 | 11、12、13 |
| 文档与版本 | 13 |

**Review Focus 对位**：坏服务不拖垮启动 → Task 8 `test_failed_server_does_not_block_others` + Task 12；活动 Run 拒绝禁用/重连 → Task 8 `test_disable_blocked_while_run_active`；MCP 始终审批 → Task 4/5 + Task 12 `test_mcp_tool_requires_approval`；大输出/二进制 → Task 6 `test_normalize_result_truncates_and_drops_binary`；关停无孤儿 → Task 8/12。

**类型一致性**：`McpServer.status: McpStatus`、`McpConnection.params: StdioServerParameters | dict`、`tool_name_for()`、`ToolDefinition.input_schema_override`、`ApprovalPreview.kind/input_preview` 在各任务中被一致引用。
