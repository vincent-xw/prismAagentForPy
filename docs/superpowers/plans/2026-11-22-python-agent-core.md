# PrismAgentKit Python Agent Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建一个本地运行、SQLite 持久化、FastAPI/SSE 对外、自研 Agent 循环的 PrismAgentKit Python Core。

**Architecture:** FastAPI 只承担 BFF；Application Service 管理用例和事务；SimpleAgentEngine 负责模型与工具循环；SQLAlchemy Repository 管理 SQLite 事实数据；EventBus 合并持久事件与临时流式事件。未来 LangGraph 等实现通过 `AgentEngine` 接口接入。

**Tech Stack:** Python 3.12、FastAPI、Pydantic v2、SQLAlchemy 2 Async、aiosqlite、Alembic、OpenAI Python SDK、sse-starlette、tiktoken、pytest、Ruff、mypy。

**Spec:** `docs/superpowers/specs/2026-11-22-python-agent-core-design.md`

## Global Constraints

- 不做 Node.js URL、DTO 或 SQLite 表结构兼容。
- 不引入 LangChain、LangGraph、PydanticAI、MCP SDK 或 LangSmith 运行时依赖。
- 使用 `src` 布局；产品代码只写入 `src/prism_agent_kit/`。
- 默认单进程本地运行；API 只绑定 `127.0.0.1`，非测试环境必须配置 API Token。
- SQLite 是首版唯一数据库；启动时启用 WAL、外键和 busy timeout。
- 模型密钥只来自环境变量；不得写入数据库、日志、SSE 或错误响应。
- 模型可见历史必须可以从 Message、ToolCall 和 Run 数据重建。
- 只允许在完整 assistant/tool 消息组边界裁剪上下文。
- 所有终止 Run 必须闭合未完成 ToolCall。
- 不猜测 Prompt 版本；必须使用明确 `name@version`。
- Token 预算必须使用显式配置的 `tiktoken` encoding，不静默退回字符近似。
- 默认不做字段兜底；缺失或非法配置必须显式失败。
- 每个任务先写失败测试，再实现，再运行定向测试与全量质量门槛，最后提交。

## Review Focus

- 终止 Run 留下未闭合 ToolCall：后续 ContextAssembler 必须 fail closed，不能把非法历史发给模型。
- 远端工具重复回填或进程重启竞态：结果必须原子、幂等，冲突不能覆盖已提交历史。
- 一轮多个工具调用：每个 call ID 都必须有工具结果，不能只处理第一个。
- 上下文裁剪：assistant 与它的全部 tool 结果必须同去同留。
- SSE 重放与实时订阅竞态：持久事件不能重复或丢失。

## File Structure

```text
src/prism_agent_kit/
├── api/
│   ├── auth.py
│   ├── errors.py
│   ├── schemas.py
│   └── routes/
│       ├── runs.py
│       ├── sessions.py
│       └── tools.py
├── application/
│   ├── container.py
│   ├── event_bus.py
│   ├── run_service.py
│   ├── run_worker.py
│   ├── session_service.py
│   └── tool_result_service.py
├── core/
│   ├── context.py
│   ├── engine.py
│   ├── enums.py
│   ├── errors.py
│   ├── models.py
│   ├── ports.py
│   ├── prompts.py
│   ├── state.py
│   └── token_budget.py
├── db/
│   ├── database.py
│   ├── mappers.py
│   ├── models.py
│   ├── repositories/
│   │   ├── events.py
│   │   ├── messages.py
│   │   ├── runs.py
│   │   ├── sessions.py
│   │   └── tool_calls.py
│   └── uow.py
├── providers/
│   └── openai_compatible.py
├── tools/
│   ├── contracts.py
│   ├── executor.py
│   ├── registry.py
│   └── testing.py
└── main.py

tests/
├── api/
├── application/
├── core/
├── db/
├── providers/
├── tools/
└── fakes.py
```

---

### Task 1: Runtime Configuration, App Factory, and SQLite Database

**Files:**
- Modify: `pyproject.toml`
- Modify: `.env.example`
- Modify: `src/prism_agent_kit/core/config.py`
- Create: `src/prism_agent_kit/db/database.py`
- Modify: `src/prism_agent_kit/db/session.py`
- Modify: `migrations/env.py`
- Modify: `src/prism_agent_kit/main.py`
- Modify: `tests/conftest.py`
- Modify: `tests/test_health.py`
- Create: `tests/core/test_config.py`
- Create: `tests/db/test_database.py`

**Interfaces:**
- Consumes: existing FastAPI scaffold and `Settings`.
- Produces: `Settings` runtime fields；`Database(path: Path)`；`Database.session_factory`；`Database.dispose()`；`create_app(settings: Settings | None = None) -> FastAPI`。

- [ ] **Step 1: Write failing config and database tests**

```python
def test_settings_parse_runtime_values(tmp_path: Path) -> None:
    settings = Settings(
        database_path=tmp_path / "agent.db",
        api_token=SecretStr("test-token"),
        model_base_url="https://example.test/v1",
        model_api_key=SecretStr("secret"),
        model_name="deepseek-chat",
        model_token_encoding="cl100k_base",
    )
    assert settings.database_path == tmp_path / "agent.db"
    assert settings.model_name == "deepseek-chat"


async def test_database_enables_sqlite_pragmas(tmp_path: Path) -> None:
    database = Database(tmp_path / "agent.db")
    async with database.engine.connect() as connection:
        assert (await connection.exec_driver_sql("PRAGMA journal_mode")).scalar() == "wal"
        assert (await connection.exec_driver_sql("PRAGMA foreign_keys")).scalar() == 1
    await database.dispose()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/core/test_config.py tests/db/test_database.py -v`

