# PrismAgentKit 工作区与文件工具设计（迁移第二部分）

- 状态：待评审（已过一轮独立 builder 评审）
- 日期：2026-11-23
- 关联：[Python Agent Core 设计](2026-11-22-python-agent-core-design.md)、[Core UI 设计](2026-11-22-core-ui-design.md)

## 0. 已确认的交互结论

- 第二部分范围选 **A：Workspace + 本地文件工具（最小版）**，不选 MCP Client，也不选可用性收尾。
- **写入文件纳入本期**。
- **前端交互一并交付**（工作区页 + 写入审批）。

## 1. 背景与意图

第一部分交付了 Python Agent Core 与 Core UI：Run、SSE、恢复、远端工具回填都通了，但 Agent 实际上"没有手"——内置工具只有 `echo` 与 `wait_for_host` 两个测试件，模型拿不到任何外部信息，也产不出文件。用户在和它对话时，只能得到模型自身的知识。

第二部分要让 Agent 在**用户明确指定的本地目录**里干活：列目录、读文本文件、全文检索、写文件；并且用户能在 UI 上选择目录、浏览文件、审批每一次写入。这是后续 MCP、RAG、多 Agent 的前置地基：没有工作区边界，任何工具都没有可操作的上下文，也没有可约束的路径范围。

## 2. 目标

### 2.1 功能目标

1. 绑定 / 切换本地工作区，并把绑定关系持久化；同一时刻只有一个活跃工作区，但**已开始的 Run 固定在自己创建时的工作区**。
2. 对工作区建立全文索引（SQLite FTS5），支持中英文正文检索并返回命中片段。
3. 提供 4 个工具：`file_list`、`file_read`、`file_search`、`file_write`。
4. `file_write` 必须经过用户审批后执行；未审批不得落盘。
5. UI：工作区页（选择/切换、索引状态、文件树、文本预览、搜索）+ 会话页的写入审批卡片。

### 2.2 工程目标

- 不新增运行时依赖：FTS5 与 `sqlite3` 来自标准库，目录选择用系统命令。
- 所有文件系统 I/O 通过 `asyncio.to_thread` 执行，不在事件循环里做阻塞调用。
- 现有 HTTP / SSE 契约只做增量扩展，不改变既有字段语义。
- 继续满足 `ruff check`、`ruff format --check`、`mypy src`、`pytest` 与 `pnpm check`、`pnpm test`、`pnpm build`。

## 3. 非目标

- 删除、移动、重命名文件；执行 shell / 命令；git 操作。
- 向量检索、embedding、外部索引服务、RAG 记忆（A/B/C 那套）。
- 多工作区并行使用（同一时刻仍只有一个活跃工作区）、工作区成员与 ACL。
- 文件系统监听（watch）与自动增量同步（写后单文件重索引除外）。
- 二进制、PDF、XLSX 解析与预览；图片预览。
- 远端 / SSH / 容器内工作区。
- MCP Client、多 Agent、Workflow、设备工具。
- 模型档案 UI、SQLite 加密密钥库。

## 4. 反目标

- 让模型绕过审批直接改盘，或用"模型自己判断已获同意"代替真实审批。
- 用字符串拼接处理路径，留下 `..` 与符号链接逃逸口子。
- 把索引进度塞进 `RunEvent` / SSE（索引不属于任何 Run）。
- 在 FastAPI 路由里直接写遍历、写盘、建索引逻辑。
- 用不带上限的全表 `LIKE` 冒充全文检索，或用字符近似蒙混中文分词。
- 让"当前活跃工作区"在执行中途改变一个 Run 的写入目标。

## 5. 约束

- SQLite 是唯一数据库，结构变更必须带 Alembic 迁移；FTS5 虚拟表需手写 `op.execute`。
- 单进程 asyncio、无独立 Worker（沿用现有 `RunWorker`）。
- 沿用既有不变量：同一 Session 单活跃 Run；终止 Run 必须闭合 ToolCall；模型可见历史必须能由持久化数据重建。
- 第一目标平台是 macOS（`osascript`），Linux `zenity`、Windows PowerShell 作尽力支持；不支持时回退手输路径。
- 配置只经 `pydantic-settings` 从环境变量或 `.env` 读取。
- 工具输出必须 JSON 可序列化并通过 Pydantic 校验；工具异常不透传正文。

