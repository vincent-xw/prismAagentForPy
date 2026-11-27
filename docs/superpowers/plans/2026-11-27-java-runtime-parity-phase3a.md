# Java 双语言 Runtime —— Phase 3a（Run / SSE / 工具循环）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 Java 后端真正跑起来：创建 Run → 后台 Worker 调模型 → 持久化 assistant/tool 消息 → 通过 SSE 实时推送可重放的事件 → 支持取消、超时与进程恢复；并用确定性模型桩验证整条链路。

**Architecture:** Spring MVC（同步 Controller + `SseEmitter`）+ 虚拟线程 Worker 轮询 claim；MySQL 短事务（`TransactionTemplate`），模型调用与 SSE 绝不包在事务里；事件用 **per-run 单调 `seq`**（在 `runs` 行锁内分配）作为 SSE `id`，保证"序序 = 提交序"；Provider 用 JDK `HttpClient` 手工解析 OpenAI-compatible SSE，聚合文本/reasoning/多工具增量。

**Tech Stack:** JDK 21（虚拟线程）、Spring MVC、MyBatis-Plus、MySQL 8.4 + Flyway、Jackson、`java.net.http.HttpClient`、JUnit 5 + MockMvc + 服务器上的开发 MySQL。

**Spec:** `docs/superpowers/specs/2026-11-27-java-runtime-v14-parity-design.md`（§8、§10.1–10.9、§11、§13）

## Global Constraints

- 对外契约与 Python V1.4 逐字对齐：字段 snake_case、时间 ISO-8601 `Z`、错误信封、事件名与 payload。
- 事件 `id` 必须是**纯数字**且随 Run 单调递增；`message.delta`/`reasoning.delta` 不得带 `id`；终态事件后服务端关闭流。
- 每个事务只做一件事：claim、持久化模型回合、工具结果、终态。**禁止**把模型调用、SSE 写入、等待放进事务。
- Worker 并发默认 2（`prism.worker.concurrency`），每个 Worker 一个虚拟线程；轮询间隔 100ms。
- 状态迁移必须走 `RunStateMachine` + 条件更新 CAS；终态不可逆；成功迁移要带 `cancel_requested_at IS NULL`。
- 单会话只允许一个活动 Run：`runs.active_session_id` 生成列 + 唯一索引，冲突映射 `RUN_CONFLICT`/409。
- 工具调用必须闭合：任何终态 Run 不得留下 `pending/running/awaiting_approval` 的 ToolCall。
- 错误码只从 `ErrorCode` 枚举取，不新增未在 Python 定义的码。
- 测试：`cd backend-java && ./mvnw verify` 全绿；集成测试连 `127.0.0.1:13306/prism_test`（SSH 隧道）。
- 不实现工作区文件工具、审批、MCP、Skills、压缩/轨迹/模型档案（分别属于 Phase 4/3b/5/6）。

## Review Focus

1. **事件游标重复/乱序**：并发事务同时追加事件，若用自增主键当游标会丢事件 —— 在 Task 3 的并发用例里钉住。
2. **取消与完成竞态**：取消请求已提交时仍写入 `succeeded` —— 在 Task 8 的竞态用例里钉住。
3. **终态不关流**：收到终态事件后 `SseEmitter` 未 complete，客户端永久挂起 —— 在 Task 4 的 SSE 用例里钉住。
4. **多工具增量聚合错位**：`tool_calls[].index` 处理错导致参数拼到错误的调用上 —— 在 Task 5 的 Provider 用例里钉住。
5. **事务跨模型调用**：把 `provider.stream` 包进事务，连接池在并发下耗尽 —— 在 Task 6 的并发 Run 用例里钉住。

---

## 文件结构（Phase 3a 结束时新增）

```text
backend-java/src/main/java/com/prism/agent/
├── api/controller/RunController.java
├── api/dto/{RunCreateRequest,RunView,ToolCallView,ToolResultRequest,ToolResultErrorPayload}.java
├── application/service/RunService.java
├── application/event/{RunEventPublisher,RunStreamHub,RunSubscriber}.java
├── application/worker/{RunWorker,RunCancellationRegistry,RunClaimer,ExpirySweeper}.java
├── core/domain/{Run,Message,ToolCall,RunEvent,RunStatus,ToolCallStatus,MessageRole,MessageKind,EventType}.java
├── core/state/RunStateMachine.java
├── core/engine/{AgentEngine,SimpleAgentEngine,EngineContext,EngineOutcome}.java
├── providers/{ModelProvider,ModelRequest,ModelResponse,ModelChunk,TokenUsage,ToolCallDraft,OpenAiCompatibleModelProvider}.java
├── tools/{ToolRegistry,ToolDefinition,ToolExecutionResult}.java
├── persistence/entity/{RunEntity,MessageEntity,ToolCallEntity,RunEventEntity}.java
├── persistence/mapper/{RunMapper,MessageMapper,ToolCallMapper,RunEventMapper}.java
├── persistence/repository/{RunRepository,MessageRepository,ToolCallRepository,EventRepository}.java
└── config/{PrismProperties,WorkerConfiguration}.java（后者提供虚拟线程执行器）

backend-java/src/main/resources/db/migration/V2__runs_messages_events.sql
backend-java/src/test/java/com/prism/agent/...（见各任务）
tests/mock-model/server.py（零依赖模型桩，供端到端 SSE 验证）
tests/contract/test_runs.py（黑盒 Run 契约）
```

职责边界：Controller 只做绑定；Service 管短事务；Engine 只管"下一步做什么"；Provider 只管协议；Hub 只管广播；Repository 只管 SQL。

---

### Task 1: 数据模型与状态机