Expected: FAIL because runtime fields and `Database` do not exist.

- [ ] **Step 3: Add dependencies and implement configuration/database lifecycle**

Add runtime dependencies: `aiosqlite`、`openai`、`sse-starlette`、`tiktoken`、`platformdirs`、`filelock`。移除不再使用的 `asyncpg` 直接依赖。

`Settings` 增加：

```python
database_path: Path | None = None
api_token: SecretStr | None = None
default_prompt_ref: str = "default@1"
model_base_url: str | None = None
model_api_key: SecretStr | None = None
model_name: str | None = None
model_context_window: int | None = None
model_max_output_tokens: int | None = None
model_token_encoding: str | None = None
model_timeout_seconds: float = 30.0
context_safety_margin_tokens: int = 2048
max_steps: int = 10
tool_timeout_seconds: float = 30.0
remote_tool_timeout_seconds: float = 300.0
worker_concurrency: int = 2
sse_heartbeat_seconds: float = 15.0
```

`Settings.resolved_database_path` 在未配置 `database_path` 时使用 `platformdirs.user_data_dir("prism-agent-kit")`；这是明确的数据目录默认值，不用于掩盖缺失的模型配置。

`Database` 使用 `create_async_engine("sqlite+aiosqlite:///...")`，通过 connection event 执行设计中的 PRAGMA。`create_app()` 接收可选 Settings，在 lifespan 中创建 `Database` 并挂到 `app.state`。

`migrations/env.py` 改为从 `Settings.resolved_database_path` 构造 SQLite URL，不再读取 Postgres `database_url`。

- [ ] **Step 4: Run focused tests and existing health test**

Run: `uv run pytest tests/core/test_config.py tests/db/test_database.py tests/test_health.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml uv.lock .env.example src/prism_agent_kit tests
git commit -m "chore: configure Python agent runtime and SQLite"
```

---

### Task 2: Domain Enums, Errors, Models, and Run Transitions

**Files:**
- Create: `src/prism_agent_kit/core/enums.py`
- Create: `src/prism_agent_kit/core/errors.py`
- Create: `src/prism_agent_kit/core/models.py`
- Create: `src/prism_agent_kit/core/state.py`
- Create: `tests/core/test_models.py`
- Create: `tests/core/test_state.py`

**Interfaces:**
- Consumes: no persistence or web types.
- Produces: `RunStatus`、`ToolCallStatus`、`MessageRole`、`ExecutionMode`、`EventType`；`ErrorCode`；`AgentKitError`；Pydantic `Session`、`Run`、`Message`、`ToolCall`、`RunEvent`；`ensure_run_transition(current, target)`。

- [ ] **Step 1: Write failing domain tests**

```python
def test_run_status_serializes_as_string() -> None:
    assert RunStatus.WAITING_FOR_TOOL.value == "waiting_for_tool"


def test_waiting_run_can_be_requeued() -> None:
    ensure_run_transition(RunStatus.WAITING_FOR_TOOL, RunStatus.QUEUED)


def test_terminal_run_cannot_be_requeued() -> None:
    with pytest.raises(AgentKitError) as error:
        ensure_run_transition(RunStatus.SUCCEEDED, RunStatus.QUEUED)
    assert error.value.code is ErrorCode.INVALID_RUN_TRANSITION
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/core/test_models.py tests/core/test_state.py -v`

Expected: FAIL because domain modules do not exist.

- [ ] **Step 3: Implement domain types**

`RunStatus` 包含 `queued/running/waiting_for_tool/succeeded/failed/cancelled`。

`ToolCallStatus` 包含 `pending/running/succeeded/failed/expired/cancelled`。

`EventType` 包含设计文档中的持久事件名，以及 `message.delta`、`reasoning.delta` 两个临时事件名。

`AgentKitError` 签名：

```python
class AgentKitError(Exception):
    def __init__(
        self,
        code: ErrorCode,
        message: str,
        *,
        http_status: int = 500,
        details: Mapping[str, object] | None = None,
    ) -> None: ...
```

`state.py` 使用显式 transition map，不允许跳过校验直接更新状态。

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/core/test_models.py tests/core/test_state.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/prism_agent_kit/core tests/core
git commit -m "feat: add agent core domain model"
```

---

### Task 3: SQLAlchemy Tables, Initial Migration, and Mappers

**Files:**
- Create: `src/prism_agent_kit/db/models.py`
- Create: `src/prism_agent_kit/db/mappers.py`
- Create: `migrations/versions/20261122_0001_agent_core_schema.py`
- Modify: `src/prism_agent_kit/db/base.py`
- Modify: `tests/conftest.py`
- Create: `tests/db/test_migration.py`
- Create: `tests/db/test_mappers.py`

**Interfaces:**
- Consumes: Task 2 domain models and `Database`.
- Produces: ORM rows `SessionRow/RunRow/MessageRow/ToolCallRow/RunEventRow`；双向 mapper 函数 `session_to_domain()` 等；可升级到 `head` 的 Alembic migration。

- [ ] **Step 1: Write failing schema tests**

```python
async def test_migration_creates_agent_tables(migrated_database: Database) -> None:
    async with migrated_database.engine.connect() as connection:
        rows = await connection.exec_driver_sql("SELECT name FROM sqlite_master WHERE type='table'")
        names = {row.name for row in rows}
    assert {"sessions", "runs", "messages", "tool_calls", "run_events"} <= names