## 6. 方案选择

### 6.1 第二部分做什么（已决策）

| 方案 | 内容 | 取舍 |
|---|---|---|
| A（选中） | Workspace + 本地文件工具 | 补"Agent 有可操作上下文"的地基；后续 MCP 工具同样受工作区路径约束 |
| B | MCP Client | 纯后端、不动领域模型，但要推翻"不引入 MCP SDK"约束，且没有工作区时第三方工具同样无处落地 |
| C | 可用性收尾 | 一周量级，但不新增 Agent 能力 |

选 A 的理由：当前最大缺口不是工具数量，而是"有没有可被授权的操作范围"。A 是 B 的前置约束，也是最小可用的真实能力。

### 6.2 A 内部的备选与决策

| 决策点 | 备选 | 选择与理由 |
|---|---|---|
| 检索方式 | FTS5 / 向量 / 纯 LIKE | **FTS5 `trigram`**：零新依赖，`bm25` 与 `snippet` 开箱可用。实测 SQLite 3.53 下 `MATCH` 对 2 字中文返回空，因此**查询 < 3 字符时回退到 `instr(content, ?) > 0` 的受限扫描**（limit 50） |
| 索引粒度 | 整文件 / 分块 | **整文件**：最小版够用，`snippet` 直接可用；分块留给向量阶段 |
| 目录选择 | 浏览器目录 API / 手输路径 / 后端原生对话框 | **后端原生对话框**（`osascript` / `zenity` / PowerShell），失败回退手输。浏览器拿不到真实绝对路径，手输单独使用体验差 |
| 写入安全 | 直接写 / 写前审批 | **写前审批**：写入是本项目第一次让模型改用户磁盘，必须先有闸门；审批可用配置关闭（默认开启） |
| 工作区作用域 | 全局当前活跃 / Run 级固定 | **Run 级固定**：Run 创建时记录 `workspace_id`，其全部工具调用、审批执行、写后重索引都用它。否则"预览看的是 A 目录、审批时写入 B 目录"是真实安全事故 |
| 活跃工作区数量 | 单活跃 / 多活跃 | **单活跃**：最小版心智简单；Run 固定后，切换只影响新 Run |

## 7. 总体架构

```text
UI(工作区页/审批卡片)
   │ HTTP / SSE（同一 API Token）
api/routes/workspaces.py ──┐
api/routes/runs.py(审批)   │
                           ▼
application/workspace_service.py（绑定、树、读、搜索、索引调度）
application/workspace_indexer.py（遍历 → 过滤 → 写 FTS）
application/index_tasks.py（WorkspaceIndexTaskManager：单飞、生命周期、崩溃复位）
application/tool_approval_service.py（审批决策 → 执行工具 → 闭合轮次）
tools/workspace_tools.py（4 个 ToolDefinition，handler 调 workspace_service）
core/engine.py（审批闸门：遇到 requires_approval 的本地工具不执行，转 waiting_for_approval）
   │
   ├── db/repositories/workspaces.py
   ├── db/repositories/workspace_documents.py
   └── SQLite: workspaces / workspace_documents(FTS5) / runs / tool_calls / run_events
```

职责边界：

- 路由只做鉴权、参数校验、DTO 转换。
- 遍历、读写、索引事务全部在 `application/`；工具 handler 仅做输入到服务调用的映射。
- 审批执行复用 `LocalToolExecutor`，不复制工具执行逻辑；结果落库复用抽出的共享记录器（见 §11.4）。
- `SimpleAgentEngine` 只增加"识别并挂起需审批调用"的分支，不搬走既有本地/远端执行逻辑。

## 8. 数据模型

### 8.1 `workspaces`

| 列 | 类型 | 说明 |
|---|---|---|
| `id` | String(36) PK | UUID |
| `root_path` | Text NOT NULL | 规范化后的绝对路径（`realpath`），唯一 |
| `label` | String(255) NULL | 展示名，默认取目录名 |
| `is_active` | Integer NOT NULL DEFAULT 0 | 0/1 |
| `index_status` | String(16) NOT NULL | `idle` / `indexing` / `ready` / `failed` |
| `index_error` | Text NULL | 失败原因（已脱敏，不含文件内容） |
| `file_count` | Integer NOT NULL DEFAULT 0 | 成功入索引的文件数 |
| `indexed_at` | DateTime NULL | 上次索引完成时间 |
| `created_at` / `updated_at` | DateTime | |