**Files:**
- Create: `backend-java/src/main/resources/db/migration/V2__runs_messages_events.sql`
- Create: `backend-java/src/main/java/com/prism/agent/core/domain/*.java`（Run/Message/ToolCall/RunEvent/枚举）
- Create: `backend-java/src/main/java/com/prism/agent/core/state/RunStateMachine.java`
- Create: `backend-java/src/main/java/com/prism/agent/persistence/entity/*.java`、`mapper/*.java`、`repository/*.java`
- Test: `backend-java/src/test/java/com/prism/agent/core/RunStateMachineTest.java`
- Test: `backend-java/src/test/java/com/prism/agent/persistence/RunRepositoryTest.java`

**Interfaces:**
- Consumes: `MySqlTestBase`、`SessionRepository`（Phase 1）
- Produces:
  - `enum RunStatus { QUEUED, RUNNING, WAITING_FOR_TOOL, WAITING_FOR_APPROVAL, SUCCEEDED, FAILED, CANCELLED }`
  - `enum ToolCallStatus { PENDING, RUNNING, AWAITING_APPROVAL, SUCCEEDED, FAILED, EXPIRED, CANCELLED }`
  - `enum MessageRole { USER, ASSISTANT, TOOL }`、`enum MessageKind { TEXT, SKILL_CONTEXT, CHECKPOINT }`
  - `record Run(String id, String sessionId, String workspaceId, RunStatus status, String inputText, String promptName, String promptVersion, String systemPrompt, String model, Integer modelContextWindow, Integer modelMaxOutputTokens, String skillName, int stepCount, String outputText, String errorCode, String errorMessage, Instant cancelRequestedAt, Instant createdAt, Instant startedAt, Instant finishedAt)`
  - `record Message(Long id, String sessionId, String runId, MessageRole role, MessageKind kind, Object content, String reasoning, String toolCallId, Instant createdAt)`
  - `record ToolCall(String id, String runId, long assistantMessageId, String toolName, String executionMode, ToolCallStatus status, Object input, Object output, String inputDigest, String errorCode, String errorMessage, Instant expiresAt)`
  - `record RunEvent(Long id, String runId, int seq, EventType type, Object payload, Instant createdAt)`
  - `RunStateMachine.ensure(RunStatus from, RunStatus to) throws ApiException(INVALID_RUN_TRANSITION, 409)`
  - `Run.newQueued(String sessionId, String inputText, String model, String systemPrompt, Instant now)`（prompt 固定 `default@1`，其余可空字段为 null）
  - `RunRepository { Run insert(Run); Run requireById(String); Optional<Run> claimNext(); Run transition(String id, RunStatus to, TransitionOptions options); List<Run> listByStatus(RunStatus); Run markCancelRequested(String id); void updateStepCount(String id, int stepCount); }`

- [ ] **Step 1: 写失败测试**

```java
class RunStateMachineTest {
    @Test
    void queuedCanBecomeRunningOrCancelled() {
        RunStateMachine.ensure(RunStatus.QUEUED, RunStatus.RUNNING);
        RunStateMachine.ensure(RunStatus.QUEUED, RunStatus.CANCELLED);
    }

    @Test
    void terminalStateIsIrreversible() {
        ApiException error = assertThrows(ApiException.class,
                () -> RunStateMachine.ensure(RunStatus.SUCCEEDED, RunStatus.RUNNING));
        assertThat(error.code()).isEqualTo(ErrorCode.INVALID_RUN_TRANSITION);
        assertThat(error.httpStatus()).isEqualTo(409);
    }
}
```

```java
class RunRepositoryTest extends MySqlTestBase {
    @Autowired RunRepository runs;
    @Autowired SessionRepository sessions;
    @Autowired JdbcTemplate jdbc;

    @BeforeEach
    void clean() {
        jdbc.update("delete from run_events");
        jdbc.update("delete from tool_calls");
        jdbc.update("delete from messages");
        jdbc.update("delete from runs");
        jdbc.update("delete from sessions");
    }

    @Test
    void secondActiveRunInSameSessionIsRejected() {
        String sessionId = sessions.insert(Session.newSession("s", Instant.now())).id();
        runs.insert(Run.newQueued(sessionId, "hi", "mock-model", "sys", Instant.now()));
        assertThatThrownBy(() -> runs.insert(Run.newQueued(sessionId, "again", "mock-model", "sys", Instant.now())))
                .isInstanceOf(org.springframework.dao.DuplicateKeyException.class);
    }

    @Test
    void claimNextMarksRunningOnce() {
        String sessionId = sessions.insert(Session.newSession("s", Instant.now())).id();
        Run created = runs.insert(Run.newQueued(sessionId, "hi", "mock-model", "sys", Instant.now()));
        Optional<Run> claimed = runs.claimNext();
        assertThat(claimed).isPresent();
        assertThat(claimed.get().status()).isEqualTo(RunStatus.RUNNING);
        assertThat(claimed.get().startedAt()).isNotNull();
        assertThat(runs.claimNext()).isEmpty();
    }
}
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend-java && ./mvnw -q -Dtest=RunStateMachineTest,RunRepositoryTest test`
Expected: FAIL —— 编译失败（domain/enum/repository 不存在）

- [ ] **Step 3: 实现迁移与仓储**

`V2__runs_messages_events.sql` 关键列（其余按 spec §11.1）：