async def test_active_run_index_rejects_second_active_run(migrated_database: Database) -> None:
    # 插入同 Session 的两个 queued Run，第二次必须触发 IntegrityError。
    ...
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/db/test_migration.py tests/db/test_mappers.py -v`

Expected: FAIL because tables, migration and mappers do not exist.

- [ ] **Step 3: Implement ORM schema and migration**

使用 SQLAlchemy 2 `Mapped` 声明式模型。JSON 字段使用 SQLAlchemy `JSON`，时间字段存储 UTC datetime。

Migration 创建设计中的五张业务表、索引和 `ux_runs_one_active_per_session` partial unique index。Alembic revision 固定为 `20261122_0001`。

Mappers 负责 ORM 与 Pydantic 领域模型转换，禁止 ORM Row 泄漏到 API 或 Engine。

- [ ] **Step 4: Run migration and mapper tests**

Run: `uv run pytest tests/db/test_migration.py tests/db/test_mappers.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add migrations src/prism_agent_kit/db tests/db
git commit -m "feat: add SQLite schema and domain mappers"
```

---

### Task 4: Unit of Work, Session Repository, and Run Repository

**Files:**
- Create: `src/prism_agent_kit/db/uow.py`
- Create: `src/prism_agent_kit/db/repositories/sessions.py`
- Create: `src/prism_agent_kit/db/repositories/runs.py`
- Create: `tests/db/test_session_repository.py`
- Create: `tests/db/test_run_repository.py`

**Interfaces:**
- Consumes: `Database.session_factory`、ORM rows、domain models。
- Produces: `UnitOfWorkFactory`；`UnitOfWork(sessions, runs, messages, tool_calls, events)`；`SessionRepository.create/get/list`；`RunRepository.create/get/get_active/claim_next/transition`。

- [ ] **Step 1: Write failing repository tests**

```python
async def test_create_and_load_session(uow_factory: UnitOfWorkFactory) -> None:
    async with uow_factory() as uow:
        created = await uow.sessions.create(title="demo")
        await uow.commit()
    async with uow_factory() as uow:
        loaded = await uow.sessions.get(created.id)
    assert loaded == created


async def test_claim_next_only_claims_queued_run(uow_factory: UnitOfWorkFactory) -> None:
    # 创建 queued Run 后 claim，状态必须变为 running；第二次 claim 返回 None。
    ...
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/db/test_session_repository.py tests/db/test_run_repository.py -v`

Expected: FAIL because UoW and repositories do not exist.

- [ ] **Step 3: Implement repositories**

`UnitOfWork` 持有同一个 `AsyncSession`，提供 `commit()` 与 `rollback()`。

`RunRepository.claim_next()` 使用条件更新或事务内重新读取，保证同一 Run 不会被执行两次。

`RunRepository.transition()` 调用 `ensure_run_transition()` 后再写数据库。

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/db/test_session_repository.py tests/db/test_run_repository.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/prism_agent_kit/db tests/db
git commit -m "feat: add SQLite unit of work and run repositories"
```

---

### Task 5: Message, ToolCall, Event Repositories, and History Closure

**Files:**
- Create: `src/prism_agent_kit/core/digests.py`
- Create: `src/prism_agent_kit/db/repositories/messages.py`
- Create: `src/prism_agent_kit/db/repositories/tool_calls.py`
- Create: `src/prism_agent_kit/db/repositories/events.py`
- Modify: `src/prism_agent_kit/db/uow.py`
- Create: `tests/db/test_message_repository.py`
- Create: `tests/db/test_tool_call_repository.py`
- Create: `tests/db/test_event_repository.py`
- Create: `tests/core/test_digests.py`

**Interfaces:**
- Consumes: Task 4 UoW and mappers.
- Produces: `canonical_json_digest(value) -> str`；`MessageRepository.append/list_for_session`；`ToolCallRepository.create_many/get/list_for_run/complete/close_open_calls`；`EventRepository.append/list_after`；`CompleteToolResult` 幂等结果类型。

- [ ] **Step 1: Write failing atomicity tests**

```python
def test_canonical_json_digest_is_key_order_independent() -> None:
    left = canonical_json_digest({"b": 2, "a": 1})
    right = canonical_json_digest({"a": 1, "b": 2})
    assert left == right
    assert left.startswith("sha256:")


async def test_complete_tool_result_is_idempotent(uow_factory: UnitOfWorkFactory) -> None:
    # 首次提交返回 committed；完全相同的第二次提交返回 already_committed。
    ...


async def test_conflicting_tool_result_does_not_modify_history(
    uow_factory: UnitOfWorkFactory,
) -> None:
    # 同 call_id 不同 output 抛出 TOOL_RESULT_CONFLICT，tool Message 数量不变。
    ...


async def test_close_open_calls_adds_tool_messages_for_every_call(
    uow_factory: UnitOfWorkFactory,
) -> None:
    # 两条未完成 ToolCall 必须生成两条 tool Message。
    ...
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/core/test_digests.py tests/db/test_message_repository.py tests/db/test_tool_call_repository.py tests/db/test_event_repository.py -v`

Expected: FAIL because repositories and closure logic do not exist.

- [ ] **Step 3: Implement repositories and atomic completion**

`ToolCallRepository.complete()` 在调用方事务内：

- 读取现有 ToolCall 与 tool Message。
- 相同结果返回 `already_committed`。
- 不同结果抛出 `TOOL_RESULT_CONFLICT`。
- 新结果插入 tool Message、更新 ToolCall、写入事件。

