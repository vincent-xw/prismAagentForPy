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

### 2.2 权限档位（取代逐工具审批）

工作区上有一个 `permission_mode` 开关，三档：

| 档位 | 允许的操作 |
|---|---|
| `read_only`（仅可查看） | 只能 `file_list / file_read / file_search`；写、删直接拒绝 `WORKSPACE_READ_ONLY`(403)，**不进入审批** |
| `workspace_write`（工作区内修改） | 允许在工作区根内写/删；越界仍 `WORKSPACE_PATH_DENIED` |
| `full_access`（完全权限） | 允许工作区外路径；**UI 侧必须二次弹窗确认**后才能保存该档位 |

- **不做自动审查**：不引入模型/规则审查，档位即策略；越权直接返回错误码，不产生等待态。
- 与 V1.4 的差异（记为 **K-09**）：V1.4 的逐工具 `waiting_for_approval` + `approve/reject` 端点与 3 个审批事件，本实现**不启用**；事件总数保持 24。契约测试不得断言审批事件；parity 文档记录为有意差异。
- 切档必须显式：`PATCH /workspaces/{id}` 带 `permission_mode`；`full_access` 的二次确认只在 UI 层，API 不做"确认票据"（避免多一套状态）。

### 2.3 文件工具语义

| 工具 | 参数 | 审批 |
|---|---|---|
| `file_list` | `path`, `depth≤3` | 否 |
| `file_read` | `path`, `max_bytes` | 否 |
| `file_search` | `query`, `glob?` | 否 |
| `file_write` | `path`, `content`, `mode=create/overwrite` | 受档位约束（`read_only` 拒绝） |
| `file_delete` | `path`（文件或**空目录**；非空目录拒绝 `WORKSPACE_DIR_NOT_EMPTY`） | 受档位约束（`read_only` 拒绝） |

- 写入采用“临时文件 + 原子 rename”，避免半截文件。
- 所有工具返回 `{ok, data|error}`，错误码与 Python 现有实现一致。

### 2.4 迁移与兼容

- Python：新增 Alembic 迁移（`workspaces`、`tool_calls.approval_state`、`approval_decided_at`）。
- Java：新增 Flyway `V5`，字段与状态枚举同名同义。
- 既有会话未绑定工作区时，文件工具直接返回 `WORKSPACE_NOT_BOUND`(409)，不隐式创建。

## 3. 实施顺序（建议）

1. 契约先行：workspace 端点（含 `permission_mode`）+ 快照 v1.3（事件数保持 24）+ 双端契约测试；
2. Python 与 Java **同时实现**：表/迁移、工作区绑定、文件工具（各自容器内独立实现，**不调用对端**）、档位校验；
3. UI：工作区文件树、档位开关、`full_access` 二次确认弹窗；
4. E2E：绑定 → `read_only` 写被拒 → 切 `workspace_write` 写成功 → 读回 → 删空目录 → 非空目录拒绝 → `full_access` 流程。

## 4. 已确认的决定

1. **命名冲突**：自动加后缀 `name-2`、`name-3`…（`POST /workspaces` 返回最终目录名；不返回 409）。
2. **实施顺序**：Python + Java **同时做**，UI 跟随同一批契约。
3. **删除语义**：`file_delete` 允许删文件与**空目录**；非空目录返回 `WORKSPACE_DIR_NOT_EMPTY`。
4. **权限模型**：工作区级三档开关（`read_only` / `workspace_write` / `full_access`）；`full_access` 在 UI 二次弹窗确认；**不做自动审查**；不启用 V1.4 的逐工具审批（K-09）。

## 5. 非目标

- 不做多人并发写锁、不做版本历史、不做云存储同步。
- 不实现 V1.4 的逐工具审批（`tool.approval_required/approved/rejected`），见 K-09。
- 不做工作区级权限模型（单用户本地优先）。