约束：`UNIQUE(root_path)`；`CREATE UNIQUE INDEX ux_workspaces_single_active ON workspaces(is_active) WHERE is_active = 1`。

### 8.2 `workspace_documents`（FTS5 虚拟表）

```sql
CREATE VIRTUAL TABLE workspace_documents USING fts5(
  workspace_id UNINDEXED,
  rel_path     UNINDEXED,
  content,
  tokenize = 'trigram'
);
```

- 每文件一行，`rel_path` 为相对工作区根的 POSIX 路径（统一 `/`）。
- `UNINDEXED` 列不参与检索但可 `WHERE` 过滤与取回；删除按 `DELETE FROM workspace_documents WHERE workspace_id = ?`。
- 检索：`SELECT rel_path, snippet(workspace_documents, 2, '[', ']', '…', 16), bm25(workspace_documents) FROM workspace_documents WHERE workspace_documents MATCH ? AND workspace_id = ? ORDER BY bm25(workspace_documents) LIMIT ?`。
- 降级路径：查询去空白后长度 < 3 时改用 `SELECT rel_path FROM workspace_documents WHERE workspace_id = ? AND instr(content, ?) > 0 LIMIT ?`，不做排序。
- 启动自检：试建 FTS5 `trigram` 表失败时，健康接口暴露 `workspace_fts: unsupported`，相关接口返回 `WORKSPACE_INDEX_UNAVAILABLE`，不静默降级为"搜不到"。

### 8.3 枚举扩展

```python
class RunStatus:      # 新增
    WAITING_FOR_APPROVAL = "waiting_for_approval"

class ToolCallStatus: # 新增
    AWAITING_APPROVAL = "awaiting_approval"

class EventType:      # 新增
    RUN_WAITING_FOR_APPROVAL = "run.waiting_for_approval"
    TOOL_APPROVAL_REQUIRED   = "tool.approval_required"
    TOOL_APPROVED            = "tool.approved"
    TOOL_REJECTED            = "tool.rejected"
```

### 8.4 迁移 `20261123_0003_workspace` 的注意点

1. 建 `workspaces` 与部分唯一索引。
2. `runs` 增加可空列 `workspace_id`（`ForeignKey("workspaces.id", ondelete="SET NULL")`）。SQLite 用 `op.add_column` 即可。
3. `op.execute` 建 FTS5 虚拟表；`downgrade` 里 `DROP TABLE workspace_documents`。
4. **重建 `runs` 的部分唯一索引**：`ux_runs_one_active_per_session` 的 `sqlite_where` 必须加入 `'waiting_for_approval'`，否则审批中的 Run 会让同会话无法开新 Run。SQLite 不支持原地改索引条件，需 drop + create。
5. `runs.status` / `tool_calls.status` 是 `String`，无需改列，只需枚举与状态机同步。

### 8.5 Run 与工作区绑定

- `runs.workspace_id` 可空：Run 创建时取当前活跃工作区（无则 NULL）。
- 工具解析路径时**只用 Run 的 `workspace_id`**，不看"当前活跃"；`workspace_id` 为 NULL 时工具返回 `WORKSPACE_NOT_BOUND`。
- 审批执行、写后重索引同样按该 Run 的 `workspace_id` 定位。
- `RunView` 增加只读字段 `workspace_id`（可空），UI 显示"本次会话绑定的目录"；切换活跃工作区不影响在跑/等待审批的 Run，只影响之后新建的 Run。

## 9. 工作区服务

### 9.1 路径安全（唯一入口）

所有路径都经一个函数收敛：

```python
def resolve_in_workspace(root: str, rel: str) -> Path:
    # 1) 拒绝 NUL 字节与空串（空串视为根）
    # 2) (root / rel).resolve(strict=False) 后再 realpath，取真实路径
    # 3) 真实路径必须等于 root 或位于 root + os.sep 之下，否则 WORKSPACE_PATH_OUTSIDE
```