`close_open_calls(run_id, error_code, message)` 为每个未完成 ToolCall 生成 tool Message 并更新状态。调用方负责在同一事务中把 Run 置为终态。

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/core/test_digests.py tests/db/test_message_repository.py tests/db/test_tool_call_repository.py tests/db/test_event_repository.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/prism_agent_kit/core/digests.py src/prism_agent_kit/db tests/core/test_digests.py tests/db
git commit -m "feat: persist messages tools and run events atomically"
```

---

### Task 6: Prompt Registry, Token Budget, and Context Assembly

**Files:**
- Create: `src/prism_agent_kit/core/prompts.py`
- Create: `src/prism_agent_kit/core/token_budget.py`
- Create: `src/prism_agent_kit/core/context.py`
- Create: `tests/core/test_prompts.py`
- Create: `tests/core/test_token_budget.py`
- Create: `tests/core/test_context.py`

**Interfaces:**
- Consumes: `Run.system_prompt`、Message/ToolCall domain models、Settings。
- Produces: `PromptRegistry.register/get(name, version)/get_by_ref(ref)`；`TokenEstimator`；`TiktokenEstimator`；`ContextAssembler.assemble(...) -> ContextAssembly`；`ContextAssembly(messages, estimated_tokens, trimmed_count)`。

- [ ] **Step 1: Write failing tests**

```python
def test_prompt_ref_requires_explicit_version() -> None:
    registry = PromptRegistry()
    registry.register(name="default", version="1", prompt="system")
    with pytest.raises(AgentKitError):
        registry.get_by_ref("default")


def test_context_trimming_keeps_assistant_and_tool_results_together() -> None:
    # 历史为 user、assistant(call-1)、tool(call-1)、user；
    # 预算只够最后一条时，裁剪不能留下孤立的 assistant 或 tool。
    ...
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/core/test_prompts.py tests/core/test_token_budget.py tests/core/test_context.py -v`

Expected: FAIL because Prompt、tokenizer 和 context modules do not exist.

- [ ] **Step 3: Implement prompt lookup, token estimation, and assembly**

Token 预算：

```text
input_budget = context_window - max_output_tokens - safety_margin_tokens
```

`ContextAssembler` 计入 system prompt、工具 Schema、消息内容和 message framing overhead。它按完整消息组从旧到新删除；当前 user Message 单独超预算时抛出 `CONTEXT_BUDGET_EXCEEDED`。

发现未闭合 assistant/tool 组时抛出 `INVALID_HISTORY`，不得静默跳过。

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/core/test_prompts.py tests/core/test_token_budget.py tests/core/test_context.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/prism_agent_kit/core tests/core
git commit -m "feat: add prompts token budget and context assembly"
```

---

### Task 7: Tool Contracts, Registry, and Local Executor

**Files:**
- Create: `src/prism_agent_kit/tools/contracts.py`
- Create: `src/prism_agent_kit/tools/registry.py`
- Create: `src/prism_agent_kit/tools/executor.py`
- Create: `src/prism_agent_kit/tools/testing.py`
- Create: `tests/tools/test_registry.py`
- Create: `tests/tools/test_executor.py`

**Interfaces:**
- Consumes: Pydantic models and `AgentKitError`。
- Produces: `ToolDefinition`；`ToolExecutionContext`；`ToolExecutionResult`；`ToolRegistry`；`LocalToolExecutor.execute(...)`；测试工具 `echo`、`wait_for_host`。

- [ ] **Step 1: Write failing tool tests**

```python
def test_tool_schema_requires_object_input() -> None:
    definition = ToolDefinition(
        name="bad",
        description="bad",
        input_model=str,
        output_model=None,
        execution_mode=ExecutionMode.LOCAL,
        timeout_seconds=1,
    )
    with pytest.raises(AgentKitError):
        definition.to_model_schema()


async def test_local_tool_timeout_returns_tool_error() -> None:
    result = await LocalToolExecutor().execute(slow_tool, {}, context, timeout=0.01)
    assert result.ok is False
    assert result.error_code is ErrorCode.TOOL_EXECUTION_TIMEOUT
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/tools -v`

Expected: FAIL because tool modules do not exist.

- [ ] **Step 3: Implement tool contracts and executor**

工具名校验 `^[a-zA-Z0-9_-]+$`。输入 Schema 顶层必须为 object。输出 Schema 可选。

同步工具通过 `asyncio.to_thread()` 执行。异步工具使用 `asyncio.timeout()`。超时、取消和运行异常转换为 `ToolExecutionResult`；Schema 错误保留为契约错误。

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/tools -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/prism_agent_kit/tools tests/tools
git commit -m "feat: add registered local and remote tool contracts"
```

---

### Task 8: OpenAI-Compatible Streaming Model Provider

**Files:**
- Create: `src/prism_agent_kit/core/ports.py`
- Create: `src/prism_agent_kit/providers/openai_compatible.py`
- Create: `tests/providers/test_openai_compatible.py`
- Create: `tests/fakes.py`

**Interfaces:**
- Consumes: `Settings`、`ToolDefinition`、domain Message。
- Produces: `ToolCallDraft`；`ModelProvider` Protocol；`ModelRequest`；`ModelChunk`；`ModelResponse`；`OpenAICompatibleProvider.stream(...)`。

- [ ] **Step 1: Write failing provider tests**

```python
async def test_provider_aggregates_fragmented_tool_call_arguments() -> None:
    # 使用 httpx.MockTransport 模拟两个 tool_call argument 分片。
    result = await provider.stream(request, on_delta=collect)
    assert result.tool_calls == [
        ToolCallDraft(call_id="call-1", tool_name="echo", input={"text": "hi"})
    ]


