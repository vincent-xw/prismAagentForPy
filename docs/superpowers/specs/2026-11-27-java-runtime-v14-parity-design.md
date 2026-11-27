# Prism Agent 双语言 Runtime 设计（Java 对齐 V1.4）

- 状态：待评审
- 日期：2026-11-27
- 范围：Phase 0（设计 + 实施计划），不落地 Java 代码
- 基线：本地工作区 `feat/v1.4` @ `343a682`，Python 1.4.0
- 关联：`2026-11-22-python-agent-core-design.md`、`2026-11-23-workspace-file-tools-design.md`、`2026-11-24-mcp-client-design.md`、`2026-11-26-skills-design.md`、`2026-11-27-v1.4-compaction-trajectory-model-profile-design.md`

## 0. 已确认的结论

1. **对齐范围是 V1.4 全部对外能力**：42 个 HTTP 端点、27 类 SSE 事件、9 张业务表的持久化语义、4 个状态机，而不是任务书第 8 节列出的子集（该节漏掉了压缩、轨迹、模型档案、标题生成、会话工作区绑定）。
2. **推进方式取"方案 A：契约快照 + 纵向切片"**：Phase 0 冻结契约，之后每个阶段端到端打通一条业务链，Phase 1 结束 UI 即可连上 Java。
3. **部署形态**：Docker Compose，同一 UI 镜像跑两个容器，**每个 UI 容器内置 nginx 作为自己的同源入口**（不存在第三个统一网关，原因见 12.2）；目标机 `192.168.31.90` 为 **x86_64**，所有镜像必须按 `linux/amd64` 构建。
4. **不改 Python 核心行为、不改 UI 的 HTTP/SSE 契约、不新增 `ui-java/`**。Java 侧对外 JSON 一律 snake_case，不加 `Result<T>` 包装。
5. **数据完全隔离**：Python 用 SQLite 卷，Java 用独立 MySQL；不共享库、不共享运行状态；共享的只有契约、测试夹具与只读技能目录。
6. **Java 后端不得调用 Python 后端**，任何一端停机不影响另一端。
7. Phase 0 只产出文档与契约骨架，不动业务代码；后续每阶段必须以真实构建/测试结果更新兼容性状态。
8. **模型端点用外部 OpenAI-compatible 服务**（DeepSeek 等），容器只需出网与密钥注入，不在服务器上跑模型运行时。
9. **容器里的工作区改为"命名创建"**：Compose 挂载 `WORKSPACE_ROOT`，用户只提交工作区名字，服务端创建 `<root>/<user>/<name>`。这是 V1.4 之后的第一项**契约扩展**（v1.1），必须在 V1.4 parity 全绿之后再落地，且两端同时实现（见 10.14、17.1）。

## 1. 背景与目标

### 1.1 为什么做

现有 `backend/`（Python）已经把 Agent Runtime 的语义跑通：Session/Run/Message/ToolCall/RunEvent、可恢复执行、持久事件 + SSE、工具审批、MCP、Skills、压缩与轨迹。现在要在同一份 UI、同一套协议下再建一个 **Java 实现**，同时承担两件事：

- 工程目标：证明"同一协议、两种语言实现"是可维护的，而不是靠翻译代码对齐；
- 学习目标：在真实业务链路里吃透 Java 企业级技术栈（Maven、Spring、MyBatis、事务、并发、SSE、JVM 诊断）。

### 1.2 成功的定义

| 维度 | 判据 |
|---|---|
| 契约 | 同一套黑盒契约测试分别打向 Python/Java，全部通过 |
| 行为 | 同一套确定性模型夹具下，两端的 Run/ToolCall/事件序列可对齐（动态字段除外） |
| 可用 | 同一份 UI 构建产物分别连两个后端，关键业务流可用 |
| 隔离 | 停掉任一后端，另一端不受影响；数据、卷、日志互不可见 |
| 学习 | 15 篇 `docs/java-learning/` 文档全部指向真实代码位置与真实调用链 |

### 1.3 反目标（技术上跑通但算失败）

- Java 通过 HTTP 调 Python 完成核心业务。
- 为了让 Java 测试通过而放宽 UI 断言、跳过功能、改契约字段。
- 用 Mock 冒充满足"功能已迁移"。
- 把 Agent Loop 藏进 Spring AI / LangChain4j 等框架，导致学习者看不到执行链路。
- 为对齐而把 Java 写成 Python 的逐行翻译（丢 Java 工程惯例）。

## 2. 事实基线（V1.4 实测）

以下均为 2026-11-27 对本地源码的核对结果，不是文档转述。

### 2.1 工程现状

| 项 | 事实 |
|---|---|
| 分支 | `feat/v1.4`，工作区干净，HEAD `343a682` |
| Python 规模 | `backend/src/prism_agent_kit` 93 个文件、11,663 行；`backend/migrations` 7 个版本 |
| Python 测试 | 336 passed（`docs/releases/v1.4.0.md` 验证记录） |
| UI 规模 | `ui/src/lib/api` 5 个文件 919 行；80 个 vitest 用例 |
| 容器化 | **仓库内没有任何 Dockerfile / compose / nginx 配置** |
| 代理配置 | `PRISM_UI_API_TARGET` 只被 Vite dev server 读取；构建产物只有 `VITE_API_BASE_PATH=/api/v1` |
| 跨进程模型替身 | 不存在。`backend/tests/fakes.py` 只能进程内注入；唯一独立进程夹具是 `support/mcp_http_server.py` |
| 端口写死 | Playwright `3000/8000`、`vite.config.ts` 的 `127.0.0.1:3000` |

### 2.2 对外端点清单（42 个）

统一前缀 `/api/v1`；除 `/health` 外均要求 `Authorization: Bearer <token>`。

| # | Method | Path | 成功码 | 请求要点 | 响应要点 |
|---|---|---|---|---|---|
| 1 | GET | `/health` | 200 | — | `status/service/version/environment/workspace_fts` |
| 2 | POST | `/sessions` | 201 | `{title?<255}` | `SessionView` |
| 3 | GET | `/sessions` | 200 | — | `{items:[SessionView]}` |
| 4 | GET | `/sessions/{id}` | 200 | — | `SessionView`；404 `SESSION_NOT_FOUND` |
| 5 | GET | `/sessions/{id}/messages` | 200 | — | `{items:[MessageView]}`，按 `id` 升序 |
| 6 | POST | `/sessions/{id}/workspace` | 200 | `{workspace_id:str\|null}` | `SessionView` |
| 7 | POST | `/sessions/{id}/compact` | 200 | — | `{compacted,...}`；409 `COMPACTION_BUSY` |
| 8 | POST | `/sessions/{id}/runs` | 202 | `{input,prompt_ref?,metadata?,skill_name?}` | `RunView`；409 `RUN_CONFLICT` |
| 9 | GET | `/runs/{id}` | 200 | — | `RunView` |
| 10 | POST | `/runs/{id}/cancel` | 200 | — | `RunView`（幂等） |
| 11 | GET | `/runs/{id}/events` | 200 | `Last-Event-ID` 头；`once` 仅 test | `text/event-stream` |
| 12 | POST | `/runs/{id}/tool-calls/{cid}/result` | 200 | `{ok,input_digest,output?,error?}` | `ToolCallView`；409 三类 |
| 13 | GET | `/runs/{id}/tool-calls/{cid}/preview` | 200 | — | `{kind,path,mode,bytes,exists,diff,truncated,input_preview}` |
| 14 | POST | `/runs/{id}/tool-calls/{cid}/approval` | 200 | `{decision,reason?<200}` | `{call,run}` |
| 15 | GET | `/tools` | 200 | — | `{items:[ToolView]}` |
| 16 | GET | `/workspaces` | 200 | — | `{items,active_id}` |
| 17 | POST | `/workspaces/pick` | 200 | — | `{path}`；容器内 409 `WORKSPACE_PICKER_UNAVAILABLE` |
| 18 | POST | `/workspaces` | 200 | `{path,label?}` | `WorkspaceView` |
| 19 | GET | `/workspaces/{id}` | 200 | — | `WorkspaceView` |
| 20 | POST | `/workspaces/{id}/activate` | 200 | — | `WorkspaceView` |
| 21 | POST | `/workspaces/{id}/reindex` | 200 | — | `WorkspaceView` |
| 22 | DELETE | `/workspaces/{id}` | 204 | — | 活跃区 409 |
| 23 | GET | `/workspaces/{id}/tree` | 200 | `path="."` | `{items:[{name,type,size?,modified_at?}]}` |
| 24 | GET | `/workspaces/{id}/file` | 200 | `path`,`max_bytes=65536` | `{path,content,truncated,size}` |
| 25 | GET | `/workspaces/{id}/search` | 200 | `q`,`limit=20`,`path_prefix?` | `{items:[{path,snippet}]}` |
| 26 | GET | `/mcp/servers` | 200 | — | `[McpServerView]`（密钥掩码） |
| 27 | POST | `/mcp/servers` | 200 | `McpServerCreate` | `McpServerView`（不建连） |
| 28 | PATCH | `/mcp/servers/{id}` | 200 | 全量 `McpServerCreate` | `McpServerView` |
| 29 | DELETE | `/mcp/servers/{id}` | 204 | — | 有活动 Run 时 409 |
| 30 | POST | `/mcp/servers/{id}/enable` | 200 | — | 连接并注册工具 |
| 31 | POST | `/mcp/servers/{id}/disable` | 200 | — | 断开并摘除工具 |
| 32 | POST | `/mcp/servers/{id}/reconnect` | 200 | — | 重连刷新工具 |
| 33 | GET | `/mcp/servers/{id}/tools` | 200 | — | `{server_id,tools[]}` |
| 34 | GET | `/skills` | 200 | — | `{items:[{name,description,path,root,shadowed}]}` |
| 35 | GET | `/skills/{name}` | 200 | — | `{name,description,content,resources[]}` |
| 36 | GET | `/model-profiles` | 200 | — | `[ModelProfileView]` |
| 37 | POST | `/model-profiles` | 200 | `ModelProfileCreate` | `ModelProfileView` |
| 38 | PATCH | `/model-profiles/{id}` | 200 | 全量 | `ModelProfileView` |
| 39 | DELETE | `/model-profiles/{id}` | 204 | — | 活跃档案 409 `MODEL_PROFILE_IN_USE` |
| 40 | POST | `/model-profiles/{id}/activate` | 200 | — | 全局唯一 active |
| 41 | POST | `/model-profiles/{id}/probe` | 200 | — | `{ok,latency_ms,error}`，失败也是 200 |
| 42 | GET | `/sessions/{id}/trajectory` | 200 | `limit 1..200=50`,`before?` | `{turns:[{run,steps,compactions}]}` |

