# PrismAgentKit Python Agent Core 技术设计

- 日期：2026-11-22
- 状态：已确认
- 范围：Python Core、FastAPI BFF、SQLite 持久化
- 上游参考：Node.js Agent Kit。仅参考领域经验与安全不变量，不做协议或表结构兼容。
- 选定方向：自研 Python Core + FastAPI

## 1. 背景与意图

PrismAgentKit 的 Python 版本不准备对现有 Node.js Agent Runtime 做 1:1 迁移。现有 UI 和浏览器扩展会重新设计，因此 Python 版可以重新定义更符合本地 Agent、Python 类型系统和长期演进需要的协议。

首版交付一个可在本地独立运行的 Agent Runtime：

- FastAPI 暴露 HTTP 与 SSE。
- SQLite 保存 Session、Run、Message、ToolCall 和持久事件。
- 自研单 Agent 执行循环，支持一轮多个工具调用、本地工具和远端工具结果回填。
- 通过 OpenAI-compatible 接口调用模型。
- 不依赖 LangChain、LangGraph、PydanticAI 或 MCP SDK。

Node.js 版本中的以下行为仍作为设计参考：

- 一轮模型响应中的全部工具调用都必须处理。
- assistant 发起的工具调用与对应 tool 结果必须成对保存。
- 挂起工具调用必须校验 Session、call ID 和输入一致性。
- 密钥、Prompt 正文、模型原文和业务上下文不得进入普通日志。
- 模型可见的历史必须能够从持久化数据重建。

## 2. 目标

### 2.1 功能目标

- 创建和管理 Session。
- 在 Session 内创建 Run，并异步执行 Agent。
- 支持 OpenAI-compatible Chat Completions。
- 支持文本流式输出。
- 支持 Python 进程内工具和需要外部宿主回填结果的远端工具。
- 支持一个 assistant 轮次发起多个工具调用。
- 支持 Run 取消、工具超时、模型超时和最大步数限制。
- 支持 SSE 实时事件和持久事件重放。
- 服务重启后保留完整历史；等待远端工具的 Run 可以继续。
- 通过 Alembic 管理 SQLite Schema。

### 2.2 工程目标

- HTTP DTO、领域逻辑、Agent 循环、模型适配和持久化分层。
- 所有跨进程边界使用 Pydantic 模型校验。
- Core 不导入 FastAPI。
- `AgentEngine`、`ModelProvider`、`ToolProvider` 和 Repository 均通过接口注入。
- 测试不依赖真实模型 API。
- 单进程本地运行，不引入 Redis、Celery、消息队列或独立 Worker 服务。

## 3. 非目标

- 兼容 Node.js 现有 URL、请求体、响应体或 SQLite 表结构。
- 实现 MCP Client、MCP Server 管理或 MCP 凭据 UI。
- 实现 Workspace、文件索引、RAG、向量检索或设备控制。
- 实现多 Agent、Subagent、Team 或工作流图。
- 实现多租户、公网部署、分布式调度或 Postgres 生产部署。
- 实现完整的上下文摘要压缩。
- 实现模型档案管理 UI 或 SQLite 加密密钥库。
- 实现前端、桌面壳或浏览器扩展。
- 第一版即接入 LangChain、LangGraph、PydanticAI 或 LangSmith。

## 4. 反目标

- 用自研类名包装 LangChain，却不掌握 Agent 循环和状态语义。
- 只把完整 messages 数组存成一段 JSON，无法独立查询 Run 和 ToolCall。
- 把 LangSmith、日志或 SSE 当作业务状态事实源。
- 在 FastAPI 路由中直接实现模型循环、工具执行或数据库事务。
- 使用无类型的 `dict[str, Any]` 贯穿领域层。
- 为未来可能使用的复杂工作流提前引入图编排框架。
- 在模型流已经开始输出后自动重试并产生重复文本。
- 静默丢弃模型一轮中的部分工具调用。

## 5. 约束