async def test_provider_does_not_retry_after_first_delta(monkeypatch: pytest.MonkeyPatch) -> None:
    # 首次流输出一个文本片段后抛错，请求计数必须保持为 1。
    ...
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/providers -v`

Expected: FAIL because provider does not exist.

- [ ] **Step 3: Implement the provider**

使用 `AsyncOpenAI`，允许注入自定义 `AsyncClient` 以便测试。聚合文本、reasoning、usage 和按索引分片的 tool calls。只在尚未输出任何增量时重试可重试错误。

缺少模型配置时抛出 `MODEL_NOT_CONFIGURED`，不得使用隐式默认模型。

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/providers -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/prism_agent_kit/core/ports.py src/prism_agent_kit/providers tests
git commit -m "feat: add OpenAI-compatible streaming provider"
```

---

### Task 9: Simple Agent Engine with Multiple Local Tools

**Files:**
- Create: `src/prism_agent_kit/core/engine.py`
- Modify: `src/prism_agent_kit/core/ports.py`
- Create: `tests/core/test_engine_local.py`

**Interfaces:**
- Consumes: `ModelProvider`、`ToolRegistry`、`PromptRegistry`、`ContextAssembler`、`UnitOfWorkFactory`、`EventPublisher`。
- Produces: `EventPublisher` Protocol；`EngineContext`；`EngineOutcome`；`AgentEngine` Protocol；`SimpleAgentEngine.execute()`；`SimpleAgentEngine.resume()`。

- [ ] **Step 1: Write failing local loop tests**

```python
async def test_engine_processes_every_tool_call_in_one_assistant_turn(
    engine: SimpleAgentEngine,
    seeded_run: Run,
    uow_factory: UnitOfWorkFactory,
) -> None:
    outcome = await engine.execute(EngineContext(run_id=seeded_run.id, cancel=asyncio.Event()))
    assert outcome.kind == "completed"
    async with uow_factory() as uow:
        calls = await uow.tool_calls.list_for_run(seeded_run.id)
        messages = await uow.messages.list_for_session(seeded_run.session_id)
    assert [call.status for call in calls] == [ToolCallStatus.SUCCEEDED] * 2
    assert [message.role for message in messages].count(MessageRole.TOOL) == 2


async def test_engine_stops_at_max_steps(
    configured_max_steps: int,
    always_calls_tool_model: ModelProvider,
) -> None:
    # 模型始终请求工具时，Run 必须失败并返回 HARNESS_STEP_LIMIT。
    ...
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/core/test_engine_local.py -v`

Expected: FAIL because `SimpleAgentEngine` does not exist.

- [ ] **Step 3: Implement the local Agent loop**

`execute()` 加载 Run 和历史，循环执行：

- 装配模型请求。
- 流式接收模型输出并发布临时事件。
- 持久化 assistant Message 与全部 ToolCall。
- 按顺序执行全部本地工具并持久化结果。
- 没有工具调用时写入最终 assistant Message 并把 Run 置为 `succeeded`。

`resume()` 复用相同循环，但从已经持久化的 tool Message 之后继续。

任何 Step 失败都必须在同一终态事务中关闭未完成 ToolCall。

`EventPublisher` 的最小接口固定为：

```python
class EventPublisher(Protocol):
    async def publish(self, event: EventEnvelope) -> None: ...
```

持久事件先在当前 UoW 中写入 `run_events`，事务提交后再调用 `EventPublisher.publish()`；提交失败时不得发布。

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/core/test_engine_local.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/prism_agent_kit/core tests/core
git commit -m "feat: execute multi-tool agent loop"
```

---

### Task 10: Remote Tool Suspension, Result Submission, and Closure

**Files:**
- Create: `src/prism_agent_kit/application/tool_result_service.py`
- Modify: `src/prism_agent_kit/core/engine.py`
- Create: `tests/application/test_remote_tools.py`

**Interfaces:**
- Consumes: Task 9 engine、`canonical_json_digest()`、ToolCall repository、history closure。
- Produces: `RemoteToolResult`；`ToolResultService.submit(run_id, call_id, input_digest, result) -> ToolCall`；Engine 的 `waiting_for_tools` outcome。

- [ ] **Step 1: Write failing remote tool tests**

```python
async def test_remote_tool_suspends_and_requeues_after_all_results(
    engine: SimpleAgentEngine,
    tool_result_service: ToolResultService,
) -> None:
    outcome = await engine.execute(context)
    assert outcome.kind == "waiting_for_tools"

    await tool_result_service.submit(run.id, "call-1", digest_1, {"ok": True, "output": {"a": 1}})
    await tool_result_service.submit(run.id, "call-2", digest_2, {"ok": True, "output": {"b": 2}})

    async with uow_factory() as uow:
        run = await uow.runs.get(run.id)
    assert run.status is RunStatus.QUEUED


async def test_cancel_closes_every_unfinished_remote_tool_call(
    engine: SimpleAgentEngine,
) -> None:
    # 取消后所有 ToolCall 都必须是 cancelled，且都有对应 tool Message。
    ...
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/application/test_remote_tools.py -v`

Expected: FAIL because remote result handling does not exist.

- [ ] **Step 3: Implement remote tool flow**

模型返回 `remote` 工具时：

- 持久化所有 ToolCall。
- 执行同轮本地工具。
- 若仍有 pending 远端调用，把 Run 置为 `waiting_for_tool` 并发布 `run.waiting_for_tool`。

`ToolResultService.submit()` 在单一事务中校验 Run、call ID、摘要、过期时间和输出 Schema，并调用 `ToolCallRepository.complete()`。全部完成后把 Run 从 `waiting_for_tool` 改为 `queued` 并写入 `run.requeued`。

取消和失败通过 `close_open_calls()` 补齐 tool Message。

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/application/test_remote_tools.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/prism_agent_kit tests/application
git commit -m "feat: support resumable remote tool calls"
```