错误信封统一为：

```json
{"error":{"code":"RUN_CONFLICT","message":"...","request_id":"...","details":{}}}
```

响应头同名回显 `X-Request-ID`；401 带 `WWW-Authenticate: Bearer`。

### 2.3 事件清单（27 类：25 持久 + 2 临时）

`EventType` 共 27 个取值；`message.delta`、`reasoning.delta` 不落库；**UI 只解析其中 19 个**，其余 8 个（`context.pruned`、`step.started/completed/failed`、`compaction.started/completed/failed/skipped`）UI 会跳过。

| 事件 | 持久 | payload 关键字段 | 触发点 |
|---|---|---|---|
| `run.queued` | ✔ | `prompt_ref, metadata` | Run 创建事务 |
| `run.started` | ✔ | — | 引擎首个 Step 前（只写一次） |
| `step.started` | ✔ | `step_index, model, model_profile_id` | 每步调用模型前 |
| `step.completed` | ✔ | `step_index, usage, duration_ms, finish_reason, tool_call_ids` | 模型流结束 |
| `step.failed` | ✔ | `step_index, error_code, duration_ms` | 模型流失败 |
| `assistant.completed` | ✔ | `message_id, tool_call_ids` | 持久化 assistant 消息 |
| `tool.requested` | ✔ | `call_id, tool_name, execution_mode, input, input_digest`；审批类改为 `kind/path/mode/bytes` 摘要 | 持久化 ToolCall |
| `tool.completed` | ✔ | `call_id, tool_name, message_id` | 工具成功 |
| `tool.failed` | ✔ | `+ error_code, error_message` | 工具失败/取消闭合 |
| `tool.expired` | ✔ | 同上 | 远端超时/审批超时 |
| `run.waiting_for_tool` | ✔ | `call_ids` | 进入等待远端 |
| `run.waiting_for_approval` | ✔ | `call_ids` | 进入等待审批 |
| `tool.approval_required` | ✔ | `call_id, tool_name, kind, path/mode/bytes` 或 `input_preview, input_digest` | 审批请求 |
| `tool.approved` | ✔ | `call_id` | 用户允许 |
| `tool.rejected` | ✔ | `call_id, reason` | 用户拒绝 |
| `run.requeued` | ✔ | `call_ids` | 工具全部闭合后回队 |
| `context.trimmed` | ✔ | `trimmed_count, trimmed_tokens` | 装配裁剪 |
| `context.pruned` | ✔ | `pruned_chars, pruned_count` | tool 结果头尾裁剪 |
| `compaction.started` | ✔ | `tokens_before, forced` | 摘要开始 |
| `compaction.completed` | ✔ | `checkpoint_id, tokens_before, tokens_after, usage` | 摘要成功 |
| `compaction.failed` | ✔ | `error, error_code` | 摘要失败（继续跑） |
| `compaction.skipped` | ✔ | `reason` | 无可压缩段 |
| `run.succeeded` | ✔ | `message_id` | 无工具调用即完成 |
| `run.failed` | ✔ | `error_code, error_message` | 终态 |
| `run.cancelled` | ✔ | — | 终态 |
| `message.delta` | ✘ | `text` | 文本增量 |
| `reasoning.delta` | ✘ | `text` | reasoning 增量 |

SSE 帧形态（必须逐字对齐）：

```text
event: tool.completed
id: 42
data: {"type":"tool.completed","run_id":"...","call_id":"...","tool_name":"...","message_id":7}
```

- 持久事件：`id` 必为**纯数字**且随 Run 递增；临时增量：**不得有 `id` 行**。
- `data` 是 payload 平铺进 `{type,run_id}` 的 JSON，非对象 payload 才会出现 `payload` 字段。
- 心跳为注释行（`:` 开头），间隔默认 15s。
- 终态事件后服务端关闭流；终态 Run 的重连只做有限重放。

### 2.4 状态机

```
Run:      queued → running → waiting_for_tool | waiting_for_approval
          waiting_* → queued（工具全部闭合）/ running
          任意非终态 → succeeded | failed | cancelled（终态不可逆）
ToolCall: pending → running | awaiting_approval
          awaiting_approval → running（批准）/ failed（拒绝）
          running → succeeded | failed | expired（超时闭合）
MCP:      disabled → connecting → connected → error → (reconnect)
Index:    idle → indexing → ready | failed
```

关键不变量：终态 Run 必闭合所有 ToolCall；`cancel_requested_at` 一旦写入，后续成功迁移需带 `cancel_requested_at IS NULL` 条件。

### 2.5 持久化事实

- 9 张业务表：`workspaces/sessions/runs/messages/tool_calls/run_events/mcp_servers/model_profiles/compaction_checkpoints`，另有 FTS5 虚表 `workspace_documents`。
- ID：session/run/workspace/mcp/profile/checkpoint 为 UUID4 字符串；ToolCall ID 由模型下发（≤128）；message/event 为自增整数。
- 时间：领域层 UTC aware，落库前转 naive UTC，读回补 UTC。
- 三个**部分唯一索引**：单会话单活动 Run、workspace 单活跃、model_profile 单 active；`messages(run_id, tool_call_id)` 唯一（`tool_call_id IS NOT NULL`）。
- 事件与状态变更在同一 UoW/事务提交；终态迁移 + 事件 + 工具闭合同事务。
- `claim_next` = 选最早 `queued` 后条件 UPDATE 抢锁（`UPDATE ... WHERE id=? AND status='queued' RETURNING`）。
- FTS5 tokenizer = `trigram`：≥3 字走 `MATCH` + `bm25` + `snippet(...,16)`；<3 字退化为 `instr` 全表扫描且不排序。
- 工具输入摘要 `input_digest` 是对规范化 JSON 的 sha256；重复回填幂等，冲突 409。

### 2.6 UI 的硬约束（Java 必须满足）

来自 `ui/src/lib/api/contracts.ts` 与 `sse.ts`：

1. DTO 用 zod 严格校验：`id` 非空串、`created_at` 等必须是带偏移的 ISO 时间、`message.id` 正整数。
2. 事件 `type` 必须与 SSE `event:` 名一致，否则抛错。
3. 持久事件 `id` 必须匹配 `^\d+$`；`message.delta`/`reasoning.delta` 必须 `id === null`。
4. 每条事件 `run_id` 必须等于订阅的 run，否则视为协议错误终止。
5. 不认识的事件会被跳过（`console.warn`），**多发安全、少发/改字段不安全**。
6. 终态以 `run.succeeded/failed/cancelled` 三个事件名判定。
7. 错误响应必须是 `{error:{code,message,request_id,details}}`。