- Python 3.12。
- FastAPI + Uvicorn。
- Pydantic v2 和 pydantic-settings。
- SQLAlchemy 2 Async + `aiosqlite`。
- Alembic。
- OpenAI Python SDK，通过 `base_url` 对接 OpenAI-compatible 服务。
- SSE 使用 `sse-starlette`。
- Token 预算使用可配置的 `tiktoken` encoding 估算。
- 本地单进程运行，API 默认只绑定 `127.0.0.1`。
- SQLite 使用 WAL、外键约束和短事务。
- 时间统一以 UTC 存储，API 使用 ISO 8601 返回。
- 代码标识符使用英文；函数、变量和复杂逻辑使用中文注释。
- 默认不做字段兜底；无法确认的输入显式报错。

## 6. 方案选择

### 6.1 方案一：自研 Python Core + FastAPI

自研 Agent 循环、工具调度、Run 状态机和事件模型；FastAPI 提供本地 BFF。

- 协议和领域模型完全可控。
- 可以精确设计远端工具、恢复、取消、幂等和事件语义。
- 后续可以把 LangChain、LangGraph 或 PydanticAI 作为 `AgentEngine` 适配器。
- 需要自行实现模型流解析、工具循环和恢复逻辑。

### 6.2 方案二：PydanticAI 作为核心

由 PydanticAI 负责模型调用和 Agent 工具循环，项目补充持久化和 API。

- 首版速度快，Python 类型体验好。
- 核心执行行为受第三方框架约束。
- 挂起工具、恢复和领域事件需要围绕框架能力适配。

### 6.3 方案三：LangGraph 作为核心

使用状态图和 Checkpointer 作为 Agent 执行基础。

- 适合复杂分支、多步骤和人工介入。
- 对单 Agent 首版偏重。
- SQLite 持久化与事件模型容易受框架结构影响。

### 6.4 决策

选择方案一。

Node.js 版本和第三方 Agent 框架只提供思想与经验。Python Core 自己拥有 Session、Run、Message、ToolCall、Event 和状态转换；未来框架通过 `AgentEngine` 接口接入，不进入领域模型。

## 7. 总体架构

```text
FastAPI Routes
    |
Application Services
    |-- SessionService
    |-- RunService
    |-- ToolResultService
    |-- EventStreamService
    |
RunCoordinator / RunWorker
    |
AgentEngine
    |-- SimpleAgentEngine
    `-- Future LangGraphEngine
    |
Ports
    |-- ModelProvider
    |-- ToolProvider
    |-- SessionRepository
    |-- RunRepository
    |-- MessageRepository
    |-- ToolCallRepository
    `-- EventRepository
    |
SQLAlchemy Async -> SQLite
```

### 7.1 分层职责

- `api/`：HTTP 参数、认证、响应映射和 SSE 输出。
- `application/`：用例编排、Run 状态转换、事务边界和后台调度。
- `core/`：Agent 循环、Prompt、上下文装配、事件和领域错误。
- `providers/`：OpenAI-compatible 模型适配。
- `tools/`：工具定义、注册、校验和执行。
- `db/`：ORM 模型、Repository、Session 工厂和迁移。

### 7.2 关键接口

```python
class AgentEngine(Protocol):
    async def execute(self, context: EngineContext) -> EngineOutcome: ...
    async def resume(self, context: EngineContext) -> EngineOutcome: ...


class ModelProvider(Protocol):
    async def stream(
        self,
        request: ModelRequest,
        on_delta: DeltaSink,
    ) -> ModelResponse: ...


class ToolProvider(Protocol):
    def list_tools(self) -> list[ToolDefinition]: ...
    def get(self, name: str) -> ToolDefinition | None: ...
```

`AgentEngine` 只能依赖 Port，不依赖 FastAPI、SQLAlchemy Session 或具体模型 SDK。`EngineOutcome` 只表达：

- `completed`：Run 已完成并产生最终输出。
- `waiting_for_tools`：存在尚未回填的远端工具调用。
- `failed`：Run 以稳定错误码失败。

## 8. 领域模型

### 8.1 Session

一个 Session 表示连续的对话上下文。

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | UUID string | Session 主键 |
| `title` | string/null | 可空标题 |
| `created_at` | UTC datetime | 创建时间 |
| `updated_at` | UTC datetime | 最近活动时间 |

首版为本地单用户服务。Session 不包含 Workspace、设备或组织信息。

### 8.2 Run