```sql
CREATE TABLE runs (
  id CHAR(36) NOT NULL PRIMARY KEY,
  session_id CHAR(36) NOT NULL,
  workspace_id CHAR(36) NULL,
  status VARCHAR(32) NOT NULL,
  model_profile_id CHAR(36) NULL,
  model_context_window INT NULL,
  model_max_output_tokens INT NULL,
  skill_name VARCHAR(64) NULL,
  input_text MEDIUMTEXT NOT NULL,
  prompt_name VARCHAR(128) NOT NULL,
  prompt_version VARCHAR(64) NOT NULL,
  system_prompt MEDIUMTEXT NOT NULL,
  model VARCHAR(128) NOT NULL,
  step_count INT NOT NULL DEFAULT 0,
  output_text MEDIUMTEXT NULL,
  error_code VARCHAR(64) NULL,
  error_message TEXT NULL,
  cancel_requested_at DATETIME(6) NULL,
  last_event_seq INT NOT NULL DEFAULT 0,
  created_at DATETIME(6) NOT NULL,
  started_at DATETIME(6) NULL,
  finished_at DATETIME(6) NULL,
  active_session_id VARCHAR(36) GENERATED ALWAYS AS (
    CASE WHEN status IN ('queued','running','waiting_for_tool','waiting_for_approval')
         THEN session_id ELSE NULL END) STORED,
  UNIQUE KEY ux_runs_one_active (active_session_id),
  KEY ix_runs_session_created (session_id, created_at),
  KEY ix_runs_status (status),
  CONSTRAINT fk_runs_session FOREIGN KEY (session_id) REFERENCES sessions (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE messages (
  id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  session_id CHAR(36) NOT NULL,
  run_id CHAR(36) NOT NULL,
  role VARCHAR(16) NOT NULL,
  kind VARCHAR(32) NOT NULL DEFAULT 'text',
  content JSON NOT NULL,
  reasoning TEXT NULL,
  tool_call_id VARCHAR(128) NULL,
  created_at DATETIME(6) NOT NULL,
  KEY ix_messages_session (session_id, id),
  UNIQUE KEY ux_messages_run_tool_call (run_id, tool_call_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE tool_calls (
  id VARCHAR(128) NOT NULL PRIMARY KEY,
  run_id CHAR(36) NOT NULL,
  assistant_message_id BIGINT NOT NULL,
  tool_name VARCHAR(128) NOT NULL,
  execution_mode VARCHAR(16) NOT NULL,
  status VARCHAR(16) NOT NULL,
  input JSON NOT NULL,
  output JSON NULL,
  input_digest VARCHAR(80) NOT NULL,
  error_code VARCHAR(64) NULL,
  error_message TEXT NULL,
  expires_at DATETIME(6) NULL,
  created_at DATETIME(6) NOT NULL,
  finished_at DATETIME(6) NULL,
  KEY ix_tool_calls_run_status (run_id, status),
  CONSTRAINT fk_tool_calls_run FOREIGN KEY (run_id) REFERENCES runs (id) ON DELETE CASCADE,
  CONSTRAINT fk_tool_calls_message FOREIGN KEY (assistant_message_id) REFERENCES messages (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE run_events (
  id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  run_id CHAR(36) NOT NULL,
  seq INT NOT NULL,
  event_type VARCHAR(64) NOT NULL,
  payload JSON NOT NULL,
  created_at DATETIME(6) NOT NULL,
  UNIQUE KEY ux_run_events_run_seq (run_id, seq),
  CONSTRAINT fk_run_events_run FOREIGN KEY (run_id) REFERENCES runs (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
```

迁移里用 `CREATE TABLE IF NOT EXISTS`，因为 Phase 1 的 `V1` 已在测试库执行过一次（Flyway 会跳过已应用的版本，但测试库可能被手工清理）。

`RunRepository.claimNext()` 用：

```sql
SELECT id FROM runs WHERE status='queued' ORDER BY created_at, id LIMIT 1 FOR UPDATE SKIP LOCKED
```
再 `UPDATE ... SET status='running', started_at=? WHERE id=? AND status='queued'`；行数 0 返回空。
`transition` 语义与 Python 一致：校验状态机、终态写 `finished_at`、`SUCCEEDED` 额外要求 `cancel_requested_at IS NULL`、CAS 失败重试 3 次后 409。

- [ ] **Step 4: 运行确认通过**

Run: `cd backend-java && ./mvnw -q -Dtest=RunStateMachineTest,RunRepositoryTest test`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend-java/src/main/resources/db/migration/V2__runs_messages_events.sql backend-java/src/main/java backend-java/src/test/java
git commit -m "feat(java): Run/Message/ToolCall/RunEvent 持久化与状态机"
```

---

### Task 2: Run 创建、查询与取消 API

**Files:**
- Create: `backend-java/src/main/java/com/prism/agent/api/controller/RunController.java`
- Create: `backend-java/src/main/java/com/prism/agent/api/dto/{RunCreateRequest,RunView,RunListResponse? 不需要}.java`
- Create: `backend-java/src/main/java/com/prism/agent/application/service/RunService.java`
- Create: `backend-java/src/main/java/com/prism/agent/application/worker/RunCancellationRegistry.java`
- Test: `backend-java/src/test/java/com/prism/agent/api/RunApiTest.java`

**Interfaces:**
- Consumes: Task 1 的仓储、`SessionRepository`
- Produces:
  - `record RunCreateRequest(@NotBlank String input, String promptRef, Map<String,Object> metadata, String skillName)`
  - `record RunView(String id, String sessionId, String workspaceId, RunStatus status, String input, String promptRef, String model, int stepCount, String output, String errorCode, String errorMessage, Instant cancelRequestedAt, Instant createdAt, Instant startedAt, Instant finishedAt)` + `static RunView from(Run)`
  - `RunService { Run create(String sessionId, RunCreateRequest request); Run get(String runId); Run cancel(String runId); }`
  - `RunCancellationRegistry { void register(String runId); void signal(String runId); boolean isSignalled(String runId); void unregister(String runId); }`（`ConcurrentHashMap<String, AtomicBoolean>`）

- [ ] **Step 1: 写失败测试**

```java
@SpringBootTest(webEnvironment = RANDOM_PORT,
        properties = {"prism.environment=test", "prism.api-token=test-token"})