### 2.7 与任务书正文的差异（以源码为准）

| 任务书说法 | 实际 |
|---|---|
| 第 8 节功能基线 | 缺压缩、轨迹、模型档案、标题生成、会话工作区绑定 |
| "复用现有 `PRISM_UI_API_TARGET` 的部署设计" | 该变量只服务 dev 代理，生产部署是净新增 |
| "现有 UI Docker Image" | 不存在任何容器产物 |
| "Session 删除、重命名未实现" | 属实；`title` 只能由生成服务写入，无改标题接口 |
| 技能/工作区文档 | `docs/skills.md` 仍标 V1.3；FTS 不可用错误码定义但从未抛出 |

**唯一新增的契约扩展**：命名工作区（10.14、17.1）。它不属于 V1.4，因此排在 parity 全绿之后，并且必须两端同时实现、同时进契约快照；在它落地前，V1.4 的 42 个端点保持逐字对齐。

## 3. 目标 / 非目标

### 3.1 目标

1. 42 个端点、27 类事件、4 个状态机的**外部语义**与 V1.4 等价。
2. 独立 MySQL 持久化，事务边界、幂等、恢复语义对齐。
3. 同一 UI 源码 + 同一镜像，两个容器分别连两个后端。
4. 一套黑盒契约/行为测试同时验证两端；一套 UI E2E 跑两个地址。
5. 一条 `docker compose up -d --build` 起完整双后端；支持只起一端。
6. Java 可在宿主机 IDE 独立启动、断点调试。
7. 学习文档与真实代码/调用链一一对应。

### 3.2 非目标

- 不新增 V1.4 之外的业务能力（记忆、Workflow、多 Agent）。
- 不迁移 Python 到 MySQL，不改 SQLite schema。
- 不做 Session 删除/重命名。
- 不引入 Spring Cloud、Nacos、Kafka、Redis、K8s、独立 Worker 服务。
- 不做 WebFlux 响应式重构（SseEmitter + MVC 为准）。
- 不做多实例部署下的 SSE 广播（单实例语义，与 Python 一致）。

### 3.3 反目标

- 为"看起来更 Java"给接口加包装层或改字段名。
- 把 Java 端做成 Python 的 HTTP 代理或 golden 回放器。
- 用无限队列/无限线程池掩盖背压问题。
- 让事务跨越模型请求、SSE 连接或审批等待。

## 4. 约束

1. 目标机 `192.168.31.90` 为 x86_64；本机 Mac 为 arm64 → 镜像统一 `linux/amd64`，本机通过 `DOCKER_DEFAULT_PLATFORM` 或 buildx 构建。
2. Python 端除"新增容器化所需的最小配置"外不改行为；任何 Python 改动必须证明无回退。
3. Java 对外 JSON 一律 snake_case；内部 Java 命名按惯例。
4. 不引入 Lombok、不做过度抽象、不滥用反射/AOP。
5. MySQL 8.x（建议 8.4 LTS 镜像），字符集 `utf8mb4`。
6. 模型端点通过环境变量配置，容器不得假设 `localhost` 可达宿主机。

## 5. 方案选择

| 方案 | 做法 | 代价 |
|---|---|---|
| A 契约快照 + 纵向切片（**选定**） | 冻结 OpenAPI/事件 schema/fixtures，每阶段端到端打通一条链 | Phase 0 契约整理必须扎实 |
| B 基础设施先行 + 水平分层 | 先铺框架与文档，再逐域实现 | Phase 1 无可运行产物，反馈闭环晚，文档易脱离代码 |
| C Python 对拍优先 | 录 golden，Java 按 golden 实现 | 易写成翻译层；动态字段归一化会洗掉语义差异 |

选 A 的理由：同时满足"学习"和"对齐"；第 18 节 Phase 2 的验收（UI 不改业务代码即可连 Java）只有纵向切片能做到；每阶段都有真实调用链可讲，学习文档不必编造。

## 6. 总体架构

### 6.1 部署拓扑

```text
                    Browser
                       │
        ┌──────────────┴──────────────┐
        │                             │
   ui-python :3000              ui-java :3001
   (nginx + 静态产物)            (同一镜像 + 同一产物)
        │ /api/                       │ /api/
   backend-python :8000         backend-java :8001
   FastAPI + SQLite             Spring Boot + MySQL
        │                             │
   python-data 卷                mysql-java + mysql-data 卷
```

- 两套 UI 容器使用**同一个 image tag**，仅运行时环境变量不同（`API_TARGET`）。
- 两个 Backend 无启动依赖；UI 只依赖对应 Backend 的 **ready** 健康检查。
- Java 启动时先等 MySQL 可用并跑 Flyway，再开放端口。

### 6.2 进程与数据隔离

| 资源 | Python | Java |
|---|---|---|
| 数据库 | SQLite 文件（独立卷） | MySQL（独立实例 + 卷） |
| 迁移 | Alembic | Flyway |
| 工作区 | `workspace-python` 卷 | `workspace-java` 卷 |
| Skills | 只读挂载 | 只读挂载（可指向同一只读目录） |
| 日志 | 容器日志（轮转） | 容器日志（轮转） |
| MCP 配置 | SQLite 表 | MySQL 表 |

### 6.3 一次 Run 的端到端时序

```text
POST /sessions/{id}/runs
  → RunService: 校验 prompt/skill/profile → 单事务写 user message + run(queued) + run.queued 事件
  → 返回 202 RunView
GET /runs/{id}/events（UI 在创建成功后立即订阅）
  → 注册订阅者 → 按游标重放 → 转入实时
RunWorker（N 个虚拟线程）
  → claim: SELECT ... FOR UPDATE SKIP LOCKED → UPDATE running → commit
  → AgentEngine: 装配上下文 → Provider.stream(delta→SSE) → 持久化 assistant/tool_calls
  → 本地工具执行/审批等待/远端等待 → 继续或终态
  → 每个事务提交后 publish 事件 → 订阅者去重后下发 → 终态关闭流
```

## 7. Java 技术栈与依赖治理

### 7.1 版本矩阵（2026-11-27 从 Maven Central 元数据核对）

| 组件 | 版本 | 依据 |
|---|---|---|
| JDK | 21 LTS（Temurin） | 任务书；虚拟线程可用 |
| Maven | 3.9.x + Wrapper | 任务书 |
| Spring Boot | **3.5.16**（3.5.x 最新） | 元数据 `latest 3.5.x` |
| Spring Framework | 6.2.x（随 Boot 3.5 BOM） | 不手工指定 |
| MyBatis-Plus | **3.5.18**（`mybatis-plus-spring-boot3-starter`） | 元数据 |
| Flyway | 由 Boot 3.5.16 BOM 管理 + `flyway-mysql` 同版本 | 只补数据库模块 |
| MySQL Server | 8.4 LTS 镜像 | 任务书 MySQL 8.x |
| MySQL Driver | `mysql-connector-j`，由 Boot BOM 管理 | 不手工指定 |
| Spring AI | **1.1.8**（1.1.x 最新） | 元数据；仅用于评估/旁路 |
| MCP Java SDK | **1.1.5**（1.x 最新，与 Spring AI 1.1 同代） | 元数据；Phase 5 实测后可评估 2.2.0 |
| Token 估算 | `com.knuddels:jtokkit` **1.1.0** | 元数据；cl100k 与 tiktoken 同族 |
| Diff | `io.github.java-diff-utils:java-diff-utils` | 审批预览 |
| 测试 | JUnit 5、Mockito、MockMvc、Testcontainers MySQL | 随 Boot BOM |

> 所有版本在 Phase 1 以真实 `mvn -q dependency:tree` 与构建结果为准；BOM 优先，禁止手写一长串版本号。Flyway/MySQL Driver 的具体版本以 BOM 解析结果记录到 `docs/compatibility/java-dependency-matrix.md`。

### 7.2 依赖原则

- 只用 `spring-boot-dependencies` + 少量 BOM（Spring AI、MCP SDK）；不引入第二套日志/JSON/HTTP 栈。
- 不引入 Lombok；DTO 用 `record`，实体用显式 getter/setter 或不可变 + 构造器。
- 不引入 MapStruct/AOP 框架；手写映射，保持可断点。
- 传递依赖冲突用 `dependency:tree` + `enforcer` 收敛，不靠"能跑就行"。

### 7.3 Spring AI 的定位（明确取舍）

**结论：Agent Runtime 的模型流式链路不用 Spring AI 承载。**

原因：Python 契约要求精确控制 `reasoning_content` 增量、按 `index` 聚合多工具调用、`finish_reason` 原值、流末 `usage`、仅在首个增量前重试、429/5xx/超时到错误码的映射。这些是**协议行为**，不能依赖框架的抽象层去"大致表达"。