一个 Run 表示一次用户输入触发的完整 Agent 执行。

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | UUID string | Run 主键 |
| `session_id` | UUID string | 所属 Session |
| `status` | enum | `queued/running/waiting_for_tool/succeeded/failed/cancelled` |
| `input_text` | string | 本次用户输入 |
| `prompt_name` | string | 使用的 Prompt 名 |
| `prompt_version` | string | Prompt 版本 |
| `system_prompt` | string | 本次 Run 的系统提示词快照 |
| `model` | string | 本次请求使用的模型名 |
| `step_count` | integer | 已执行的模型请求次数 |
| `output_text` | string/null | 最终文本输出 |
| `error_code` | string/null | 稳定错误码 |
| `error_message` | string/null | 脱敏错误信息 |
| `cancel_requested_at` | UTC datetime/null | 取消请求时间 |
| `created_at` | UTC datetime | 创建时间 |
| `started_at` | UTC datetime/null | 开始执行时间 |
| `finished_at` | UTC datetime/null | 终止时间 |

同一 Session 同时最多存在一个非终止 Run。通过 SQLite partial unique index 保证：

```sql
CREATE UNIQUE INDEX ux_runs_one_active_per_session
ON runs(session_id)
WHERE status IN ('queued', 'running', 'waiting_for_tool');
```

### 8.3 Message

Message 是模型可见历史的权威来源。每个 Run 至少产生一条 user Message；模型产生的 assistant 和 tool Message 也逐条保存。

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | integer autoincrement | 全局顺序 |
| `session_id` | UUID string | 所属 Session |
| `run_id` | UUID string | 产生或消费该消息的 Run |
| `role` | enum | `user/assistant/tool` |
| `content` | JSON | 文本或多模态内容 |
| `reasoning` | string/null | 模型 reasoning 内容，仅 assistant |
| `tool_call_id` | string/null | 仅 tool Message |
| `created_at` | UTC datetime | 创建时间 |

System Prompt 存在 `runs.system_prompt` 快照中，不重复写入历史 Message。

### 8.4 ToolCall

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | string | 模型返回或 Core 生成的 call ID |
| `run_id` | UUID string | 所属 Run |
| `assistant_message_id` | integer | 发起调用的 assistant Message |
| `tool_name` | string | 注册工具名 |
| `execution_mode` | enum | `local/remote` |
| `status` | enum | `pending/running/succeeded/failed/expired/cancelled` |
| `input` | JSON | 工具输入 |
| `output` | JSON/null | 工具输出 |
| `input_digest` | string | `sha256:` 前缀的规范化输入摘要，供远端宿主回显 |
| `error_code` | string/null | 稳定错误码 |
| `error_message` | string/null | 脱敏错误信息 |
| `expires_at` | UTC datetime/null | 远端工具回填截止时间 |
| `created_at` | UTC datetime | 创建时间 |
| `finished_at` | UTC datetime/null | 完成时间 |

### 8.5 RunEvent

RunEvent 保存可重放的产品事件和状态事实，不保存模型流式 token。

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | integer autoincrement | 事件游标 |
| `run_id` | UUID string | 所属 Run |
| `event_type` | string | 稳定事件名 |
| `payload` | JSON | 非敏感事件数据 |
| `created_at` | UTC datetime | 创建时间 |

持久事件至少包括：

- `run.queued`
- `run.started`
- `assistant.completed`
- `tool.requested`
- `tool.completed`
- `tool.failed`
- `tool.expired`
- `run.waiting_for_tool`
- `run.requeued`
- `context.trimmed`
- `run.succeeded`
- `run.failed`
- `run.cancelled`

`message.delta` 和 `reasoning.delta` 只存在于 SSE，不写入 RunEvent。

## 9. Run 状态机

```text
queued
  -> running
  -> waiting_for_tool
  -> queued
  -> running
  -> succeeded | failed | cancelled
```

规则：

