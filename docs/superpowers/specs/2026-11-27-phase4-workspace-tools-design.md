# Phase 4 设计：工作区 / 文件工具 / 审批（含 V1.5 命名工作区）

- 状态：待评审（尚未写实施计划）
- 日期：2026-11-27
- 前置：Phase 3 已完成（3a + 3b-1 + 3b-2）

## 1. 范围

1. **工作区**：`workspaces` 表 + 绑定端点（`POST /sessions/{id}/workspace`）、文件树与全文检索（FTS）。
2. **本地文件工具**：`file_list / file_read / file_write / file_search / file_delete`，由 Runtime 自己执行（区别于 Phase 3 的 remote 工具）。
3. **审批流**：危险操作（写、删、覆盖）先进入 `waiting_for_approval`，通过 `POST /runs/{id}/tool-calls/{call_id}/approve|reject` 决定；新增 3 个事件，事件总数 24 → 27。
4. **V1.5 命名工作区**：目录布局 `<WORKSPACE_ROOT>/<WORKSPACE_USER>/<name>`，解决多人共用一台机器时同名目录互相覆盖。

## 2. 关键设计点

### 2.1 目录与隔离

- 根目录来自 `PRISM_AGENT_KIT_WORKSPACE_ROOT`（默认 `~/prism-workspaces`）。
- 会话绑定后，所有文件工具的相对路径都相对于该会话工作区解析。
- **路径穿越防护**：解析后 `Path.resolve()` 必须仍在工作区根内（含符号链接解析后）；越界 → `WORKSPACE_PATH_DENIED`(422)。
- 单文件读写上限 2 MB；目录列举上限 500 条。

### 2.2 审批状态机

```
waiting_for_tool → waiting_for_approval → (approve) → running → …
                                       → (reject)  → waiting_for_tool（工具闭合为 rejected）
```

- 审批超时 300s → 工具 `expired`，事件 `tool.expired`，Run 回队。
- 审批决定只允许一次；重复提交 → 409 `TOOL_APPROVAL_CONFLICT`。
- 审批事件：`tool.approval_required`、`tool.approved`、`tool.rejected`（24→27，与 `contracts/events` 对齐）。

### 2.3 文件工具语义

| 工具 | 参数 | 审批 |
|---|---|---|
| `file_list` | `path`, `depth≤3` | 否 |
| `file_read` | `path`, `max_bytes` | 否 |
| `file_search` | `query`, `glob?` | 否 |
| `file_write` | `path`, `content`, `mode=create/overwrite` | **是** |
| `file_delete` | `path`（只能删文件） | **是** |

- 写入采用“临时文件 + 原子 rename”，避免半截文件。
- 所有工具返回 `{ok, data|error}`，错误码与 Python 现有实现一致。

### 2.4 迁移与兼容

- Python：新增 Alembic 迁移（`workspaces`、`tool_calls.approval_state`、`approval_decided_at`）。
- Java：新增 Flyway `V5`，字段与状态枚举同名同义。
- 既有会话未绑定工作区时，文件工具直接返回 `WORKSPACE_NOT_BOUND`(409)，不隐式创建。

## 3. 实施顺序（建议）

1. Python + UI：workspaces 表/端点、文件树、FTS、文件工具、审批流；
2. 契约快照 v1.3（新增 workspace 端点与 3 个事件）+ 双端契约测试；
3. Java：V5 迁移、工作区绑定、文件工具（容器内独立实现，**不调用 Python**）、审批状态机；
4. E2E：绑定 → 写文件（审批）→ 读回 → 删除（审批）→ 拒绝路径。

## 4. 需要你确认

1. **命名工作区命名规则**：`<WORKSPACE_ROOT>/<WORKSPACE_USER>/<name>`，`WORKSPACE_USER` 默认取容器 env（如 `default`）；同名冲突时返回 409 还是自动加后缀？
2. **Phase 4 是否两端同时做**，还是按原计划 Python + UI 先落地、Java 跟随？（我的建议：先 Python + UI，拿到可用的产品体验，再用同一批契约测试约束 Java。）
3. **删除语义**：`file_delete` 只删文件、还是允许删空目录？（建议只删文件，目录删除留给后续。）
4. **审批默认策略**：写/删一律审批，还是按路径可配置白名单？（建议默认一律审批，白名单留作后续。）

## 5. 非目标

- 不做多人并发写锁、不做版本历史、不做云存储同步。
- 不做工作区级权限模型（单用户本地优先）。