落地方式：

- 主路径：`OpenAiCompatibleModelProvider`，JDK `HttpClient` + Jackson 手工解析 SSE，行为逐条对齐（见 10.9）。
- 旁路：Phase 3 写一个 Spring AI 1.1.8 的对照实验（同一批夹具跑一遍），把"哪些字段/语义表达不出来"写成 `docs/java-learning/10-spring-ai-and-provider.md` 的实证结论。
- 若 Phase 3 实验证明 Spring AI 能完整表达，再单独提设计替换主路径，不在本设计里预先切换。

MCP 同理：直接用 MCP Java SDK，不用 Spring AI 的 MCP Client Starter，避免多一层自动配置。

### 7.4 检索方案（工作区搜索）

候选：

| 方案 | 优点 | 问题 |
|---|---|---|
| MySQL FULLTEXT + ngram | 无新组件，随库持久化 | 与 FTS5 trigram 结果/排序不同 |
| Lucene 独立模块 | 语义可控、可复刻 bm25 | 新增索引生命周期与文件一致性负担 |
| 纯 `LIKE` 扫描 | 行为与短查询分支一致 | 大目录性能差 |

**选定：MySQL FULLTEXT（ngram，`ngram_token_size=2`）+ 短查询回退 `LIKE`**，并显式复刻 Python 的短查询分支：

- `len(q) < 3`：`WHERE content LIKE '%q%'`，不排序、按 `rel_path` 升序（与 `instr` 分支一致）。
- `len(q) >= 3`：`MATCH(content) AGAINST(? IN BOOLEAN MODE)` 取候选，Java 侧生成 snippet；`path_prefix` 用 `rel_path LIKE` 前置过滤。
- 排序：按相关度（MySQL score）降序、`rel_path` 升序；**不保证与 bm25 顺序一致**，记为已知差异 K-02。
- snippet：复刻 `[...]` 标记与 16 词窗口的**近似**实现（按字符窗口），差异记 K-02。

验收用固定语料：单词查询的结果**路径集合**必须与 Python 一致（忽略排序与截断并列项），snippet 必须包含查询词与方括号标记。

## 8. Java 工程结构

### 8.1 为什么单模块

任务书允许"多模块工程的基本机制"作为学习点，但第一阶段拆模块会带来：跨模块循环依赖、Spring 扫描边界、构建时间翻倍，而收益只有"看起来分层"。

**决定：单 Maven 模块 `backend-java/`，内部用 package 强制依赖方向**；在 `docs/java-learning/02-maven-and-build.md` 里用这个单模块工程讲清 lifecycle、scope、BOM、plugin 与"如果拆多模块该怎么拆"。

### 8.2 目录与依赖方向

```text
backend-java/
├── pom.xml
├── mvnw / mvnw.cmd / .mvn/
└── src/main/java/com/prism/agent/
    ├── api/            controller, dto, security, exception, sse
    ├── application/    service, worker, event
    ├── core/           domain, engine, context, prompt, state
    ├── providers/
    ├── tools/
    ├── mcp/
    ├── skills/
    ├── workspace/
    ├── persistence/    entity, mapper, repository
    ├── config/
    └── common/
```

依赖方向（编译期即可检查）：`api → application → core`；`application → providers|tools|mcp|skills|workspace|persistence`；`core` **只能依赖 common 与 JDK**，不得 import Spring/MyBatis/Jackson 注解（唯一例外：DTO 不在 core）。

### 8.3 核心接口

| 接口 | 职责 | 对应 Python |
|---|---|---|
| `AgentEngine` | `execute/resume/cancel`，返回 `EngineOutcome` | `core/engine.py::AgentEngine` |
| `ModelProvider` | `stream(request, deltaConsumer)` | `core/ports.py::ModelProvider` |
| `ToolRegistry` / `ToolDefinition` | 工具注册、schema、审批标记 | `tools/registry.py`、`tools/contracts.py` |
| `EventPublisher` / `RunStreamHub` | 事务提交后发布 + 订阅 | `application/event_bus.py` |
| `Repository` + `TransactionTemplate` | 短事务工作单元 | `db/uow.py` |
| `TokenEstimator` | 上下文预算估算 | `core/token_budget.py` |
| `WorkspaceLocator` | 工作区根与检索回调 | `core/ports.py` |

### 8.4 Python → Java 模块映射

| Python | Java | 说明 |
|---|---|---|
| `api/routes/*.py` | `api/controller/*Controller` | 只做参数绑定与 DTO 转换 |
| `api/schemas.py` | `api/dto/*` | `record` + Bean Validation |
| `api/auth.py` | `api/security/ApiTokenFilter` | 常量时间比较、health 放行 |
| `api/errors.py` | `api/exception/GlobalExceptionHandler` | 同一错误信封 |
| `application/*_service.py` | `application/service/*` | `@Transactional` 边界 |
| `application/run_worker.py` | `application/worker/RunWorker` + `ExpirySweeper` | 虚拟线程 + 短事务 |
| `application/event_bus.py` | `application/event/RunStreamHub` | 内存订阅 + 库内重放补偿 |
| `application/cancellation.py` | `application/worker/CancellationRegistry` | `ConcurrentHashMap<String, RunCancelSignal>` |
| `core/engine.py` | `core/engine/SimpleAgentEngine` | 执行链核心，保持无 Spring |
| `core/context.py` + `token_budget.py` + `compaction.py` | `core/context/*` | 装配、裁剪、压缩 |
| `core/prompts.py` | `core/prompt/PromptRegistry` | 文本来自 `contracts/prompts/` |
| `providers/openai_compatible.py` | `providers/OpenAiCompatibleModelProvider` | 手工 SSE 解析 |
| `tools/*` | `tools/*` | 本地工具 + 执行器 |
| `mcp/*` | `mcp/*` | MCP Java SDK |
| `skills/*` | `skills/*` | SKILL.md 解析、目录、工具 |
| `workspace/*` | `workspace/*` | 索引、检索、文件安全 |
| `db/*` | `persistence/*` | Entity/Mapper/Repository |
| `core/config.py` | `config/PrismProperties` | `@ConfigurationProperties` |
| `db/mappers.py` | `persistence/*Mapper` | 显式映射 |

## 9. 契约治理

### 9.1 事实来源顺序

1. 真实运行中的 Python 服务（黑盒）；
2. Python 源码中的 Pydantic 模型与路由；
3. FastAPI 导出的 OpenAPI；
4. UI 的 zod 校验与 SSE 解析；
5. 现有测试夹具。

冲突时以 1/2 为准，UI 校验作为"客户端可接受性"约束，OpenAPI 只作快照与辅助。

### 9.2 `contracts/` 布局

```text
contracts/
├── openapi/prism-agent-api.yaml      # 由运行中的 Python 导出，提交快照
├── events/events.schema.json         # 27 事件 JSON Schema + 序不变量说明
├── prompts/default@1.md              # system prompt 原文
├── prompts/compaction-summary.md     # 8 段摘要 prompt
├── prompts/session-title.md
├── fixtures/http/*.json              # 关键响应样本（脱敏 + 动态字段占位）
├── fixtures/model/*.json             # 确定性模型场景脚本
└── README.md                         # 冻结/变更规则
```

### 9.3 冻结与变更流程

1. 契约快照只在 Phase 0 与"Python 真实行为变化"时更新，更新必须有 diff 说明与双端影响分析。
2. 任何字段名、枚举值、错误码、事件名、状态码变更 = 破坏性变更，需单独评审。
3. Java 端不得"顺手补齐"契约里没有的字段；不上 `Result<T>`，不改大小写。
4. CI（本地脚本）校验：`contracts/openapi` 与 Python 当前导出一致；契约测试全绿。
5. **OpenAPI diff 只能当提示，不能当判定**；判定靠黑盒契约测试。

### 9.4 动态字段归一化与事件比对规则

对比 Python/Java 响应前统一处理：`id`、`message_id`、`created_at/updated_at/started_at/finished_at`、`duration_ms`、`latency_ms`、`tokens_*`、`expires_at`、`request_id`、事件 `id` 全部替换为占位符；只校验类型、格式、单调性与相对关系（如 `finished_at >= started_at`）。

事件比对按**事件类别**分三档，避免 token 估算差异把 parity 变成随机失败：

| 档 | 事件 | 比较方式 |
|---|---|---|
| 严格序 | `run.queued/started/succeeded/failed/cancelled`、`assistant.completed`、`tool.*`、`run.waiting_*`、`run.requeued` | 顺序与 payload 全等（动态字段除外） |
| 结构序 | `step.*` | 顺序、数量、（存在的）字段集合必须一致；`usage/duration_ms` 只校验类型 |
| 存在性 | `context.*`、`compaction.*` | 触发的**相对位置**必须一致（第 N 个 assistant 消息之前/之后）；同一步内出现多次不比较次数；token 数值不比较 |