- `queued` 可以由用户取消。
- 进入 `running` 时只允许一次原子 claim。
- 模型返回多个工具调用时，先完成本地工具，再等待全部远端工具。
- 当前 assistant 轮次的所有 ToolCall 都完成后，Run 在同一事务中从 `waiting_for_tool` 转为 `queued`；Worker 再按正常 claim 流程进入 `running`。
- 达到最大步数时以 `HARNESS_STEP_LIMIT` 失败。
- 取消是协作式的：worker 设置取消标记、取消当前模型请求或工具任务，并在安全点写入终态。
- 已进入终态的 Run 不允许再次推进。
- 进入任何终态前，必须闭合该 Run 已落库 assistant Message 发起的全部 ToolCall。
- 进程重启时：
  - `queued` Run 重新入队。
  - `running` Run 标记为 `PROCESS_INTERRUPTED` 失败，并在同一事务中为所有未完成 ToolCall 写入错误 tool Message。
  - `waiting_for_tool` Run 保持可恢复；过期的远端 ToolCall 标记为 `expired`。

### 9.1 历史闭合不变量

只要一个 assistant Message 已经落库，它发起的每个 ToolCall 最终都必须有一条对应的 tool Message，即使 Run 失败、取消或进程中断。

闭合工具结果使用稳定的错误码：

- `RUN_CANCELLED`
- `PROCESS_INTERRUPTED`
- `TOOL_EXECUTION_TIMEOUT`
- `REMOTE_TOOL_TIMEOUT`
- `TOOL_EXECUTION_FAILED`
- `TOOL_INPUT_INVALID`
- `TOOL_OUTPUT_INVALID`

终态事务负责为尚未完成的 ToolCall 补齐合成错误结果。ContextAssembler 遇到未闭合工具组时必须 fail closed，不能静默跳过整个 Run 或丢弃 assistant Message。

## 10. Agent 执行流程

### 10.1 创建 Run

1. API 校验 Session 存在且没有活动 Run。
2. 事务内创建 user Message、Run 和 `run.queued` 事件。
3. API 返回 `202` 和 Run 视图。
4. `RunWorker` 异步 claim 并执行。

### 10.2 模型请求

1. 加载 Session 历史、当前 Run 和全部工具定义。
2. `ContextAssembler` 生成模型请求。
3. `ModelProvider.stream()` 发起流式请求。
4. 文本和 reasoning 增量作为临时 SSE 事件发送，不写入 SQLite。
5. 模型完成后：
   - 持久化 assistant Message。
   - 持久化 assistant 发起的全部 ToolCall。
   - 写入 `assistant.completed` 和 `tool.requested` 事件。

### 10.3 工具执行

- 本地工具由 Core 直接执行。
- 远端工具不执行，等待外部宿主提交结果。
- 本地工具与远端工具可以出现在同一 assistant 轮次。
- 所有工具输入先通过 Pydantic Schema 校验。
- 工具运行失败或本地工具超时作为 tool 错误结果返回给模型，Agent 继续下一步。
- 工具输入或输出违反 Schema 属于契约失败，Run 直接失败，并闭合本轮其余未完成工具调用。
- Run 取消时，当前及尚未开始的本地工具转为 `cancelled`，不继续模型循环。
- 本地工具按顺序执行，保证事件和持久化顺序确定。后续可以在不改变协议的前提下增加并发上限。

### 10.4 远端工具结果

外部宿主调用：

```http
POST /api/v1/runs/{run_id}/tool-calls/{call_id}/result
```

成功结果：

```json
{
  "ok": true,
  "input_digest": "sha256:...",
  "output": {}
}
```

失败结果：

```json
{
  "ok": false,
  "input_digest": "sha256:...",
  "error": {
    "code": "BROWSER_ACTION_FAILED",
    "message": "页面元素不存在"
  }
}
```

事务内完成：

1. 校验 Run 属于 `waiting_for_tool`。
2. 校验 ToolCall 属于当前 Run 且仍为 `pending`。
3. 校验提交的 `input_digest` 与持久化值完全一致。
4. 成功结果通过输出 Schema 校验。
5. 校验未过期。
6. 写入 tool Message。
7. 更新 ToolCall 为终态。
8. 写入 `tool.completed` 或 `tool.failed` 事件。
9. 若当前轮次所有 ToolCall 均已完成，将 Run 从 `waiting_for_tool` 原子转为 `queued`，写入 `run.requeued` 事件。

摘要计算规则：