- 检查发生在 `realpath` 之后，符号链接逃逸一并覆盖；跨平台用 `os.path.commonpath` 语义而非字符串前缀。
- 写路径额外要求：不许落在 `.git/` 下；目标父目录允许自动创建（仅限工作区内）。

### 9.2 绑定流程

1. `POST /workspaces/pick`：按平台执行原生目录选择命令（`osascript -e 'POSIX path of (choose folder ...)'` 等），设 **120 秒超时**；用户取消（`osascript` 退出码 -128）、无 GUI、命令缺失、超时统一返回 409 `WORKSPACE_PICKER_UNAVAILABLE`，`details.reason = cancelled | unsupported | timeout`；UI 收到后**静默切换到手输路径**，不弹错误。
2. `POST /workspaces {path, label?}`：校验为绝对路径、存在、是目录、可读；拒绝与应用数据目录（`agent.db` 所在目录）重叠的根；`realpath` 去重后落库并激活。
3. 激活：同一事务内把旧活跃置 0、新活跃置 1，并触发后台索引。
4. 切换工作区不删除旧索引；再次激活复用已有索引并触发一次重建（保证不陈旧）。

### 9.3 目录树与读文件

- `tree(path)`：`readdir` 按需读取（不落库），跳过排除目录（`.git`、`node_modules`、`dist`、`build`、`.dart_tool`、`coverage`），目录优先、字典序；返回 `name/type/size/modified_at`。
- `read_file(path, max_bytes)`：先 `lstat` 拒绝非普通文件与超限；读前 4096 字节若含 NUL 判定二进制并拒绝（`WORKSPACE_FILE_BINARY`）；按 UTF-8 严格解码，失败返回 `WORKSPACE_FILE_ENCODING`；超 `max_bytes` 截断并标记 `truncated`。

### 9.4 索引

- 触发：绑定/激活、手动重建、写文件成功后（单文件）。
- 遍历规则沿用上游：排除目录同上；排除扩展名 `.png .jpg .jpeg .gif .webp .ico .pdf .zip .gz .7z .mp4 .mov .woff .woff2`；排除文件名 `.env`、`.env.*`、`*.sqlite`、`*.db`；跳过符号链接文件与大于 1 MiB 的文件。
- 规模上限：单工作区 20,000 个文件、索引正文累计 200 MiB，超出即停止遍历并在 `index_error` 记录 `truncated_at_limit`。
- 状态机：`idle → indexing → ready | failed`；同一工作区同时只允许一个索引任务（单飞 + 状态检查），重复触发返回当前状态。
- 事务：按 200 行一批写入，批次之间让出事件循环；重建先删后插，失败时保留旧数据并在 `index_error` 说明（避免"半索引"被当成完整）。
- 写后增量：写入成功后只重索引该文件（删除旧行 + 插入新行 + 更新 `file_count`）。
- **任务归属**：`application/index_tasks.py` 的 `WorkspaceIndexTaskManager` 由 `ApplicationContainer` 持有，提供 `submit(workspace_id, mode=full|file)`；内部登记 `asyncio.Task` 并单飞；容器 `stop()` 时统一 cancel 并 await（避免关停泄漏）。**启动时**把遗留的 `indexing` 一律重置为 `failed` 且 `index_error = "process_interrupted"`，需要用户重新点"重建索引"。

## 10. 工具契约

| 工具 | 输入 | 输出 | 执行 |
|---|---|---|---|
| `file_list` | `path: str = "."` | `entries: [{name, type: file|dir, size?, modified_at?}]` | local，15s |
| `file_read` | `path: str`, `max_bytes: int = 65536`（≤200000） | `content: str, truncated: bool, size: int` | local，15s |
| `file_search` | `query: str`（1–200 字）, `limit: int = 20`（≤50）, `path_prefix?: str` | `hits: [{path, snippet}]` | local，20s |
| `file_write` | `path: str`, `content: str`, `mode: overwrite|append|create` | `path, bytes, created: bool` | local，30s，**需审批** |

- 4 个工具常驻注册（`ToolRegistry` 不支持运行时增删）；执行时按 `run.workspace_id` 取工作区根，未绑定返回 `WORKSPACE_NOT_BOUND`；工具描述写明"需要用户先绑定工作区"。
- `ToolDefinition` 增加 `requires_approval: bool = False`。
- `file_write` 的 `create` 在文件已存在时失败；`overwrite` 整体替换；`append` 追加。
- 工具描述要写明"写入需要用户审批，审批在界面完成"，避免模型自行宣称"我已获授权"。