配套要求：Phase 3 增加一个"估算器对照实验"，对固定语料分别用 tiktoken 与 jtokkit 计算，记录偏差分布到 `docs/compatibility/token-estimator-delta.md`；偏差不得改变裁剪/压缩的**判定顺序**（先 prune 再估算再压缩），只允许改变触发所在步。

## 10. Java 运行时详细设计

### 10.1 Run 抢占（claim）

```sql
BEGIN;
SELECT id FROM runs WHERE status='queued'
ORDER BY created_at, id LIMIT 1
FOR UPDATE SKIP LOCKED;
UPDATE runs SET status='running', started_at=? WHERE id=? AND status='queued';
COMMIT;
```

- 影响行数 0 → 回到轮询；100ms 间隔，与 Python 一致。
- 提交后才开始执行，避免长事务包住模型调用。
- Worker 数量 = `prism.worker.concurrency`（默认 2），每 worker 一个**虚拟线程**循环 claim → 执行 → 再 claim。
- 执行前注册 `RunCancelSignal`（`AtomicBoolean`），结束后注销。

### 10.2 单会话单活动 Run

MySQL 无部分唯一索引，用**生成列 + 唯一索引**：

```sql
ALTER TABLE runs
  ADD COLUMN active_session_id VARCHAR(36)
  GENERATED ALWAYS AS (
    CASE WHEN status IN ('queued','running','waiting_for_tool','waiting_for_approval')
         THEN session_id ELSE NULL END
  ) STORED,
  ADD UNIQUE KEY ux_runs_one_active_per_session (active_session_id);
```

插入第二个活动 Run 触发唯一冲突 → 映射为 `RUN_CONFLICT`/409，与 Python 捕获 `IntegrityError` 等价。workspace 单活跃、model_profile 单 active 用同一手法（`generated column ... UNIQUE`，多 NULL 允许）。

### 10.3 状态迁移与并发

- 统一 `RunStateMachine`：`Map<RunStatus, Set<RunStatus>>`，终态集合为空集。
- CAS 更新：`UPDATE runs SET status=?, ... WHERE id=? AND status=?`；失败重读重试 3 次后 409 `INVALID_RUN_TRANSITION`。
- `cancel_requested_at` 只对非终态写、带 `IS NULL` 条件，保证幂等。
- 成功迁移（`SUCCEEDED`）额外带 `cancel_requested_at IS NULL` 条件，覆盖"取消与完成竞态"。

### 10.4 事件序（与 SQLite 的关键差异）

SQLite 写串行，自增 id 顺序 == 提交顺序；MySQL 自增 id 是**分配顺序**，并发事务可能先提交后分配。若直接用自增 id 当 SSE 游标，会出现"收到 11 却永远补不到 10"。

**设计：事件按 Run 编号。**

```sql
run_events(id BIGINT AUTO_INCREMENT PK, run_id, seq INT NOT NULL, ...)
UNIQUE KEY ux_run_events_run_seq (run_id, seq)
```

- 分配：同一事务内先 `UPDATE runs SET last_event_seq = last_event_seq + 1 WHERE id=?`（行锁），再以返回的值插入事件。
- 因为持锁到提交，**seq 顺序 == 提交顺序**；`seq` 作为 SSE `id`（纯数字）。
- 重放：`SELECT ... WHERE run_id=? AND seq > ? ORDER BY seq`。
- 直播仍保留 Python 的"补读直到触发事件"补偿：先注册订阅 → 重放 → 收到实时事件时先查库补齐 `seq <= 当前` 的缺口，再下发。
- 禁止反向加锁顺序（先写事件再锁 run 行会死锁），在代码注释与文档中标注。
- 这是**内部差异**：对外仍是"每 Run 单调递增数字 id"，与原语义一致。

### 10.5 SSE

- 每个订阅 = 一个 `SseEmitter`；`spring.mvc.async.request-timeout=-1`，心跳由共享 `ScheduledExecutor` 每 15s 写注释行。
- 订阅注册表：`ConcurrentHashMap<String, Set<Subscriber>>`；`Subscriber` 内含 `ArrayBlockingQueue<EventEnvelope>(1024)` 与一个虚拟线程消费。
- 队列满：**不阻塞发布方**，以 error 完成该 emitter，客户端带 `Last-Event-ID` 重连并从库补齐（比 Python 的无界队列更安全，记 K-03）。
- 断连：`onCompletion/onTimeout/onError` 注销订阅；Run 执行不受影响。
- 终态：`run.succeeded/failed/cancelled` 下发后 `complete()`；终态 Run 的新连接走有限重放并立即结束。
- `once=true` 仅在 `prism.environment=test` 生效，否则 400 `INVALID_REQUEST`。
- `Last-Event-ID` 非数字/负数 → 400 `INVALID_REQUEST`，与 Python 一致。

### 10.6 取消、超时与恢复

| 场景 | 行为 |
|---|---|
| HTTP 取消（queued/等待态） | 直接闭合工具 + 终态 + 事件（单事务） |
| HTTP 取消（running） | 写 `cancel_requested_at` + 置内存信号；Worker 在安全点收尾 |
| 模型流进行中取消 | 逐块检查信号并中止 HTTP 流，统一走 `cancel` 收尾（比 Python 更早生效，K-04） |
| 远端工具超时 | 15s 扫描器把 `pending/running` 中 `expires_at<=now` 置 `expired`，闭合后回队 |
| 审批超时 | 同上，错误码 `TOOL_APPROVAL_TIMEOUT` |
| 进程重启 | 启动时把遗留 `running` 置 `failed` + `PROCESS_INTERRUPTED`，闭合工具并写事件 |
| 步骤上限 | `step_count >= max_steps` → `HARNESS_STEP_LIMIT` |

### 10.7 工具执行与审批

- 执行器按 `ToolDefinition.executionMode` 分派：`LOCAL` 直接调用，`REMOTE` 只登记。
- 超时取 `min(definition.timeout, global.toolTimeout)`。
- 审批：`requires_approval` 的调用不执行，置 `awaiting_approval` + `expires_at`，Run 转 `waiting_for_approval`，发 `run.waiting_for_approval` + 每个 `tool.approval_required`。
- 决策：`UPDATE tool_calls SET status='running' WHERE id=? AND status='awaiting_approval'`（CAS）；0 行 → 重读后按"终态幂等/409 冲突"处理，覆盖重复点击与并发。
- 批准后执行 → 记录结果 → `finalize`；拒绝 → `failed` + `tool.rejected` + `finalize`。
- `finalize` 规则与 Python 完全一致：仍有 `awaiting_approval` → 不动；有未完成远端 → `waiting_for_tool`；全部终态 → `queued` + `run.requeued`。

### 10.8 远端工具结果回填

- 校验顺序：`input_digest`（409 `TOOL_INPUT_DIGEST_MISMATCH`）→ 终态幂等 → Run 状态（409 `RUN_CONFLICT`）→ 过期（409 `TOOL_CALL_EXPIRED`）→ 输出 schema（422 `TOOL_OUTPUT_INVALID`）。
- 串行化：Python 用服务级 `asyncio.Lock`；Java 用**数据库行锁**（`SELECT ... FOR UPDATE` on tool_call）保证跨线程/跨请求一致。
- `messages(run_id, tool_call_id)` 唯一冲突 → 409 `TOOL_RESULT_CONFLICT`（等价于 Python 识别 SQLite 唯一约束）。

### 10.9 模型 Provider

- 请求体：`model/messages/stream=true/stream_options.include_usage`，有工具才带 `tools`，`max_tokens`。
- 消息重建：system 置首；assistant 的 `tool_calls.arguments` 用**稳定 JSON**（键序固定）；tool 消息必须带 `tool_call_id`，缺失 → `MODEL_PROTOCOL_INVALID`。
- 增量聚合：`delta.content` → 文本；`reasoning_content`（或 `model_extra`）→ reasoning；`delta.tool_calls[]` 按 `index` 累积 `id/name/arguments`；参数非法 JSON / 缺 index / 缺 id → 502 `MODEL_PROTOCOL_INVALID`。
- `finish_reason` 取最后一个非空原值，不做枚举校验。
- 重试：仅在**首个文本/reasoning 增量之前**，最多 2 次，退避 `min(0.2*2^n, 1s)`；超时/连接/429/5xx 可重试。
- 错误映射：超时→`MODEL_TIMEOUT`/504；含 context 关键字的 400→`CONTEXT_OVERFLOW`/422；429→`MODEL_RATE_LIMITED`；其余→`MODEL_UPSTREAM_ERROR`/502；缺配置→`MODEL_NOT_CONFIGURED`。
- **启动校验与 Python 对齐**：没有激活档案时，`MODEL_NAME/CONTEXT_WINDOW/MAX_OUTPUT_TOKENS/TOKEN_ENCODING` 缺失即启动失败（不是延迟到请求期）；档案激活但 `api_key_env` 未设置时，创建 Run 返回 422 `MODEL_PROFILE_INVALID`。`MODEL_NOT_CONFIGURED` 只用于 Provider 构造期缺 base/model/key 的兜底。
- 取消：检查信号后 `HttpClient` 请求中断，抛 `RUN_CANCELLED` 路径。