class RunApiTest extends MySqlTestBase {

    @LocalServerPort int port;
    @Autowired TestRestTemplate rest;
    @Autowired ObjectMapper mapper;

    private HttpHeaders authJson() { /* Bearer + application/json */ }
    private String createSession() { /* POST /api/v1/sessions → id */ }

    @Test
    void createRunReturns202Queued() {
        String sessionId = createSession();
        ResponseEntity<JsonNode> response = post("/api/v1/sessions/" + sessionId + "/runs",
                Map.of("input", "你好"));
        assertThat(response.getStatusCode().value()).isEqualTo(202);
        assertThat(response.getBody().get("status").asText()).isEqualTo("queued");
        assertThat(response.getBody().get("prompt_ref").asText()).isEqualTo("default@1");
        assertThat(response.getBody().get("step_count").asInt()).isZero();
        assertThat(response.getBody().has("cancel_requested_at")).isTrue();
        assertThat(response.getBody().get("cancel_requested_at").isNull()).isTrue();
    }

    @Test
    void blankInputIsRejected() {
        String sessionId = createSession();
        assertThat(post("/api/v1/sessions/" + sessionId + "/runs", Map.of("input", "   "))
                .getStatusCode().value()).isEqualTo(422);
    }

    @Test
    void secondActiveRunConflicts() {
        String sessionId = createSession();
        post("/api/v1/sessions/" + sessionId + "/runs", Map.of("input", "a"));
        ResponseEntity<JsonNode> second = post("/api/v1/sessions/" + sessionId + "/runs", Map.of("input", "b"));
        assertThat(second.getStatusCode().value()).isEqualTo(409);
        assertThat(second.getBody().at("/error/code").asText()).isEqualTo("RUN_CONFLICT");
    }

    @Test
    void getMissingRunIs404() {
        assertThat(get("/api/v1/runs/nope").getStatusCode().value()).isEqualTo(404);
    }

    @Test
    void cancelQueuedRunTerminatesImmediately() {
        String sessionId = createSession();
        String runId = post("/api/v1/sessions/" + sessionId + "/runs", Map.of("input", "a"))
                .getBody().get("id").asText();
        ResponseEntity<JsonNode> cancelled = post("/api/v1/runs/" + runId + "/cancel", null);
        assertThat(cancelled.getStatusCode().value()).isEqualTo(200);
        assertThat(cancelled.getBody().get("status").asText()).isEqualTo("cancelled");
        assertThat(cancelled.getBody().get("finished_at").isNull()).isFalse();
    }
}
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend-java && ./mvnw -q -Dtest=RunApiTest test`
Expected: FAIL —— 404（路由不存在）

- [ ] **Step 3: 实现**

- `create`：解析 `promptRef`（默认 `default@1`，仅支持该值；其他 → 422 `PROMPT_NOT_FOUND`），在**一个事务**里：`sessions.touch`、插 Run（`queued`）、插 user Message。活动 Run 冲突由唯一索引抛出 → 映射 409 `RUN_CONFLICT`。**本任务不写事件**（`run.queued`/`run.cancelled` 由 Task 3 在此基础上补进同一事务并加断言），避免与事件仓储形成循环依赖。
- `get`：查不到 → 404 `RUN_NOT_FOUND`。
- `cancel`：写 `cancel_requested_at`（幂等）；若当前是 `queued`/`waiting_for_tool`/`waiting_for_approval` → 闭合工具 + 转 `cancelled` + 写 `run.cancelled`；`running` 只写请求并 signal，交给 Worker 收尾；终态直接返回原 Run。
- Controller：`POST /sessions/{id}/runs` → 202；`GET /runs/{id}`；`POST /runs/{id}/cancel`。前缀同为 `${prism.api-prefix}`。

- [ ] **Step 4: 运行确认通过**

Run: `cd backend-java && ./mvnw -q -Dtest=RunApiTest test`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend-java/src/main/java backend-java/src/test/java
git commit -m "feat(java): Run 创建/查询/取消 API"
```

---

### Task 3: 事件写入与 per-run 序号

**Files:**
- Create: `backend-java/src/main/java/com/prism/agent/persistence/repository/EventRepository.java`
- Create: `backend-java/src/main/java/com/prism/agent/application/event/RunEventPublisher.java`
- Modify: `backend-java/src/main/java/com/prism/agent/application/service/RunService.java`（创建/取消时在同一事务写事件）
- Test: `backend-java/src/test/java/com/prism/agent/persistence/EventSeqTest.java`
- Test: `backend-java/src/test/java/com/prism/agent/api/RunEventWiringTest.java`（`POST /runs` 后事件表里有且只有一条 `run.queued`；取消后有 `run.cancelled`）

**Interfaces:**
- Consumes: Task 1 的 `runs.last_event_seq`、`run_events`
- Produces:
  - `RunEvent append(String runId, EventType type, Map<String,Object> payload)`：在**调用方事务内**先 `UPDATE runs SET last_event_seq = last_event_seq + 1 WHERE id=?`（行锁），再查回值插入事件，返回带 `seq`
  - `List<RunEvent> listAfter(String runId, Integer afterSeq)`：`seq > ? ORDER BY seq`
  - `int lastSeq(String runId)`
  - `RunEventPublisher.publish(RunEvent)`：事务提交后调用，交给 Hub（Task 4）