- 对 ToolCall `input` 使用 UTF-8、键排序、无多余空白的规范 JSON。
- 摘要为 `sha256:<hex>`。
- `tool.requested` 事件携带该摘要；宿主回填时必须原样带回，Core 不信任宿主重新序列化后的内容。

重复提交完全相同的结果视为幂等成功；同一 call ID 提交不同结果返回 `409 TOOL_RESULT_CONFLICT`。输出 Schema 不合法返回 `422 TOOL_OUTPUT_INVALID`，ToolCall 保持 `pending`，允许宿主修正后重试。过期结果返回 `409 TOOL_CALL_EXPIRED`。

## 11. HTTP 协议

统一前缀：`/api/v1`。

### 11.1 Endpoints

| Method | Path | 说明 |
|---|---|---|
| `GET` | `/health` | 健康检查 |
| `POST` | `/sessions` | 创建 Session |
| `GET` | `/sessions` | 列出 Session |
| `GET` | `/sessions/{session_id}` | 获取 Session |
| `GET` | `/sessions/{session_id}/messages` | 获取会话消息 |
| `POST` | `/sessions/{session_id}/runs` | 创建并异步启动 Run |
| `GET` | `/runs/{run_id}` | 获取 Run |
| `GET` | `/runs/{run_id}/events` | SSE 事件流 |
| `POST` | `/runs/{run_id}/tool-calls/{call_id}/result` | 回填远端工具结果 |
| `POST` | `/runs/{run_id}/cancel` | 取消 Run |
| `GET` | `/tools` | 列出已注册工具及 Schema |

### 11.2 创建 Run

```json
{
  "input": "帮我检查项目状态",
  "prompt_ref": "default@1",
  "metadata": {}
}
```

- `input` 必须是非空字符串。
- `prompt_ref` 使用明确的 `name@version`，可省略；省略时使用 `PRISM_AGENT_KIT_DEFAULT_PROMPT_REF`。
- `metadata` 只用于客户端关联，不进入模型上下文。
- 返回 `202`：

```json
{
  "id": "run_uuid",
  "session_id": "session_uuid",
  "status": "queued",
  "created_at": "2026-11-22T08:00:00Z"
}
```

### 11.3 SSE

事件格式：

```text
event: message.delta
data: {"type":"message.delta","run_id":"...","text":"你"}
```

持久事件额外带 SSE `id`，例如：

```text
id: evt_42
event: tool.requested
data: {"type":"tool.requested","run_id":"...","call_id":"...","tool_name":"browser_click","input":{}}
```

- 客户端通过 `Last-Event-ID` 请求缺失的持久事件。
- `message.delta` 和 `reasoning.delta` 是临时事件，不持久化，也没有 SSE `id`。
- 断线期间可能错过的增量文本由最终 assistant Message 恢复。
- 每 15 秒发送 SSE 注释心跳。
- Run 进入终态后，服务端发送终态事件并关闭连接。

### 11.4 错误响应

```json
{
  "error": {
    "code": "RUN_CONFLICT",
    "message": "当前 Session 已有活动 Run",
    "request_id": "req_...",
    "details": {}
  }
}
```

HTTP 映射：

- `400`：请求结构或业务参数非法。
- `401`：本地 API Token 无效。
- `404`：Session、Run、ToolCall 不存在。
- `409`：活动 Run 冲突、重复结果冲突、状态不允许。
- `422`：Pydantic 校验失败或工具结果 Schema 不合法。
- `429`：本地并发或模型限流。
- `502`：模型上游协议或服务错误。
- `504`：模型或工具超时。
- `500`：未分类内部错误，不返回敏感细节。

## 12. SQLite 持久化

### 12.1 表

- `sessions`
- `runs`
- `messages`
- `tool_calls`
- `run_events`
- `alembic_version`

不使用 Node.js 的 `agent_sessions.messages` 大 JSON 字段。

### 12.2 索引

- `messages(session_id, id)`
- `runs(session_id, created_at)`
- `runs(status)`
- `tool_calls(run_id, status)`
- `run_events(run_id, id)`
- 同一 Session 的活动 Run partial unique index

### 12.3 事务原则

- 模型调用和工具执行期间不持有数据库事务。
- Message、ToolCall、Run 状态和 RunEvent 的相关写入放在同一个短事务中。
- 远端工具结果提交必须原子更新 ToolCall 并插入 tool Message。
- Run claim 使用条件更新，禁止两个 worker 同时推进同一 Run。
- SQLite 启动时设置：