### 10.10 上下文装配、裁剪、压缩

与 Python 逐条对齐，不做"更聪明"的改动：

1. 预算 = `contextWindow - maxOutput - safetyMargin(2048)`；≤0 → `CONTEXT_BUDGET_EXCEEDED`。
2. 配对校验：assistant 吸附其 tool 消息；id 计数不一致 → `INVALID_HISTORY`。
3. 裁剪：只从最旧的非保护单元删，剩 1 个可删即停；仍超 → 422；`skill_context`、`checkpoint` 受保护。
4. 估算：`TokenEstimator` 用 jtokkit 复刻 tiktoken 的每消息/每工具开销公式；数值允许与 Python 不同（K-05），但阈值比例、裁剪/压缩的**触发顺序**必须一致。
5. 压缩：每步装配前，估算 > 预算 85% → 选最旧一段（保留 `min(20000, 预算*0.2)`）→ 8 段摘要 → 写 checkpoint → 后续只带 `id >= first_kept_message_id` + 合成 checkpoint 消息（不入库）。
6. tool 结果预裁剪：>8000 字符保留头尾各 2000，中间插 `…(pruned N chars)…`。
7. 溢出重试：provider 报 `CONTEXT_OVERFLOW` 时强制压缩一次并重试；仍超才由装配器丢弃最旧单元。
8. 失败降级：摘要失败写 `compaction.failed` 并继续；无可用段写 `compaction.skipped`。

### 10.11 轨迹、模型档案、标题

- 轨迹：按 Run（Turn）→ Step → Tool 投影；无 `step.*` 事件的旧 Run 合成 `legacy` Step；工具按 `step.completed.tool_call_ids` 归属；`assistant_message_id` 恒 null（与 Python 一致）；compactions 按时间窗归属，未归属且 `before` 为空时挂到最后一 Turn。
- 模型档案：全局唯一 active（生成列唯一索引）；删除 active → 409；密钥只存环境变量名，构造 Provider 时读进程环境，缺失在创建 Run 前 422。
- 标题：创建 Run 提交后、`title == null` 且开关开启时**同步**生成（输入前 500 字，`max_tokens=64`，超时 8s，取首行截 20 字），失败只告警。

### 10.12 MCP 生命周期

- 用 MCP Java SDK：`stdio`（子进程 + 环境白名单）与 `streamable-http`（自定义 header）。
- 工具体命名 `mcp__<slug>__<safe>`，冲突 → `INVALID_TOOL_DEFINITION`，并按前缀回滚已注册工具。
- 所有 MCP 工具 `requiresApproval=true`。
- enable/disable/reconnect/update/delete 前：**全局**存在活动 Run → 409 `MCP_SERVER_BUSY`（与 Python 的全局判定一致，不是按会话）。
- 状态机 `disabled → connecting → connected → error`，失败写 `last_error` 并 503。
- 结果归一化：文本截断 `maxResultBytes=204800`、structured 超限→`{truncated:true}`、image/audio 只留元信息、resource→`{type:"resource"}`、`is_error`→400。

### 10.13 Skills

- 发现顺序：`prism_home/skills` → `~/.agent/skills` → `~/.agents/skills` → 显式 `skills_paths`；仅一级子目录含 `SKILL.md`；符号链接拒绝；同名先到先得，其余 `shadowed`。
- frontmatter：`name` 匹配 `^[a-z0-9]+(?:-[a-z0-9]+)*$` 且 ≤64，`description` ≤1024；坏包隔离。
- 清单格式逐字复刻 `<available_skills>` 块（按 name 排序、仅 winners、8000 字符预算、省略追加"（已省略 N 个技能）"），追加到 system prompt。
- `skill` 工具：`{name, path?}`，无 path 返回正文 + 前 50 个资源，60000 字符截断；有 path 返回单文件；拒绝 `..`/绝对路径/越界/符号链接/超 200KB/非 UTF-8。
- 显式选择：`skill_name` 快照到 Run，插 `user + skill_context` 消息（正文超 20000 字符截断），位于用户正文之前。

### 10.14 Workspace 与文件工具

- 扫描排除 `.git/node_modules/dist/build/.dart_tool/coverage`；只索引 15 类文本扩展名与 `.env*`；跳过 >1MiB、含 NUL、非 UTF-8、符号链接；上限 20000 文件。
- 索引状态与错误文本沿用 Python 语义（`truncated_at_limit`、`index_failed:<类型>`、`process_interrupted`）。
- 文件工具：`file_list/file_read/file_search/file_write`，入参出参与 Python 完全一致；写入需审批（可关）。
- 路径安全：`realpath` + 前缀校验、拒绝 `..`、拒绝符号链接、写拒绝 `.git`、`create` 已存在 409、自动建父目录。
- 审批预览：unified diff（`n=3`），截断 200 行/20KB；不存在文件或 append 模式无 diff。

#### 10.14.1 命名工作区（V1.5 扩展，parity 之后）

容器内没有 `osascript/zenity`，原生目录选择不可用；同时不允许把宿主路径直接暴露给用户输入。因此新增一种受限创建方式：

- 配置：`WORKSPACE_ROOT`（容器内如 `/workspaces`）、`WORKSPACE_USER`（默认 `default`）。
- 契约：`POST /workspaces` 的 `path` 变为可选，新增可选 `name`；二者**必须且只能给一个**。
- `name` 规则：`^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$`，拒绝 `..`、路径分隔符、保留名；违规 422 `WORKSPACE_PATH_INVALID`。
- 落盘：服务端 `mkdir -p <root>/<user>/<name>`，注册为工作区并激活，`label` 默认取 `name`。
- 仅在配置了 `WORKSPACE_ROOT` 时接受 `name`；未配置时 422。
- 原生 `path` 分支保持原语义（必须绝对路径、必须已存在），宿主机开发与既有调用方不受影响。
- 契约快照升 `v1.1`，Python 与 Java 同阶段实现；新增 parity 用例：同名创建 409/reuse 语义、越界名拒绝、目录自动创建、`WORKSPACE_ROOT` 未配置时拒绝。

**实施顺序**：Phase 4 开始时先在 Python + UI 落地（小改动、独立提交、无迁移），随后 Java 按同一契约实现；两者都通过同一批契约测试才算完成。

## 11. 数据库设计（MySQL）

### 11.1 表与关键列

| 表 | 关键列 | 约束 |
|---|---|---|
| `workspaces` | id(char36), root_path, label, is_active, index_status, index_error, file_count, indexed_at | `UNIQUE(root_path)`；单活跃生成列唯一 |
| `sessions` | id, title, workspace_id, created_at, updated_at | FK workspace SET NULL |
| `runs` | id, session_id, workspace_id, status, model_profile_id, model_context_window, model_max_output_tokens, skill_name, input_text, prompt_name, prompt_version, system_prompt, model, step_count, output_text, error_code, error_message, cancel_requested_at, last_event_seq | `active_session_id` 生成列唯一；FK session CASCADE；索引 (session_id, created_at)、(status) |
| `messages` | id bigint AI, session_id, run_id, role, kind, content JSON, reasoning, tool_call_id, created_at | `UNIQUE(run_id, tool_call_id)`；索引 (session_id, id) |
| `tool_calls` | id varchar128, run_id, assistant_message_id, tool_name, execution_mode, status, input JSON, output JSON, input_digest, error_code, error_message, expires_at, created_at, finished_at | FK run/assistant_message CASCADE；索引 (run_id, status) |
| `run_events` | id bigint AI, run_id, seq int, event_type, payload JSON, created_at | `UNIQUE(run_id, seq)`；索引 (run_id, seq) |
| `mcp_servers` | id, name, transport, command, args JSON, env JSON, url, headers JSON, enabled, status, last_error | `UNIQUE(name)` |
| `model_profiles` | id, name, base_url, model, api_key_env, context_window, max_output_tokens, is_active | `UNIQUE(name)`；单 active 生成列唯一 |
| `compaction_checkpoints` | id, session_id, summary, first_kept_message_id, tokens_before, tokens_after, pruned_chars, created_at | FK session CASCADE |
| `workspace_documents` | id bigint AI, workspace_id, rel_path, content LONGTEXT | `UNIQUE(workspace_id, rel_path)`；`FULLTEXT(content) WITH PARSER ngram` |