---

### Task 11: In-Process Event Bus with Replay and Live Merge

**Files:**
- Create: `src/prism_agent_kit/application/event_bus.py`
- Modify: `src/prism_agent_kit/core/ports.py`
- Create: `tests/application/test_event_bus.py`

**Interfaces:**
- Consumes: `RunEvent` domain model。
- Produces: `EventEnvelope`；`RunEventBus.subscribe(run_id, after_event_id) -> AsyncIterator[EventEnvelope]`。

- [ ] **Step 1: Write failing bus tests**

```python
async def test_event_bus_merges_replay_and_live_without_duplicates(
    event_bus: RunEventBus,
    seeded_events: list[RunEvent],
) -> None:
    stream = event_bus.subscribe(run_id, after_event_id=1)
    first = await anext(stream)
    await event_bus.publish(_live_delta(run_id))
    second = await anext(stream)
    assert first.event_id == 2
    assert second.event_type is EventType.MESSAGE_DELTA


async def test_transient_delta_has_no_durable_event_id(event_bus: RunEventBus) -> None: ...
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/application/test_event_bus.py -v`

Expected: FAIL because `RunEventBus` does not exist.

- [ ] **Step 3: Implement replay/live event bus**

SSE 连接先注册 live subscriber，再查询 `after_event_id` 之后的持久事件。持久事件按 ID 去重。临时 delta 不带 SSE `id`。连接关闭时释放 subscriber。

使用 `asyncio.Condition` 或每订阅者队列；不得用阻塞轮询。

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/application/test_event_bus.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/prism_agent_kit/application tests/application
git commit -m "feat: stream merged persisted and live run events"
```

---

### Task 12: Run Worker, Cancellation, Recovery, and Expiry

**Files:**
- Create: `src/prism_agent_kit/application/run_worker.py`
- Create: `src/prism_agent_kit/application/cancellation.py`
- Create: `tests/application/test_run_worker.py`
- Create: `tests/application/test_recovery.py`

**Interfaces:**
- Consumes: `UnitOfWorkFactory`、`AgentEngine`、`ToolCallRepository`、`EventPublisher`。
- Produces: `RunCancellationRegistry`；`RunWorker.start()`；`RunWorker.stop()`；`RunWorker.run_once()`；`RunWorker.recover_interrupted_runs()`；`RunWorker.sweep_expired_tool_calls(now: datetime | None = None)`。

- [ ] **Step 1: Write failing worker tests**

```python
async def test_worker_claims_queued_run_and_invokes_engine(
    worker: RunWorker,
    fake_engine: RecordingEngine,
    queued_run: Run,
) -> None:
    await worker.run_once()
    assert fake_engine.executed == [queued_run.id]


async def test_startup_marks_running_run_interrupted_and_closes_tools(
    worker: RunWorker,
    running_run_with_open_tool: Run,
) -> None:
    await worker.recover_interrupted_runs()
    # Run 状态为 failed、错误码为 PROCESS_INTERRUPTED、ToolCall 有 tool Message。
    ...


async def test_expired_remote_tool_requeues_run(
    worker: RunWorker,
    waiting_run_with_expired_tool: Run,
) -> None:
    await worker.sweep_expired_tool_calls(now=NOW)
    # ToolCall=expired，Run=queued，事件为 REMOTE_TOOL_TIMEOUT。
    ...
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/application/test_run_worker.py tests/application/test_recovery.py -v`

Expected: FAIL because Worker and recovery logic do not exist.

- [ ] **Step 3: Implement worker lifecycle**

`RunWorker` 使用数据库 claim，不维护唯一事实队列。默认并发数来自 Settings。每个正在执行的 Run 在 `RunCancellationRegistry` 注册 `asyncio.Event`。

Worker 根据 Run 的 `step_count` 选择入口：`step_count == 0` 调用 `engine.execute()`；`step_count > 0` 表示该 Run 已从远端工具恢复，调用 `engine.resume()`。

启动恢复：

- `queued` 保持待 claim。
- `running` 置为 failed、关闭 ToolCall、写入终态事件。
- `waiting_for_tool` 保持；过期调用生成错误结果并重新排队。

周期任务只扫描过期 ToolCall，不重建执行到一半的模型流。

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/application/test_run_worker.py tests/application/test_recovery.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/prism_agent_kit/application tests/application
git commit -m "feat: run durable agent worker with recovery"
```

---

### Task 13: API Authentication, Request IDs, and Error Mapping

**Files:**
- Create: `src/prism_agent_kit/api/auth.py`
- Create: `src/prism_agent_kit/api/errors.py`
- Create: `src/prism_agent_kit/api/request_context.py`
- Create: `tests/api/test_auth.py`
- Create: `tests/api/test_error_mapping.py`

**Interfaces:**
- Consumes: `Settings.api_token`、`AgentKitError`。
- Produces: `ApiTokenMiddleware`；`RequestIdMiddleware`；`install_exception_handlers(app)`；统一错误 JSON。

- [ ] **Step 1: Write failing API boundary tests**