## 11. 写入审批

### 11.1 状态机

```text
Run:        running ──→ waiting_for_approval ──→ queued ──→ running …
                              ├──────────────→ waiting_for_tool（混合轮次）
                              └──────────────→ failed / cancelled
ToolCall:   pending ──→ awaiting_approval ──→ running ──→ succeeded
                                   ├────────→ failed(TOOL_REJECTED)
                                   └────────→ failed(TOOL_APPROVAL_TIMEOUT)
```

`core/state.py` 的 `_ALLOWED_TRANSITIONS` 增补：`RUNNING → WAITING_FOR_APPROVAL`、`WAITING_FOR_APPROVAL → {QUEUED, WAITING_FOR_TOOL, FAILED, CANCELLED}`。

### 11.2 一轮内的处理顺序与闭合规则

同一 assistant 轮可能混合三类调用：无需审批的本地工具、需审批写入、远端工具。顺序固定：

1. 先执行所有无需审批的本地工具（现状逻辑不变）。
2. 若存在需审批调用：全部置 `awaiting_approval`，`expires_at = now + 审批超时`，Run 转 `waiting_for_approval`，发 `run.waiting_for_approval`（payload 含全部待审批 `call_ids`）。引擎返回 `EngineOutcome(kind="waiting_for_approval")`。
3. 用户逐个决策（见 11.4）。每次决策后在同一事务里重算该 Run 的全部调用：
   - 仍有 `awaiting_approval` → 保持 `waiting_for_approval`；
   - 无 `awaiting_approval` 但有未完成的**远端**调用 → Run 转 `waiting_for_tool` 并发 `run.waiting_for_tool`（混合轮次在此衔接）；
   - 全部终态 → Run 转 `queued` 并发 `run.requeued`。
4. 远端结果全部回填（现有 `ToolResultService`）沿用同一"全部终态 → queued"判断。
5. Worker 重新 claim 后 `resume` 调模型；此时本轮结果已全在历史中，满足闭合不变量。

不允许把部分结果喂给模型。

### 11.3 事件与 SSE

审批相关事件都是持久 `RunEvent`，随现有 SSE 下发：

| 事件 | payload |
|---|---|
| `run.waiting_for_approval` | `{call_ids: [..]}` |
| `tool.approval_required` | `{call_id, tool_name, path, mode, bytes}` |
| `tool.approved` | `{call_id}` |
| `tool.rejected` | `{call_id, reason?}` |

- **预览按需获取**：事件只携带路径/模式/字节数，不含文件内容。UI 渲染审批卡片时请求 `GET /runs/{run_id}/tool-calls/{call_id}/preview`，由审批服务在 `asyncio.to_thread` 里生成：文件不存在返回 `exists=false, diff=null`；存在则返回**行级统一 diff 的前 200 行**（超出标 `truncated`），总长上限 20 KB。diff 只用于展示，不参与执行；不让 `core/engine.py` 直接读盘。
- **正文脱敏**：`file_write` 的正文不进入 `tool.requested` 事件——该事件对 `file_write` 的 `input` 脱敏为 `{path, mode, bytes, input_digest}`。正文仍保存在 `tool_calls.input` 与模型可见历史的 assistant 消息里（那是模型自己的输出，必须保留才能重建历史）；UI 的 `ToolCallCard` 对 `file_write` 只渲染路径/模式/字节数。

### 11.4 审批接口

`POST /runs/{run_id}/tool-calls/{call_id}/approval`

```json
{ "decision": "approve" | "reject", "reason": "可选，≤200 字" }
```