统一 `utf8mb4`（`utf8mb4_0900_ai_ci`），时间列 `DATETIME(6)` 存 UTC。

### 11.2 事务边界

- HTTP 请求内：Service 上一个短事务；**不跨**模型调用、SSE、审批等待。
- Worker：`claim`、`持久化模型回合`、`工具结果`、`终态` 各自短事务；事件与状态同事务。
- 事件序号在事务内通过锁定 `runs` 行分配，保证"序号顺序 = 提交顺序"。
- 隔离级别 `READ COMMITTED`；唯一约束承担幂等，不用 `SERIALIZABLE`。
- 禁止在事务中发 HTTP/读大文件/等待用户。

### 11.3 Flyway

- `V1__baseline.sql` 建全部表 + 生成列 + FULLTEXT；后续每个阶段一个 `Vn__*.sql`。
- 启动时 `flyway.migrate()`；`clean` 禁用。
- 迁移必须可回滚（down 脚本或成对 V/U），并在 Phase 7 做一次 `migrate → clean → migrate` 验证（仅测试库）。

### 11.4 与 SQLite 的语义差异（对外不可见 / 已知）

| # | 点 | 处理 |
|---|---|---|
| K-01 | 部分唯一索引 | 生成列 + 唯一索引，语义等价 |
| K-02 | 全文检索排序与 snippet | MySQL FULLTEXT + Java snippet；记录差异，按语料验收 |
| K-03 | SSE 慢消费者 | 有界队列 + 断连重连（Python 无界） |
| K-04 | 流中取消生效时点 | Java 更早中止（外部结果一致） |
| K-05 | token 估算数值 | jtokkit vs tiktoken；阈值/顺序一致，数值允许不同 |
| K-06 | 事件 id 来源 | per-run `seq`（外部仍是单调数字） |
| K-07 | 时间存储 | DATETIME(6) UTC vs SQLite text；序列化一致 |
| K-08 | `tool_call_id` 无外键 | 保持一致（不额外加 FK，避免行为差异） |

## 12. 部署与容器

### 12.1 服务与端口

| 服务 | 镜像 | 宿主端口 | 说明 |
|---|---|---|---|
| `backend-python` | 自建 `prism-backend-python` | 8000 | 启动前跑 Alembic |
| `backend-java` | 自建 `prism-backend-java` | 8001 | 等 MySQL → Flyway → 起服务 |
| `mysql-java` | `mysql:8.4` | 不暴露（dev override 3307） | 独立卷 |
| `ui-python` | `prism-agent-ui:<version>` | 3000 | `API_TARGET=http://backend-python:8000` |
| `ui-java` | 同上**同一 tag** | 3001 | `API_TARGET=http://backend-java:8080` |
| `mock-model` | 自建 | 不暴露（测试 profile） | 两后端共用 |

所有端口支持环境变量覆盖（`PRISM_PORT_PYTHON_UI` 等），默认避开已有服务。

### 12.2 UI 镜像

**没有第三个网关**：`ui-python` 与 `ui-java` 各自内置 nginx，既是静态服务也是同源入口。原因：UI 的 `parseApiBasePath` 只接受同源路径（`/api/v1`，拒绝 `//` 与绝对 URL），单端口网关无法只靠路径前缀区分两个后端，只能靠**不同端口**（3000/3001）或域名；因此保持"两个 UI 地址"是唯一不改 UI 的形态。

多阶段构建：

```dockerfile
FROM --platform=$BUILDPLATFORM node:22-slim AS build
# pnpm install --frozen-lockfile && pnpm build
FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY deploy/nginx/default.conf.template /etc/nginx/templates/default.conf.template
```

- nginx 官方镜像的 `envsubst` 机制注入 `${API_TARGET}`，**运行时可配**，不写进构建产物。
- 模板内含：`/api/` 反代（`proxy_buffering off`、`proxy_read_timeout 3600s`、`X-Accel-Buffering: no`、HTTP/1.1）、SPA 回退（`try_files $uri $uri/ /index.html`）、**`/api/` 错误不回退 HTML**。
- 同一 tag 两容器：`docker compose build ui-python` 后 `ui-java` 直接复用 image；验收用 `docker compose images` 对比 Image ID。

### 12.3 多架构

- 所有基础镜像用多架构 tag；Java 构建使用 `eclipse-temurin:21-jdk` + `21-jre`。
- 本机 arm64 构建 amd64：`DOCKER_DEFAULT_PLATFORM=linux/amd64 docker compose build`，或 `docker buildx build --platform linux/amd64`。
- 验收：`docker image inspect --format '{{.Os}}/{{.Architecture}}'` 必须为 `linux/amd64`；在服务器上 `uname -m` 为 `x86_64`。

### 12.4 健康检查

- Python：`GET /api/v1/health`（无鉴权）。
- Java：同名端点返回同结构；Actuator 仅内部使用（`/internal/actuator/health`）。
- Compose `healthcheck` 用 `wget/curl`；UI `depends_on: condition: service_healthy`。
- Java 增加 `readiness`（MySQL + Flyway 完成）与 `liveness` 区分：`management.endpoint.health.group.readiness.include=db`。

### 12.5 卷与隔离

| 卷 | 用途 |
|---|---|
| `python-data` | SQLite 文件 |
| `workspace-python` | Python 端工作区根（挂到容器 `/workspaces`，即 `WORKSPACE_ROOT`） |
| `workspace-java` | Java 端工作区根（同上） |
| `mysql-data` | MySQL 数据目录 |

- Skills 只读挂载：`./skills:/skills:ro`（可选，两容器可指向同一只读目录）。
- 禁止挂载 Docker Socket、禁止 privileged、不挂宿主用户目录。

### 12.6 模型端点

- 全部通过 env：`MODEL_BASE_URL`、`MODEL_API_KEY`、`MODEL_NAME`、窗口/输出上限。
- **已选定：外部 OpenAI-compatible 服务**（DeepSeek 等）。容器只需要出网 + 密钥注入；服务器不安装模型运行时，也不依赖 Mac 的 LM Studio。
- 若将来改为局域网/宿主模型，可按下表切换（不要在容器里用 `localhost` 指代宿主机）：

| 模型所在 | `MODEL_BASE_URL` | 备注 |
|---|---|---|
| 外部服务（当前） | `https://api.deepseek.com/v1` 等 | 需要出网与 `MODEL_API_KEY` |
| 服务器本机 | `http://host.docker.internal:11434/v1` | 需 `extra_hosts: host-gateway` |
| Mac 上的 LM Studio | `http://192.168.31.<mac>:1234/v1` | 走局域网 IP |

- 容器内一律禁止用 `localhost` 指代宿主机或另一台机器。
- **启动前置**：Python 在没有激活模型档案时，缺 `MODEL_NAME/CONTEXT_WINDOW/MAX_OUTPUT_TOKENS/TOKEN_ENCODING` 会**启动失败**（`container.py:324,343,531-543`）。Java 必须复刻这个行为（见 10.9），因此 `docker compose up` 在没有模型配置、也没有数据库内激活档案时**本来就不会 healthy**——这是契约的一部分，不是缺陷。
- `mock-model` 只存在于测试 profile，不进入默认启动。

### 12.7 MCP stdio 运行时

- **两个后端镜像都安装 `nodejs`（22 LTS）与 `ca-certificates`**，`backend-java` 额外装 `python3`：MCP stdio 服务器常用 `npx` 或 `uvx` 启动，只有一端能起会导致 parity 场景无法在同一拓扑下双跑。
- 给 Python 镜像加 node 属于"容器化所需的最小配置"，不改变 Python 代码与行为，但必须在变更说明里记录（原 Python 部署假设宿主已有 node）。
- 子进程随容器生命周期；容器停止时先关闭 MCP 客户端再退出（Java 用 `DisposableBean`，Python 沿用现有 shutdown）。
- 凭据用 env 注入，不写镜像、不写日志。

## 13. 测试策略

### 13.1 四层

| 层 | 位置 | 职责 |
|---|---|---|
| L1 语言内 | `backend/tests`（保留）、`backend-java/src/test` | 单元、仓储、MockMvc、Testcontainers |
| L2 契约 | `tests/contract` | 黑盒 HTTP/SSE，同一套打两个 BASE_URL |
| L3 行为 | `tests/parity` | 确定性 Mock Model 下的事件序列/状态机对齐 |
| L4 E2E | `ui/tests/e2e`（复用） | 同一套 Playwright 跑 3000/3001 |