```python
def test_missing_token_returns_401(client: TestClient) -> None:
    response = client.get("/api/v1/protected")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


def test_agent_error_is_mapped_without_internal_details(
    app_with_failing_route: FastAPI,
) -> None:
    # 抛 AgentKitError(ErrorCode.RUN_CONFLICT) 时返回 409，且不含堆栈。
    ...
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/api/test_auth.py tests/api/test_error_mapping.py -v`

Expected: FAIL because auth and error handlers do not exist.

- [ ] **Step 3: Implement API infrastructure**

使用 ASGI middleware 和 `hmac.compare_digest()` 校验 Bearer Token；`/api/v1/health` 明确豁免。测试环境可在显式配置 `api_token=None` 时关闭鉴权；`environment != "test"` 且缺少 Token 时启动失败。

中间件为每个请求生成 `request_id` 并写入 response header。异常处理映射 `AgentKitError.http_status`，未分类异常统一返回 `INTERNAL`。

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/api/test_auth.py tests/api/test_error_mapping.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/prism_agent_kit/api tests/api
git commit -m "feat: add local API auth and error boundary"
```

---

### Task 14: Session and Run HTTP APIs

**Files:**
- Create: `src/prism_agent_kit/api/schemas.py`
- Create: `src/prism_agent_kit/api/routes/sessions.py`
- Create: `src/prism_agent_kit/api/routes/runs.py`
- Create: `src/prism_agent_kit/application/session_service.py`
- Create: `src/prism_agent_kit/application/run_service.py`
- Modify: `src/prism_agent_kit/api/router.py`
- Create: `tests/api/test_sessions.py`
- Create: `tests/api/test_runs.py`

**Interfaces:**
- Consumes: UoW、PromptRegistry、Run model、Task 13 auth/errors。
- Produces: `SessionCreate`、`SessionView`、`RunCreate`、`RunView`；`SessionService.create/list/get/list_messages`；`RunService.create/get/cancel`；`create_sessions_router(service)`；`create_runs_router(service)`。

- [ ] **Step 1: Write failing endpoint tests**

```python
def test_create_session_and_run(client: TestClient) -> None:
    session = client.post("/api/v1/sessions", json={"title": "demo"}).json()
    response = client.post(
        f"/api/v1/sessions/{session['id']}/runs",
        json={"input": "hello", "prompt_ref": "default@1", "metadata": {"client": "test"}},
    )
    assert response.status_code == 202
    assert response.json()["status"] == "queued"


def test_second_active_run_is_rejected(client: TestClient) -> None:
    # 同 Session 第二次创建 Run 返回 409 RUN_CONFLICT。
    ...


def test_unknown_prompt_version_is_rejected(client: TestClient) -> None:
    # prompt_ref=missing@1 返回 422 PROMPT_NOT_FOUND。
    ...
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/api/test_sessions.py tests/api/test_runs.py -v`

Expected: FAIL because services and routes do not exist.

- [ ] **Step 3: Implement services and routes**

`POST /sessions/{id}/runs` 在一个事务中写入 user Message、Run 和 `run.queued` 事件。Prompt 解析失败、Session 不存在和活动 Run 冲突分别返回稳定错误码。`GET /sessions/{id}/messages` 返回按全局 Message ID 排序的消息。

路由只做 DTO 转换和调用 Service，不允许直接构造 SQLAlchemy 查询。

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/api/test_sessions.py tests/api/test_runs.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/prism_agent_kit tests/api
git commit -m "feat: expose session and run APIs"
```

---

### Task 15: SSE Run Event Stream

**Files:**
- Modify: `src/prism_agent_kit/api/routes/runs.py`
- Create: `tests/api/test_sse.py`

**Interfaces:**
- Consumes: `RunEventBus`、`EventRepository`、`RunService`。
- Produces: `GET /api/v1/runs/{run_id}/events` SSE；`Last-Event-ID` 重放；可更新 `RunView` 终态。

- [ ] **Step 1: Write failing SSE tests**

```python
def test_sse_replays_events_after_last_event_id(client: TestClient) -> None:
    response = client.get(
        f"/api/v1/runs/{run_id}/events",
        headers={"Last-Event-ID": "evt_1"},
        params={"once": "true"},
    )
    assert response.status_code == 200
    assert "id: evt_2" in response.text
    assert "id: evt_1" not in response.text


def test_sse_emits_terminal_event_and_closes(client: TestClient) -> None: ...
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/api/test_sse.py -v`

Expected: FAIL because SSE route does not exist.

- [ ] **Step 3: Implement SSE**

使用 `sse-starlette`。先订阅 live，再按 `Last-Event-ID` 查询持久事件，按 event ID 去重。`message.delta`/`reasoning.delta` 不带 `id`。发送心跳；终态事件后关闭。