```sql
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;
PRAGMA busy_timeout = 5000;
PRAGMA synchronous = NORMAL;
```

### 12.4 数据库路径

- 通过 `PRISM_AGENT_KIT_DATABASE_PATH` 显式配置。
- 未配置时使用 `platformdirs` 解析当前用户的数据目录。
- 数据库文件权限在支持 POSIX 权限的平台上限制为当前用户。

## 13. 模型与上下文

### 13.1 OpenAI-compatible Provider

首版只实现一个 Provider：

- 使用 OpenAI Python SDK 的 `AsyncOpenAI`。
- `base_url` 可配置，用于 DeepSeek 或其他兼容服务。
- 支持文本流、tool calls 增量聚合、reasoning content 和 usage。
- 工具调用参数可能被拆成多个增量，必须按调用索引完整聚合后再解析 JSON。
- 模型返回 JSON 无法解析、工具调用缺少 call ID 或响应结构非法时，Run 以 `MODEL_PROTOCOL_INVALID` 失败。

### 13.2 重试策略

- 仅在尚未收到任何模型增量前重试连接失败、`429` 和可重试 `5xx`。
- 默认最多重试 2 次，使用有上限的指数退避。
- 已经输出增量后不自动重试，避免重复文本。
- 工具默认不自动重试；工具是否幂等由工具实现自行声明和处理。

### 13.3 模型配置

首版通过环境变量提供单一模型配置：

- `PRISM_AGENT_KIT_MODEL_BASE_URL`
- `PRISM_AGENT_KIT_MODEL_API_KEY`
- `PRISM_AGENT_KIT_MODEL_NAME`
- `PRISM_AGENT_KIT_MODEL_CONTEXT_WINDOW`
- `PRISM_AGENT_KIT_MODEL_MAX_OUTPUT_TOKENS`
- `PRISM_AGENT_KIT_MODEL_TOKEN_ENCODING`
- `PRISM_AGENT_KIT_MODEL_TIMEOUT_SECONDS`

首版不把模型密钥写入 SQLite。后续模型设置 UI 使用独立加密 Secret Store。

### 13.4 Prompt

- `PromptRegistry` 在 Python 代码中注册 `name@version`。
- 创建 Run 时通过 `prompt_ref` 精确选择版本，不接受只给名称然后猜测最新版。
- 应用通过 `PRISM_AGENT_KIT_DEFAULT_PROMPT_REF` 配置默认 Prompt。
- Run 创建时解析 Prompt，并把系统提示词正文快照写入 Run。
- 同名同版本重复注册报错。
- Prompt 输出协议不在首版实现；首版模型输出只要求文本和标准 tool calls。

### 13.5 上下文装配

- 按 Message 全局 ID 顺序组装。
- assistant Message 与它发起的全部 tool Message 作为不可拆分单元。
- 只允许在完整单元边界裁剪旧历史。
- 当前用户输入永远保留；如果当前输入单独超过输入预算，返回 `CONTEXT_BUDGET_EXCEEDED`。
- 首版按配置的 token 预算执行裁剪，不调用模型生成摘要。
- 裁剪只影响本次模型请求，不删除 SQLite 历史。
- 每次裁剪写入 `context.trimmed` 持久事件，记录删除的消息数和估算 token 数，不记录消息正文。

Token 预算规则：

- `TokenEstimator` 是可替换 Port。
- 首版实现使用 `tiktoken`，encoding 由 `PRISM_AGENT_KIT_MODEL_TOKEN_ENCODING` 显式配置。
- 输入预算 = `context_window - max_output_tokens - safety_margin_tokens`。
- system prompt、工具 Schema、消息内容、message framing overhead 都计入输入预算。
- `safety_margin_tokens` 由 `PRISM_AGENT_KIT_CONTEXT_SAFETY_MARGIN_TOKENS` 配置，用于吸收不同 Provider tokenizer 的偏差。
- 工具 Schema 或 system prompt 单独超出预算时，Run 以 `CONTEXT_BUDGET_EXCEEDED` 失败。
- 不使用字符数近似作为隐式兜底。