- 响应：`{ "call": ToolCallView, "run": RunView }`，前端直接更新卡片与横幅，无需再拉一次。
- 校验顺序：Run 存在 → 调用存在 → 调用状态为 `awaiting_approval`（终态按幂等返回当前对象；其他状态 409 `RUN_CONFLICT`）→ 未过期（否则 409 `TOOL_CALL_EXPIRED`）。
- 服务级 `asyncio.Lock` 串行化；事务内落状态、写事件、按 11.2 重算 Run 状态。
- 批准时用 `LocalToolExecutor` 执行：先置 `running`，再调 handler；结果写入复用**抽出的共享记录器**（把 `SimpleAgentEngine._record_tool_result` 提取为 `ToolResultRecorder`，引擎与审批服务共用，保证 tool 消息、事件、`ToolCall` 终态写法一致）。
- **取消信号**：审批执行前向 `RunCancellationRegistry.register(run_id)` 重新登记，执行结束 `unregister`；执行前与执行中检查 `cancel.is_set()` 与 `run.cancel_requested_at`。与 `RunService.cancel` 在同一服务锁内串行化；若调用已被取消，审批返回 409。

### 11.5 过期

- 配置 `WORKSPACE_TOOL_APPROVAL_TIMEOUT_SECONDS`（默认 1800）。
- 复用 `RunWorker.sweep_expired_tool_calls`：候选状态增加 `awaiting_approval`，Run 状态判断扩展为 `waiting_for_tool` 或 `waiting_for_approval`；过期则 `failed(TOOL_APPROVAL_TIMEOUT)`，全部终态后按 11.2 规则 requeue。

### 11.6 取消与进程恢复

- 取消：现有 `close_open_calls` 覆盖 `awaiting_approval`（置 `cancelled`），Run 转 `cancelled`，事件照旧；若写入正在执行，协作式取消在下一个检查点生效，执行器标记 `RUN_CANCELLED`。
- 重启：`recover_interrupted_runs` 只处理 `running`，**不得**把 `waiting_for_approval` 判为中断——它没有进程内任务，恢复后继续等待用户决策，直到过期或被取消。

## 12. HTTP 接口（新增，前缀 `/api/v1`）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/workspaces` | 列表 + `active_id` |
| POST | `/workspaces/pick` | 打开原生目录选择，返回 `{path}`（不落库） |
| POST | `/workspaces` | 绑定并激活 `{path, label?}` |
| GET | `/workspaces/{id}` | 单个工作区与索引状态 |
| POST | `/workspaces/{id}/activate` | 切换活跃 |
| POST | `/workspaces/{id}/reindex` | 触发重建（幂等） |
| DELETE | `/workspaces/{id}` | 解除绑定并删除其索引行；活跃工作区需先切换 |
| GET | `/workspaces/{id}/tree?path=` | 目录项 |
| GET | `/workspaces/{id}/file?path=` | 文本内容（`max_bytes` 可选） |
| GET | `/workspaces/{id}/search?q=&limit=&path_prefix=` | 检索命中 |
| GET | `/runs/{run_id}/tool-calls/{call_id}/preview` | 写入预览 `{path, mode, bytes, exists, diff, truncated}`（仅 `awaiting_approval` 可读） |
| POST | `/runs/{run_id}/tool-calls/{call_id}/approval` | 审批写入 |

响应新增 `WorkspaceView`：`{id, root_path, label, is_active, index_status, index_error, file_count, indexed_at}`。
`RunView` 增加 `workspace_id`；`RunView.status` 与 `ToolCallView.status` 增加取值——**前端契约同步更新**。

## 13. UI 设计

### 13.1 导航与路由

- `src/app/modules.ts` 增加 `{ id: 'workspace', label: '工作区', path: '/workspace' }`。
- `router.ts` 增加 `/workspace` → `WorkspacePage.vue`。
- `AppShell` 的导航自动渲染新模块（现有实现按 `modules` 枚举）。

### 13.2 工作区页（`src/features/workspace/`）

三块布局，桌面优先，窄窗纵向堆叠：

1. **当前工作区卡片**：路径、状态徽标（未绑定/索引中/就绪 N 个文件/失败原因）、`选择目录` `重建索引` 按钮；未绑定时整页提示"先选择一个工作区"。
2. **文件树**：从根懒加载目录（点开才请求 `tree`），目录优先排序；点击文件在预览区打开。
3. **预览 / 搜索**：默认显示所选文件文本（等宽字体、保留换行、超限提示）；顶部搜索框输入后切到命中列表，点击命中项打开对应文件并高亮首个片段。