测试专用 `once=true` 参数只在 `environment=test` 时可用，用于有界读取，不进入正式客户端协议。

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/api/test_sse.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/prism_agent_kit/api tests/api
git commit -m "feat: stream run events over SSE"
```

---

### Task 16: Tool Result, Cancel, and Tool Discovery APIs

**Files:**
- Modify: `src/prism_agent_kit/api/routes/runs.py`
- Create: `src/prism_agent_kit/api/routes/tools.py`
- Modify: `src/prism_agent_kit/api/router.py`
- Create: `tests/api/test_tool_results.py`
- Create: `tests/api/test_cancel.py`
- Create: `tests/api/test_tools.py`

**Interfaces:**
- Consumes: `ToolResultService`、`RunCancellationRegistry`、`ToolRegistry`。
- Produces: `create_tool_routes(...)`；`POST /runs/{id}/tool-calls/{call_id}/result`；`POST /runs/{id}/cancel`；`GET /tools`。

- [ ] **Step 1: Write failing endpoint tests**

```python
def test_tool_result_requires_matching_digest(client: TestClient) -> None:
    response = client.post(
        f"/api/v1/runs/{run_id}/tool-calls/call-1/result",
        json={"ok": True, "input_digest": "sha256:wrong", "output": {}},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "TOOL_INPUT_DIGEST_MISMATCH"


def test_duplicate_identical_result_is_idempotent(client: TestClient) -> None: ...


def test_invalid_remote_output_keeps_tool_pending(client: TestClient) -> None:
    # 输出 Schema 不合法时返回 422 TOOL_OUTPUT_INVALID，ToolCall 仍为 pending。
    ...


def test_tools_returns_input_and_output_json_schema(client: TestClient) -> None:
    tools = client.get("/api/v1/tools").json()["items"]
    assert tools[0]["execution_mode"] in {"local", "remote"}
    assert tools[0]["input_schema"]["type"] == "object"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/api/test_tool_results.py tests/api/test_cancel.py tests/api/test_tools.py -v`

Expected: FAIL because these routes do not exist.

- [ ] **Step 3: Implement routes**

工具结果路由保持 409/422/404 的明确区分。取消路由对 queued、running 和 waiting Run 都有效。工具发现只返回名称、描述、执行方式和 JSON Schema。

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/api/test_tool_results.py tests/api/test_cancel.py tests/api/test_tools.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/prism_agent_kit/api tests/api
git commit -m "feat: expose remote tool and cancellation APIs"
```

---

### Task 17: Application Container, Lifespan Wiring, and End-to-End Acceptance

**Files:**
- Create: `src/prism_agent_kit/application/container.py`
- Modify: `src/prism_agent_kit/main.py`
- Modify: `src/prism_agent_kit/api/router.py`
- Modify: `README.md`
- Modify: `AGENTS.md` only if implementation commands changed
- Create: `tests/test_agent_e2e.py`
- Modify: `tests/conftest.py`

**Interfaces:**
- Consumes: all previous tasks。
- Produces: `ApplicationContainer`；FastAPI lifespan 创建 Database、EventBus、Engine、Worker 和 Services；可注入 `ModelProvider`/`ToolRegistry` 供测试替换；数据库文件进程锁。

- [x] **Step 1: Write failing end-to-end tests**

```python
def test_text_run_streams_and_persists_history(app_client: TestClient) -> None:
    session = app_client.post("/api/v1/sessions", json={}).json()
    run = app_client.post(
        f"/api/v1/sessions/{session['id']}/runs",
        json={"input": "hello", "prompt_ref": "default@1"},
    ).json()
    events = app_client.get(f"/api/v1/runs/{run['id']}/events", params={"once": "true"})
    assert "event: run.succeeded" in events.text
    messages = app_client.get(f"/api/v1/sessions/{session['id']}/messages").json()
    assert [item["role"] for item in messages["items"]] == ["user", "assistant"]


def test_remote_tool_survives_worker_restart(app_container: ApplicationContainer) -> None:
    # 第一轮执行进入 waiting_for_tool；重建 Worker 后提交结果，Run 最终 succeeded。
    ...


def test_second_container_cannot_lock_same_database(tmp_path: Path) -> None:
    # 同一数据库路径的第二个 ApplicationContainer 启动时抛出明确错误。
    ...
```

- [x] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_agent_e2e.py -v`

Expected: FAIL because application container and lifespan wiring do not exist.

- [x] **Step 3: Implement dependency assembly**

`ApplicationContainer` 只负责构造对象，不包含业务分支。lifespan 顺序：

1. 解析并校验 Settings。
2. 获取数据库文件进程锁。
3. 创建 Database。
4. 执行启动恢复。
5. 创建 EventBus、Engine、Services、Worker。
6. 启动 Worker。
7. 退出时停止 Worker、释放订阅者、dispose Database、释放进程锁。

`create_app(settings)` 将 Container 放入 `app.state`，FastAPI dependency 从 `request.app.state` 获取。

Container 在启动时注册内置 `default@1` 系统提示词，并允许测试通过构造参数替换 `ModelProvider` 和 `ToolRegistry`。E2E 测试使用脚本化模型，不访问网络。

- [x] **Step 4: Run complete quality gates**

Run:

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pytest
```

Expected: 全部通过；测试不得访问真实模型 API。

- [x] **Step 5: Update user documentation**

README 增加本地运行、SQLite 路径、模型环境变量、API Token、Alembic 和测试命令。不得写入真实密钥。

- [x] **Step 6: Commit**

```bash
git add src tests README.md AGENTS.md
git commit -m "feat: assemble local Python agent runtime"
```

## Self-Review

**Spec coverage:**

- FastAPI、原生 HTTP/SSE：Task 13–17。
- SQLite 持久化与迁移：Task 1、3、4、5。
- Session/Run/Message/ToolCall/RunEvent：Task 2–5。
- Prompt、token 预算、上下文裁剪：Task 6。
- 本地与远端工具：Task 7、9、10。
- OpenAI-compatible 模型：Task 8。
- 取消、恢复、过期与 Worker：Task 10–12。
- 安全、鉴权、错误边界：Task 13、17。
- 历史闭合不变量：Task 5、10、12。
- SSE 重放与实时合并：Task 11、15。
- 验收与文档：Task 17。
- MCP、Workspace、LangChain、LangGraph、LangSmith：明确不在本计划内。

**Open implementation decisions:** 无。测试辅助工具的具体组织可以调整，但不得改变任务产出的公开接口或行为。