## 14. 工具系统

### 14.1 ToolDefinition

```python
class ToolDefinition(BaseModel):
    name: str
    description: str
    input_model: type[BaseModel]
    output_model: type[BaseModel] | None
    execution_mode: Literal["local", "remote"]
    timeout_seconds: float
```

- 工具名必须匹配 `^[a-zA-Z0-9_-]+$`。
- 输入 Schema 顶层必须是 object。
- 使用 Pydantic `model_json_schema()` 生成模型工具声明。
- 内部 `$defs` 保留，不做静默扁平化或删除约束。

### 14.2 本地工具

- 实现 `async execute(input, context) -> output`。
- 同步工具必须显式通过 `asyncio.to_thread()` 包装，或只提供异步实现。
- 执行上下文包含 `run_id`、`call_id`、`session_id`、取消令牌和进度回调。
- 进度回调只用于事件展示，不进入模型上下文。

### 14.3 远端工具

- 远端工具只声明 Schema 和超时，不包含执行函数。
- 模型请求远端工具时，Core 产生 `tool.requested` 并进入等待状态。
- 外部宿主只能回填已经存在的 call ID。
- 结果必须通过输出 Schema 校验。
- 超时后拒绝迟到结果，并写入 `tool.expired`。

## 15. 后台执行与恢复

- FastAPI lifespan 启动 `RunWorker`。
- `RunWorker` 使用应用内 asyncio 调度，不引入独立服务。
- 首版单进程运行，启动时获取数据目录进程锁，防止多个实例同时写同一 SQLite。
- Worker 默认并发数为 2；同一 Session 仍由 partial unique index 保证串行。
- Worker 从数据库 claim Run，不依赖只存在于内存的队列状态。
- Worker 周期扫描已超过 `expires_at` 的远端 ToolCall，写入 `REMOTE_TOOL_TIMEOUT` 工具结果并将 Run 重新排队。
- 取消信号通过 `asyncio.Event` 传递，生命周期由 RunCoordinator 管理。
- 进程异常退出后，不尝试恢复执行到一半的模型流或本地工具。

## 16. 安全

- API 默认绑定 `127.0.0.1`。
- 非测试环境要求配置 `PRISM_AGENT_KIT_API_TOKEN`。
- 所有 API 使用 `Authorization: Bearer <token>`；Token 比较使用常量时间比较。
- CORS 只允许配置的 UI Origin，不使用通配符。
- 工具只能通过显式注册提供给模型。
- 模型不能动态注册工具或执行任意 Python 代码。
- 日志记录 `request_id/session_id/run_id/call_id/tool_name/error_code`，不记录 Prompt 正文、模型原文、密钥或工具结果正文。
- 错误响应不包含密钥、Prompt、原始上游响应体或堆栈。
- SSE 和事件 Payload 不包含系统提示词正文、API Key 或模型 reasoning 全文。
- `/tools` 可以返回工具 Schema，但不返回敏感默认值。

## 17. 可观测性

- `run_events` 是产品事件和状态重放的来源。
- 普通日志使用结构化键值字段。
- 每个 Run 生成稳定的 `run_id`，每次 HTTP 请求生成 `request_id`。
- 首版不接入 LangSmith。
- `TraceExporter` 设计为可选 Port，后续可输出 OpenTelemetry Span 到 LangSmith、Langfuse 或其他平台。
- Trace 默认只包含结构、耗时、Token 和错误码，不包含业务正文。

## 18. 未来扩展

### 18.1 LangChain / LangGraph

- 新增 `LangGraphEngine` 实现 `AgentEngine`。
- FastAPI、Session、Run、Message、ToolCall 和事件协议不改变。
- LangGraph Checkpoint 使用独立适配表，不写入通用领域表。
- LangChain Tool 通过 `ToolProvider` 包装后注册。

### 18.2 MCP

- 新增 `McpToolProvider`，把 MCP Tools 映射为 `ToolDefinition`。
- MCP Server 生命周期、认证和审批属于 Provider，不进入 `AgentEngine`。
- 首版工具协议已经支持远端工具，因此不需要改变 Run 状态机。

### 18.3 Workspace