- [ ] **Step 1: 写失败测试**

```java
class EventSeqTest extends MySqlTestBase {
    @Autowired RunRepository runs; @Autowired EventRepository events;
    @Autowired SessionRepository sessions; @Autowired TransactionTemplate tx;
    @Autowired JdbcTemplate jdbc;

    @Test
    void concurrentAppendsGetUniqueMonotonicSeq() throws Exception {
        // 建 1 个 Run，起 8 个线程各追加 25 条事件
        // 期望：共 200 条，seq 恰好是 1..200，无重复
        List<Integer> seqs = ...;
        assertThat(seqs).hasSize(200).doesNotHaveDuplicates();
        assertThat(seqs).isSorted();
    }

    @Test
    void listAfterReturnsOnlyNewerEvents() {
        // 追加 3 条，listAfter(runId, seq1) 返回后 2 条
    }
}
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend-java && ./mvnw -q -Dtest=EventSeqTest test`
Expected: FAIL —— `EventRepository` 不存在

- [ ] **Step 3: 实现**

- 序号分配必须在**同一事务**、且在写 `run_events` 之前完成；行锁持有到提交，从而保证"seq 顺序 = 提交顺序"。
- 并发测试用 `TransactionTemplate` + `CountDownLatch` 起线程，每个线程一个事务追加。
- 事件 payload 存 JSON（Jackson `ObjectMapper` 写入 `String` 列或 `JSON` 列；用 `JSON` 列 + `CAST(? AS JSON)` 参数）。
- `EventType` 枚举只需 Phase 3a 用到的：`RUN_QUEUED, RUN_STARTED, ASSISTANT_COMPLETED, TOOL_REQUESTED, TOOL_COMPLETED, TOOL_FAILED, TOOL_EXPIRED, RUN_WAITING_FOR_TOOL, RUN_WAITING_FOR_APPROVAL, RUN_REQUEUED, RUN_SUCCEEDED, RUN_FAILED, RUN_CANCELLED, MESSAGE_DELTA, REASONING_DELTA, STEP_STARTED, STEP_COMPLETED, STEP_FAILED`；其余（压缩/裁剪）Phase 3b 补。

- [ ] **Step 4: 运行确认通过**

Run: `cd backend-java && ./mvnw -q -Dtest=EventSeqTest test`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git commit -am "feat(java): 事件 per-run 序号与并发安全写入"
```

---

### Task 4: SSE 事件流

**Files:**
- Create: `backend-java/src/main/java/com/prism/agent/application/event/{RunStreamHub,RunSubscriber}.java`
- Create: `backend-java/src/main/java/com/prism/agent/api/controller/RunEventController.java`
- Create: `backend-java/src/main/java/com/prism/agent/config/SseConfiguration.java`（心跳线程、异步超时）
- Test: `backend-java/src/test/java/com/prism/agent/api/SseStreamTest.java`

**Interfaces:**
- Consumes: Task 3 的 `EventRepository`、`RunEventPublisher`
- Produces:
  - `RunStreamHub { void publish(RunEvent event); SseEmitter subscribe(String runId, Integer afterSeq); }`
  - `GET ${api-prefix}/runs/{runId}/events`：`Last-Event-ID` 头、`once`（仅 `prism.environment=test`）
  - SSE 帧：`event: <type>`、`id: <seq>`（仅持久事件）、`data: {"type","run_id",...payload}`
- 行为：先注册订阅者 → 从库重放 `seq > cursor` → 转入实时；实时事件 `seq <= 已发送` 丢弃；收到终态事件后 `complete()`；终态 Run 的新连接只重放并立即结束；每 15s 写注释心跳 `: ping`。

- [ ] **Step 1: 写失败测试**

```java
@SpringBootTest(webEnvironment = RANDOM_PORT, properties = {"prism.environment=test", "prism.api-token=test-token"})
class SseStreamTest extends MySqlTestBase {

    @Test
    void terminalRunReplaysAndCloses() {
        // 造一个 failed Run + 3 条事件（run.queued/run.started/run.failed）
        // GET /api/v1/runs/{id}/events，读完整响应
        // 断言：3 帧，event 名与 id 正确，最后一条 run.failed，连接结束
    }

    @Test
    void incrementalEventsHaveNoId() {
        // 直接 publish 一条 message.delta（不落库），订阅后应收到 id 为空
    }

    @Test
    void invalidLastEventIdIs400() {
        // Last-Event-ID: abc → 400 INVALID_REQUEST
    }

    @Test
    void onceIsRejectedOutsideTestEnvironment() { /* 用 development profile 断言 400 */ }
}
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend-java && ./mvnw -q -Dtest=SseStreamTest test`
Expected: FAIL —— 404 / 未实现

- [ ] **Step 3: 实现**

- `SseEmitter` 超时设 0（不超时）；`spring.mvc.async.request-timeout=-1`。
- 订阅者队列用 `ArrayBlockingQueue<Object>(1024)`；满时 `completeWithError` 并注销（不阻塞发布方）。
- JSON 自行序列化（`ObjectMapper.writeValueAsString`），`data` 必须是 `{type,run_id,...payload}` 平铺。
- 心跳用共享 `ScheduledExecutorService`（1 线程），每 15s 对活跃 emitter 写 `:\n\n`。
- 终态集合 `{run.succeeded, run.failed, run.cancelled}`。

- [ ] **Step 4: 运行确认通过**

Run: `cd backend-java && ./mvnw -q -Dtest=SseStreamTest test`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git commit -am "feat(java): Run SSE 重放、实时订阅与终态关闭"
```

---

### Task 5: 模型 Provider（OpenAI-compatible 流式）