### 13.2 共享 Mock Model 服务

- 独立进程，实现 `POST /v1/chat/completions`（SSE），零第三方依赖（Python 标准库）。
- 场景由请求头 `X-Prism-Scenario` 或 `model` 名选择，脚本文件在 `contracts/fixtures/model/`。
- 脚本元素：`text` 增量、`reasoning` 增量、`tool_calls`（index/id/name/arguments 分片）、`finish_reason`、`usage`、`error`（状态码/关键字）。
- 记录请求到内存，`GET /_requests` 供断言"模型看到了什么"。
- 提供 `/_reset`；禁止在生产 compose profile 中启动。

### 13.3 Parity 场景（最小集）

普通对话、多轮、单/多工具调用、远端回填（重复/冲突）、文件写审批（允许/拒绝/超时）、MCP 审批、Skill 显式/隐式、取消、步骤上限、进程中断恢复、SSE 断线重放、上下文压缩触发、Workspace 隔离，以及 V1.5 的命名工作区（创建/重名/越界名/未配置根）。

### 13.4 门禁

- Python：`ruff check`、`ruff format --check`、`mypy src`、`pytest`。
- Java：`mvn -q verify`（含 Testcontainers）。
- 契约：`tests/contract` 双后端全绿。
- E2E：两个地址全绿。
- 任何"跳过/放宽断言"必须在 PR 说明里给出理由，且不得进入 `main`。

## 14. 学习文档策略

- 目录 `docs/java-learning/00..15`，与实际代码同步提交；**没有对应实现就不写**。
- 每篇固定 10 问：是什么 / 解决什么问题 / Java 机制 / 项目代码位置 / 与 TS-Node 异同 / 与 Python-FastAPI 异同 / 常见误用 / 断点观察方法 / 实验或测试验证 / 生产注意。
- 必维护调用链：启动、Bean 注入、HTTP→Controller、Controller→Service、事务代理、Mapper→JDBC、Agent Loop、模型流、ToolRegistry、SSE 双通道、MCP 生命周期、Skill 披露。

## 15. 阶段计划（概览，细节见实施计划文档）

| Phase | 交付 | 门禁 |
|---|---|---|
| 0 | 本设计 + 实施计划 + `contracts/` 骨架 + parity 表初版 | 设计评审通过 |
| 1 | Maven/Spring/MyBatis/Flyway/鉴权/异常/健康 + Session API + 本地 IDE 运行 | UI 能建会话（其余功能显式未实现） |
| 2 | 三个 Dockerfile、UI nginx 模板、Compose、双 UI、契约测试骨架 | 两 UI 同镜像、同产物；`docker compose config` 通过 |
| 3a | Run 生命周期 + SSE + 取消/超时/恢复 + Provider + 本地工具 | 单轮对话/多工具/取消/重放绿 |
| 3b | 上下文装配/裁剪/压缩 + 轨迹 + 模型档案 + 标题 | 压缩与轨迹 parity 绿 |
| 4 | Workspace、索引、检索、文件工具、审批（含 V1.5 命名工作区，Python 先行） | 文件安全、审批、命名创建场景绿 |
| 5 | MCP（stdio/http） | 连接/发现/审批/超时/重连绿 |
| 6 | Skills 与剩余能力（标题、会话工作区绑定） | 全端点覆盖 |
| 7 | 全量验收、隔离与恢复测试、双 E2E、Parity 表更新 | 第 19 节 15 条全部满足 |

## 16. 风险

| 风险 | 影响 | 缓解 |
|---|---|---|
| 事件序号/提交顺序处理错误 | 丢事件、UI 卡死 | 行锁分配 seq + 补偿补读 + 专项测试 |
| SseEmitter 与虚拟线程/Tomcat 超时配置 | 长连接被断 | 全局 async timeout -1、nginx 关缓冲、心跳 |
| MySQL FULLTEXT 语义差异 | 搜索行为不一致 | 固定语料验收 + 记录 K-02 |
| token 估算差异 | 压缩时机不同 | 阈值/顺序对齐，数值不比对 |
| 契约漂移 | 两端悄悄分叉 | 快照 + 黑盒测试 + 变更流程 |
| 版本兼容（Boot/Spring AI/MCP） | 构建失败 | Phase 1 实测 dependency:tree，只升不改契约 |
| arm64→amd64 构建 | 服务器起不来 | 固定 platform，镜像 inspect 验收 |
| 容器内目录选择不可用 | 无法选工作区 | 见 17.1（需你拍板） |
| 42 端点工作量大 | 拖延 | 纵向切片，每阶段可验收 |

## 17. 需要你拍板 / 我的判断

### 17.1 已定：容器里的工作区改成"命名创建"

不再给 UI 加"手输绝对路径"：那等于把容器路径暴露给用户，还会让 UI 与两端各自理解路径规则。

定案（详见 10.14.1）：

1. Compose 给每个后端挂一个工作区根（`workspace-python` / `workspace-java`），容器内路径固定 `/workspaces`，通过 `WORKSPACE_ROOT` 注入。
2. 用户只输入**工作区名字**；服务端在其专属子目录下创建：`<WORKSPACE_ROOT>/<WORKSPACE_USER>/<name>`，`WORKSPACE_USER` 默认 `default`。
3. 原生目录选择（`POST /workspaces/pick`）保留，宿主机开发继续可用；容器里调用仍是 409，UI 不再依赖它。
4. 这是 V1.4 之后的第一项契约扩展（v1.1），两端同时实现，排在 parity 全绿之后。

### 17.2 我已替你做的判断（可推翻）

1. 单 Maven 模块，靠 package 约束依赖方向（8.1）。
2. 模型流式链路自研 Provider，Spring AI 只做对照实验（7.3）。
3. 事件用 per-run `seq` 作为 SSE id（10.4）。
4. 检索用 MySQL FULLTEXT + 短查询 `LIKE` 回退，差异记为 K-02（7.4）。
5. Phase 0 只出 1 份设计 + 1 份计划 + 契约骨架，学习文档随代码（14）。
6. Mock Model 用零依赖 Python 标准库实现（13.2）。
7. `service`/`version` 字段两端返回相同值，实例区分靠 UI 运行时标签而非 API 字段（10.5 之外的部署约定）。

### 17.3 设计评审后补定的判断

1. **不设第三个统一网关**：两个 UI 容器各自带 nginx；单端口无法在"仅同源路径"约束下区分两个后端（12.2）。
2. **parity 比对按事件分档**：token 敏感事件只比结构与相对位置，不比 token 数值与触发步（9.4），并新增估算器对照实验。
3. **两个后端镜像都带 node（Java 另带 python3）**：否则 MCP stdio 场景无法在两端跑同一套测试（12.7）。
4. **Java 复刻 Python 的启动期模型校验**：缺模型配置直接启动失败，而不是等到请求期（10.9、12.6）。
5. **Phase 3 拆成 3a/3b**：先打通 Run/SSE/工具，再补压缩/轨迹/档案（15）。
6. **计划按检查点组织，不写日历估算**：本设计不掌握你的时间预算，实施计划以"可验收切片"为单位，由你决定节奏。
7. **模型端点定为外部 OpenAI-compatible 服务**：Compose 只需出网与密钥注入，服务器不装模型运行时（12.6）。
8. **容器内工作区走命名创建**：`<WORKSPACE_ROOT>/<WORKSPACE_USER>/<name>`，作为 V1.5 契约扩展在 parity 之后两端同做（10.14.1、17.1）。

## 附录 A：错误码清单

以 Python `ErrorCode` 为准，共 68 个（含已定义未使用），Java 侧 `enum ErrorCode` 全量复刻，默认 HTTP 映射按 Python 调用点整理成表，未显式指定的走 500。重点码：`INVALID_REQUEST/NOT_FOUND/UNAUTHORIZED/VALIDATION_ERROR/SESSION_NOT_FOUND/RUN_NOT_FOUND/RUN_CONFLICT/INVALID_RUN_TRANSITION/TOOL_* /WORKSPACE_* /MCP_* /SKILL_* /MODEL_* /COMPACTION_* /CONTEXT_* /HARNESS_STEP_LIMIT/PROCESS_INTERRUPTED/INTERNAL`。

## 附录 B：留给实现者的自由

- Java 内部类名、包内分层细节、Mapper XML 的组织方式。
- 是否用 `record` 还是普通类承载领域对象（建议 record + 显式构造）。
- 日志字段名与格式（只要不改变对外协议）。
- 测试用例的拆分粒度。
- MySQL 索引的额外优化（不得改变语义）。