- Workspace 作为独立领域加入，不写入 Session 表。
- Agent 通过显式的 Context Provider 或工具获取 Workspace 信息。
- 首版不预留 Workspace JSON 字段，避免形成第二套未定义模型。

## 19. 测试策略

### 19.1 单元测试

- Run 状态机合法与非法转换。
- ContextAssembler 的单元边界和工具调用配对。
- Pydantic 工具 Schema 转换和非法工具名。
- 模型流式 tool call 增量聚合。
- 取消、超时和步数限制。
- 错误码与 HTTP 映射。

### 19.2 持久化集成测试

- 临时 SQLite 上执行 Alembic 到最新版本。
- 一个 assistant 轮次的多个工具调用全部保存。
- 任何终态 Run 都不存在未闭合的 assistant/tool 组。
- 远端工具结果原子提交。
- 重复结果幂等，冲突结果返回 409。
- 非法远端结果返回 422，且 ToolCall 保持 pending。
- 远端工具过期生成 tool 错误结果并推动 Run 继续。
- 进程重启后 `waiting_for_tool` 可以继续。
- 进程重启后 `running` 被标记为 `PROCESS_INTERRUPTED`。
- 进程重启时遗留 ToolCall 被补齐错误结果。
- 同一 Session 不能并发创建两个活动 Run。
- 显式指定不存在的 Prompt 版本时创建 Run 失败。

### 19.3 HTTP 与 SSE 测试

- Session/Run 创建、查询和消息读取。
- SSE 文本增量与终态事件。
- `Last-Event-ID` 重放持久事件。
- 鉴权失败、404、409、422 和模型错误映射。
- 错误响应和事件中不出现测试密钥、Prompt 或工具输出正文。

### 19.4 模型适配测试

- 使用假 OpenAI-compatible 服务验证流式文本、reasoning 和多工具调用。
- 验证已输出增量后不重试。
- 验证工具参数分片最终能正确聚合。

## 20. 首版验收标准

- 可以创建 Session，并在其中连续执行多个 Run。
- 模型文本可以通过 SSE 实时查看。
- 一轮模型响应包含多个工具调用时，全部工具都被处理。
- 本地工具可以执行并产生持久化结果。
- 远端工具可以挂起 Run，服务重启后仍能接收结果并继续。
- 远端工具超时、取消和进程中断不会留下无法继续装配的悬空 ToolCall。
- 远端结果必须回显匹配的 `input_digest`。
- 同一 Session 的 Run 严格串行。
- Run 可以取消，终态和事件一致。
- 模型或工具超时返回稳定错误码。
- SQLite 中不存在整段 Session messages JSON 作为唯一事实源。
- `ruff check`、`ruff format --check`、`mypy src` 和 `pytest` 全部通过。
- 不引入 LangChain、LangGraph、PydanticAI、MCP SDK 或 LangSmith 运行时依赖。

## 21. 交付规模

这是一个项目级变更，不是单文件功能：

- 需要新增领域模型、数据库迁移、Repository、AgentEngine、模型适配、工具系统、Run Worker、FastAPI 路由和 SSE。
- 需要建立一套不依赖真实模型的集成测试。
- 建议按“持久化与领域模型 → 模型与本地工具 → HTTP/SSE 与远端工具 → 恢复、安全与验收”四个阶段实施。

## 22. 已由设计确定的实现选择

- 首版主键使用 UUID 字符串，RunEvent 使用 SQLite 自增整数作为持久事件游标。
- 首版支持远端工具协议，但只提供测试工具，不内置浏览器、设备或 Workspace 工具。
- 首版模型密钥和 API Token 来自环境变量，不写入 SQLite。
- 首版同一 Session 只允许一个活动 Run。
- 首版不做 LLM 摘要压缩，只做完整消息单元边界内的上下文裁剪。
- 首版使用单进程 asyncio Worker，不引入独立任务队列。
- 首版不将模型流式增量写入数据库。
- 所有终止 Run 必须闭合未完成的 ToolCall。
- 远端工具完成后 Run 通过 `waiting_for_tool -> queued -> running` 恢复。
- 首版 Prompt 通过显式 `name@version` 选择，不猜测最新版本。
- 首版使用显式配置的 `tiktoken` encoding 估算预算，不静默退回字符近似。