**Files:**
- Create: `backend-java/src/main/java/com/prism/agent/providers/*.java`
- Create: `backend-java/src/main/java/com/prism/agent/config/ModelProperties.java`（或在 `PrismProperties` 里加 `model` 子对象）
- Test: `backend-java/src/test/java/com/prism/agent/providers/OpenAiCompatibleProviderTest.java`

**Interfaces:**
- Consumes: `ObjectMapper`、`HttpClient`
- Produces:
  - `record ModelRequest(String systemPrompt, List<Message> messages, List<ToolCall> toolCalls, List<Map<String,Object>> tools, Integer maxOutputTokens)`
  - `record ModelChunk(String text, String reasoning)`
  - `record ModelResponse(String text, String reasoning, List<ToolCallDraft> toolCalls, TokenUsage usage, String finishReason)`
  - `record ToolCallDraft(String callId, String toolName, Object input)`
  - `interface ModelProvider { ModelResponse stream(ModelRequest request, Consumer<ModelChunk> onDelta) throws InterruptedException; }`
  - `OpenAiCompatibleModelProvider(ModelProperties props, ObjectMapper mapper, HttpClient client)`

- [ ] **Step 1: 写失败测试（用 JDK `HttpServer` 起桩）**

```java
class OpenAiCompatibleProviderTest {
    // 桩依次返回：
    // 1) data: {"choices":[{"delta":{"content":"你"}}]}
    // 2) data: {"choices":[{"delta":{"content":"好"},"finish_reason":null}]}
    // 3) data: {"choices":[{"delta":{},"finish_reason":"stop"}],"usage":{...}}
    @Test void aggregatesTextDeltasAndUsage() { ... }

    @Test void aggregatesReasoningContent() { ... }

    @Test void aggregatesTwoToolCallsByIndex() {
        // index 0: id=call_1 name=file_read arguments={"path":"a"}
        // index 1: id=call_2 name=file_list arguments={}
        // 断言 toolCalls 数量 2 且参数各自正确
    }

    @Test void missingToolCallIndexIsProtocolError() { ... }   // MODEL_PROTOCOL_INVALID / 502
    @Test void rateLimitMapsToModelRateLimited() { ... }        // 429 → MODEL_RATE_LIMITED
    @Test void invalidJsonAfterFirstDeltaIsNotRetried() { ... }
}
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend-java && ./mvnw -q -Dtest=OpenAiCompatibleProviderTest test`
Expected: FAIL —— 类不存在

- [ ] **Step 3: 实现**

- 请求体：`model/messages/stream=true/stream_options.include_usage`；有工具才带 `tools`；`max_tokens`。
- 消息重建：system 置首；assistant 的 `tool_calls[].function.arguments` 用稳定 JSON（键排序）；tool 消息缺 `tool_call_id` → 502。
- SSE 解析按行读 `data:`，`[DONE]` 结束；未知字段忽略。
- 增量：`content`→text；`reasoning_content`→reasoning；`tool_calls` 按 `index` 累加；参数最终 `ObjectMapper.readTree`，非法 → 502。
- 重试：仅在**首个文本/reasoning 增量之前**，最多 2 次，退避 `min(0.2*2^n, 1s)`；超时/连接/429/5xx 可重试。
- 错误映射：超时→`MODEL_TIMEOUT`/504；400 且消息含 `context`→`CONTEXT_OVERFLOW`/422；429→`MODEL_RATE_LIMITED`；其余→`MODEL_UPSTREAM_ERROR`/502；缺配置→`MODEL_NOT_CONFIGURED`。
- 配置：`prism.model.base-url/api-key/name/context-window/max-output-tokens/timeout-seconds`；`api-key` 走环境变量 `PRISM_MODEL_API_KEY`。

- [ ] **Step 4: 运行确认通过**