交互细节：索引中每 1.5s 轮询一次 `GET /workspaces/{id}` 直到 `ready|failed`；切换工作区后清空预览与搜索状态。

### 13.3 写入审批（会话页）

- `RunInspector` 增加"待审批"区：按 `tool.approval_required` 事件渲染卡片，先显示 `path`、`mode`、`bytes`，卡片展开时请求 `.../preview` 拿 diff 与 `exists`；底部 `允许写入` / `拒绝` 两个按钮，提交期间禁用并显示处理中；响应里的 `call`、`run` 直接更新本地状态。
- `SessionPage` 顶部横幅：当活跃 Run 为 `waiting_for_approval` 时显示"等待你确认写入（N）"，点击打开 Run 详情。
- `ToolCallCard` 与状态标签补齐 `awaiting_approval`（待审批）、`TOOL_REJECTED`（已拒绝）文案；`file_write` 不渲染正文。
- 刷新恢复：审批卡片完全由 `GET /runs/{id}` 的 `status` + SSE 事件重放（`tool.approval_required` / `tool.approved` / `tool.rejected`）重建；**不新增** `RunView.tool_calls` 字段。

### 13.4 契约校验

- `contracts.ts` 增加 `workspaceSchema`、`workspaceListSchema`、tree/file/search/approval 响应 schema，扩展 run/toolCall 的 `status` 枚举、`RunView.workspace_id` 与四个新事件类型；全部 `zod` 运行时校验。
- `client.ts` 增加对应方法（`listWorkspaces`、`pickWorkspace`、`createWorkspace`、`activateWorkspace`、`reindexWorkspace`、`getTree`、`getFile`、`search`、`decideApproval`）。

## 14. 配置与错误码

新增配置（`core/config.py`，环境变量 `PRISM_AGENT_KIT_` 前缀）：

| 键 | 默认 | 说明 |
|---|---|---|
| `WORKSPACE_INDEX_MAX_FILE_BYTES` | 1048576 | 单文件索引上限 |
| `WORKSPACE_INDEX_MAX_FILES` | 20000 | 单工作区文件数上限 |
| `WORKSPACE_TOOL_APPROVAL_TIMEOUT_SECONDS` | 1800 | 审批超时 |
| `WORKSPACE_REQUIRE_WRITE_APPROVAL` | true | 关闭后写入无需审批（仅限受信本地环境，默认不关） |

新增错误码：`WORKSPACE_NOT_FOUND`、`WORKSPACE_NOT_BOUND`、`WORKSPACE_PATH_INVALID`、`WORKSPACE_PATH_OUTSIDE`、`WORKSPACE_FILE_NOT_FOUND`、`WORKSPACE_FILE_TOO_LARGE`、`WORKSPACE_FILE_BINARY`、`WORKSPACE_FILE_ENCODING`、`WORKSPACE_INDEX_UNAVAILABLE`、`WORKSPACE_INDEX_FAILED`、`WORKSPACE_PICKER_UNAVAILABLE`、`TOOL_REJECTED`、`TOOL_APPROVAL_TIMEOUT`。

## 15. 安全边界

- 一切路径先 `realpath` 再做包含性判断；写入额外禁止 `.git/`；`path` 不许出现 NUL。
- 索引排除 `.env`、`.env.*`、`*.db`、`*.sqlite` 与二进制、超限文件，避免把凭据与数据库写进 FTS 表。
- 工作区根不得与应用数据目录重叠（否则索引会吃掉 `agent.db`）。
- 日志与事件只记录路径、字节数、状态，不记录文件正文（`tool.requested` 对 `file_write` 脱敏，见 11.3）。
- 新接口全部走现有 API Token 鉴权；未鉴权请求保持 401 语义。
- 审批是唯一写入通道；模型不能通过 `file_write` 之外的途径改盘。
- 拒绝原因、diff 预览等展示内容按纯文本渲染，不解析 HTML。

## 16. 测试与验收

后端：