Run: `cd backend-java && ./mvnw -q -Dtest=OpenAiCompatibleProviderTest test`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git commit -am "feat(java): OpenAI-compatible 流式 Provider 与增量聚合"
```

---

### Task 6: Worker 与最小 Agent 循环（单步完成 + 远端工具）

**Files:**
- Create: `backend-java/src/main/java/com/prism/agent/core/engine/*.java`
- Create: `backend-java/src/main/java/com/prism/agent/application/worker/{RunWorker,RunClaimer}.java`
- Create: `backend-java/src/main/java/com/prism/agent/config/WorkerConfiguration.java`
- Create: `backend-java/src/main/java/com/prism/agent/tools/{ToolRegistry,ToolDefinition,ToolExecutionResult}.java`
- Test: `backend-java/src/test/java/com/prism/agent/application/EngineLoopTest.java`

**Interfaces:**
- Consumes: Tasks 1–5（仓储、事件、Provider、Hub）
- Produces:
  - `record EngineContext(String runId, AtomicBoolean cancel)`
  - `record EngineOutcome(Kind kind, ErrorCode errorCode, String message)`，`Kind = COMPLETED | WAITING_FOR_TOOLS | FAILED | CANCELLED`
  - `interface AgentEngine { EngineOutcome execute(EngineContext ctx); EngineOutcome resume(EngineContext ctx); EngineOutcome cancel(String runId); }`
  - `SimpleAgentEngine(TransactionTemplate tx, ModelProvider provider, ToolRegistry tools, EventRepository events, RunEventPublisher publisher, int maxSteps)`
  - `RunWorker.start()`：恢复 → 起 N 个虚拟线程 `while(true) { claim→execute→loop }`；`stop()` 中断并等待
  - `ToolRegistry { void register(ToolDefinition); Optional<ToolDefinition> get(String name); List<ToolDefinition> list(); List<Map<String,Object>> modelSchemas(); }`
  - `record ToolDefinition(String name, String description, ExecutionMode mode, boolean requiresApproval, JsonNode inputSchema)`

- [ ] **Step 1: 写失败测试**

```java
@SpringBootTest(properties = {"prism.environment=test", "prism.api-token=test-token"})
class EngineLoopTest extends MySqlTestBase {
    // 用 JDK HttpServer 做模型桩；构造 SimpleAgentEngine 直接 execute
    @Test void plainTextReplyCompletesRun() {
        // 桩返回 "你好" + finish_reason=stop
        // 期望：Run=succeeded、output=你好、messages 有 user+assistant、事件含 run.started/assistant.completed/step.completed/run.succeeded
    }

    @Test void toolCallWaitsForHostResult() {
        // 桩返回一个 remote 工具调用 call_1
        // 期望：Run=waiting_for_tool、tool_calls 1 条 pending、事件含 tool.requested + run.waiting_for_tool
    }

    @Test void stepLimitFailsRun() {
        // 桩永远返回工具调用；maxSteps=1 → Run=failed, error_code=HARNESS_STEP_LIMIT
    }
}
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend-java && ./mvnw -q -Dtest=EngineLoopTest test`
Expected: FAIL —— 引擎不存在

- [ ] **Step 3: 实现**

- `execute`：校验 Run 是 `running`；写 `run.started`（只写一次）；循环：检查取消 → 装配消息（Phase 3a 只做"全量历史 + system"）→ 写 `step.started` → 调 Provider（delta 通过 Hub 发临时事件）→ 写 `step.completed` → 单事务写 assistant Message + ToolCalls + `assistant.completed` + 每个 `tool.requested` + `step_count+1`；无工具 → `run.succeeded`（带 `message_id`）；有 remote 工具 → `waiting_for_tool` + `run.waiting_for_tool`。
- 事务边界：模型调用前后各一个短事务；Provider 调用绝不在事务内（用一个 `TransactionTemplate` 包住写库段）。
- 并发：`RunWorker` 默认 2 个虚拟线程；`EngineLoopTest.concurrentRunsDoNotExhaustPool` 起 4 个 Run 验证不报连接池超时。
- 本地工具：本阶段只注册"测试/宿主注入"的 remote 工具；`LocalToolExecutor` 留到 Phase 4。`GET /tools` 在本阶段**不注册路由**（保持 404），契约测试与 parity 行在 Phase 4 才覆盖。

- [ ] **Step 4: 运行确认通过**

Run: `cd backend-java && ./mvnw -q -Dtest=EngineLoopTest test`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git commit -am "feat(java): RunWorker 与最小 Agent 循环"
```

---

### Task 7: 远端工具结果回填

**Files:**
- Create: `backend-java/src/main/java/com/prism/agent/api/controller/ToolResultController.java`（或并入 `RunController`）
- Create: `backend-java/src/main/java/com/prism/agent/application/service/ToolResultService.java`
- Create: `backend-java/src/main/java/com/prism/agent/api/dto/{ToolResultRequest,ToolResultErrorPayload,ToolCallView}.java`
- Test: `backend-java/src/test/java/com/prism/agent/api/ToolResultApiTest.java`

**Interfaces:**
- Consumes: Task 6 的 `waiting_for_tool`、Task 3 的事件
- Produces:
  - `POST ${api-prefix}/runs/{runId}/tool-calls/{callId}/result` → `ToolCallView`
  - 校验顺序：`input_digest`（409 `TOOL_INPUT_DIGEST_MISMATCH`）→ 终态幂等 → Run 非 `waiting_for_tool`（409 `RUN_CONFLICT`）→ 过期（409 `TOOL_CALL_EXPIRED`）→ 写 tool Message + `tool.completed`/`tool.failed` → 全部闭合后 `queued` + `run.requeued`
- 并发：`SELECT ... FOR UPDATE` 锁 tool_call 行，保证跨线程串行。

- [ ] **Step 1: 写失败测试**

```java
class ToolResultApiTest extends MySqlTestBase {
    @Test void submitResultClosesCallAndRequeuesRun() { ... }
    @Test void digestMismatchIs409() { ... }
    @Test void repeatSameResultIsIdempotent() { ... }
    @Test void conflictingResultIs409() { ... }
    @Test void resultForWrongRunIs404() { ... }
}
```

- [ ] **Step 2: 运行确认失败** → Run: `./mvnw -q -Dtest=ToolResultApiTest test`，Expected: 404

- [ ] **Step 3: 实现**

- `input_digest` 用 SHA-256（十六进制）对**规范化 JSON**（键排序、无空格）计算，与 Python `canonical_json_digest` 对齐。
- 写 tool Message 的 `content`：成功为 `output`，失败为 `{"error":{"code","message"}}`；`messages(run_id, tool_call_id)` 唯一冲突 → 409 `TOOL_RESULT_CONFLICT`。
- 闭合后若 Run 仍 `waiting_for_tool` 且所有调用终态 → `queued` + `run.requeued`。

- [ ] **Step 4: 运行确认通过** → Expected: PASS
- [ ] **Step 5: 提交** `git commit -am "feat(java): 远端工具结果回填与幂等"`

---

### Task 8: 取消竞态、超时扫描与启动恢复

**Files:**
- Create: `backend-java/src/main/java/com/prism/agent/application/worker/ExpirySweeper.java`
- Modify: `application/worker/RunWorker.java`（启动时恢复）
- Test: `backend-java/src/test/java/com/prism/agent/application/RecoveryAndCancelTest.java`

**Interfaces:**
- Consumes: Tasks 1–7
- Produces:
  - `RunWorker.recoverInterruptedRuns()`：启动时把遗留 `running` → `failed` + `PROCESS_INTERRUPTED`，闭合工具，写 `run.failed`
  - `ExpirySweeper`：每 15s 把 `expires_at <= now` 的 `pending/running` 远端调用置 `expired`（`REMOTE_TOOL_TIMEOUT`），全部闭合后回队
  - 取消竞态：`transition(SUCCEEDED)` 带 `cancel_requested_at IS NULL`，失败则走取消收尾

- [ ] **Step 1: 写失败测试**

```java
class RecoveryAndCancelTest extends MySqlTestBase {
    @Test void staleRunningRunIsFailedOnStartup() { ... }        // 预置 running → recover → failed/PROCESS_INTERRUPTED + 工具闭合
    @Test void cancelDuringModelCallWinsOverCompletion() { ... } // 桩阻塞；取消后 Run=cancelled，不得 succeeded
    @Test void expiredRemoteToolIsMarkedExpiredAndRequeued() { ... }
}
```

- [ ] **Step 2: 运行确认失败**
- [ ] **Step 3: 实现**（取消信号用 `AtomicBoolean`，Engine 在每个安全点检查：循环开始、模型流结束后、持久化前）
- [ ] **Step 4: 运行确认通过**
- [ ] **Step 5: 提交** `git commit -am "feat(java): 取消竞态、超时扫描与启动恢复"`

---

### Task 9: 模型桩服务与端到端 SSE 契约

**Files:**
- Create: `tests/mock-model/server.py`（零依赖，`http.server` + 脚本化 SSE 场景）
- Create: `tests/mock-model/scenarios/*.json`（`text`、`tool_call`、`two_tool_calls`、`error_500`）
- Create: `tests/contract/test_runs.py`
- Modify: `deploy/docker-compose.dev.yml`（可选：`mock-model` 覆盖模型地址）

**Interfaces:**
- Consumes: Task 4/6 的 SSE 与 Run 流程
- Produces: `POST /v1/chat/completions` 按 `X-Mock-Scenario` 头返回确定性 SSE；`GET /_requests` 便于断言

- [ ] **Step 1: 写失败测试**

```python
def test_create_run_and_stream_events(api):
    session = api.post("/api/v1/sessions", json={}).json()
    run = api.post(f"/api/v1/sessions/{session['id']}/runs", json={"input": "hi"})
    assert run.status_code == 202
    events = list(stream_events(api, run.json()["id"]))
    types = [e["type"] for e in events]
    assert types[0] == "run.queued"
    assert types[-1] == "run.succeeded"
    assert all(e["id"].isdigit() for e in events)
```

- [ ] **Step 2: 运行确认失败**（后端尚未接模型桩）
- [ ] **Step 3: 实现桩与契约用例**

桩以 `python3 tests/mock-model/server.py --port 19000` 启动；Java 容器以 `PRISM_MODEL_BASE_URL=http://192.168.31.90:19000/v1` 指向它（与服务器同网段，容器可直连宿主端口）。为不污染常驻栈，验证时起一次性容器：

```bash
ssh srv 'docker run -d --name smoke-java-mock --network prism-agent_default -p 18003:8080 \
  -e PRISM_DB_URL="jdbc:mysql://mysql-java:3306/prism?connectionTimeZone=UTC&forceConnectionTimeZoneToSession=true" \
  -e PRISM_DB_USER=prism -e PRISM_DB_PASSWORD=prism \
  -e PRISM_API_TOKEN=dev-token -e PRISM_ENVIRONMENT=test \
  -e PRISM_MODEL_BASE_URL=http://192.168.31.90:19000/v1 \
  -e PRISM_MODEL_NAME=mock -e PRISM_MODEL_API_KEY=x \
  -e PRISM_MODEL_CONTEXT_WINDOW=65536 -e PRISM_MODEL_MAX_OUTPUT_TOKENS=8192 \
  prism-backend-java:dev'
```

用例末尾删除该容器，避免占用端口与数据。
- [ ] **Step 4: 运行确认通过**
- [ ] **Step 5: 提交** `git commit -am "test(phase3a): 模型桩与 Run/SSE 端到端契约"`

---

## Phase 3b / 4 起的后续计划

| 阶段 | 范围 | 进入条件 |
|---|---|---|
| 3b | 上下文装配/裁剪/压缩、轨迹、模型档案、标题 | 3a 全绿 |
| 4 | Workspace/索引/检索/文件工具/审批 + V1.5 命名工作区 | 3b 绿 |
| 5 | MCP Client | 4 绿 |
| 6 | Skills 与剩余端点 | 5 绿 |
| 7 | 全量 parity、双 UI E2E、隔离与恢复 | 1–6 绿 |

---

## 自检记录

- **Spec 覆盖**：§10.1–10.9（claim/状态机/事件序/SSE/取消/工具/Provider）逐条对应 Task 1–8；§13.2 的模型桩在 Task 9；压缩/轨迹/档案明确留到 3b。
- **步骤扫描**：每个 Step 一个可检查结果；DDL 与 SSE 帧格式属"精确文案"，给全文；引擎与 Provider 只给签名与关键行为。
- **类型一致性**：`Run`/`Message`/`ToolCall`/`RunEvent` 在 Task 1 定义；Task 2/6/7 复用；`EngineOutcome.Kind` 与 Python 的 `EngineOutcome` 对齐（completed/waiting_for_tools/failed/cancelled）。
- **Review Focus**：五条分别落在 Task 3（游标并发）、Task 8（取消竞态）、Task 4（终态关流）、Task 5（多工具 index）、Task 6（并发连接池）。
- **比例**：计划覆盖 9 个任务、约 25 个类；未展开 3b 与 Phase 4+。