- 单测：路径逃逸（`..`、绝对路径、符号链接）、排除规则、1 MiB 上限、二进制检测、UTF-8 失败、扩展名大小写。
- FTS：3 字以上中文/英文命中、2 字中文走回退、`snippet` 片段、`bm25` 排序、重建后旧行清空。
- 状态机：`running → waiting_for_approval → queued`、`waiting_for_approval → waiting_for_tool`（混合轮次）；非法迁移被拒；部分结果不得触发 requeue。
- 审批：批准执行并落结果、拒绝落 `TOOL_REJECTED`、重复审批幂等、过期 409、跨 Run 审批 404、取消闭合 `awaiting_approval`、审批执行中取消。
- Run 固定工作区：审批期间切换活跃工作区，写入仍落在 Run 绑定的目录。
- 恢复：重启后 `waiting_for_approval` 保持等待；遗留 `indexing` 被复位为 `failed`。
- 迁移：空库 `upgrade head` 与已有库升级均通过，FTS5 虚拟表可建可删。

UI：

- `zod` 契约对真实响应的解析用例（含新状态与新事件）。
- 工作区页：未绑定/索引中/就绪/失败四态渲染；目录懒加载；搜索命中打开文件。
- 审批卡片：允许/拒绝调用正确接口、提交中禁用、失败提示。

验收脚本（手测清单）：绑定空目录 → 索引 ready → 让模型"读 README 并总结" → 检索中文 → 让模型写文件 → 界面审批 → 文件落盘 → 再问模型确认。

## 17. 交付规模与阶段

项目级变更，按四阶段实施（详细任务留给实施计划）：

1. **数据与索引**：枚举/状态机/迁移、`workspaces` 与 FTS 表、仓储、路径安全、索引器与任务管理器。
2. **工具与审批**：4 个工具、审批服务、`ToolResultRecorder` 抽取、引擎闸门、混合轮次衔接、过期与恢复路径。
3. **HTTP**：11 个接口 + DTO + 错误映射 + 健康自检。
4. **UI 与验收**：工作区页、审批卡片、契约、测试、验收脚本。

工作量估计：后端约 1,200–1,600 行（含测试），UI 约 800–1,000 行（含测试）。

## 18. 留给构建者的空间

- diff 预览的具体实现（建议 `difflib.unified_diff`，统一 3 行上下文，限 200 行 / 20 KB）。
- 搜索结果排序是否叠加路径前缀权重（当前只用 `bm25`）。
- 工作区页文件树的虚拟滚动（文件数超过 ~2,000 时再加）。
- 是否在工作区页展示"最近索引时间"到分钟级（建议展示）。
- 索引批次大小（建议 200 行/批，可按实测调整）。

---

## 附：与既有实现的改动点清单（供评审核对）

- `core/enums.py`：2 个状态、4 个事件类型。
- `core/state.py`：状态迁移表。
- `core/errors.py`：13 个错误码。
- `core/config.py`：4 个配置项。
- `core/engine.py`：`EngineOutcome.kind` 增加 `waiting_for_approval`；本地工具循环遇到 `requires_approval` 时挂起；`_record_tool_result` 抽成共享 `ToolResultRecorder`。
- `db/models.py`：`workspaces` 表、`runs.workspace_id` 列、`runs` 部分唯一索引条件更新。
- `db/repositories/`：新增 `workspaces.py`、`workspace_documents.py`；`tool_calls.py` 增加 `await_call`/`start_after_approval`，`close_open_calls` 覆盖新状态；`runs.py` 的 `_ACTIVE_STATUSES` 加入 `waiting_for_approval`；`tool_calls.list_expired` 覆盖 `awaiting_approval`。
- `application/`：新增 `workspace_service.py`、`workspace_indexer.py`、`index_tasks.py`、`tool_approval_service.py`；`container.py` 装配与关停；`run_worker.py` 过期扫描与恢复范围；`run_service.py` 创建 Run 时写入 `workspace_id`。
- `tools/`：新增 `workspace_tools.py`；`contracts.py` 的 `ToolDefinition` 增加 `requires_approval`。
- `api/`：新增 `routes/workspaces.py`、`routes/runs.py` 审批路由、`schemas.py` 新 DTO（含 `RunView.workspace_id`）、`errors.py` 映射。
- `migrations/versions/20261123_0003_workspace.py`。
- `ui/src/lib/api/contracts.ts`、`client.ts`、`app/modules.ts`、`app/router.ts`、`features/workspace/*`、`features/runs/RunInspector.vue`、`features/runs/ToolCallCard.vue`、`features/sessions/SessionPage.vue`。
