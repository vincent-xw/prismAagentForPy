# Phase 4 实施计划：工作区 / 文件工具 / 权限档位

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让两端都具备工作区绑定、文件工具与工作区级权限档位（仅可查看 / 工作区内修改 / 完全权限），并让 UI 能浏览文件树、切换档位（`full_access` 二次确认）。

**Architecture:** Python 与 Java 各自实现同一套 `/workspaces` 契约与文件工具（各自容器内执行，互不调用）；权限判断集中在各自执行器的一处策略函数，路径解析后必须校验是否落在工作区根内。

**Tech Stack:** Python 3.12 + FastAPI + SQLAlchemy/Alembic；Java 21 + Spring Boot + MyBatis-Plus/Flyway；Vue 3 + zod；契约 pytest+httpx。

**Spec:** `docs/superpowers/specs/2026-11-27-phase4-workspace-tools-design.md`

## Global Constraints

- 权限档位枚举固定为 `read_only | workspace_write | full_access`；默认 `workspace_write`。
- `read_only` 下写/删一律 `WORKSPACE_READ_ONLY`(403)，**不进入审批等待**；不实现 V1.4 逐工具审批（K-09），事件总数保持 24。
- `full_access` 的二次确认**只在 UI**；API 只接受该枚举值，不做确认票据。
- 命名工作区目录：`<WORKSPACE_ROOT>/<WORKSPACE_USER>/<name>`；同名自动加后缀 `name-2`、`name-3`…，`POST /workspaces` 返回最终 `label` 与 `root_path`。
- 路径穿越：`Path.resolve()` 后必须仍在工作区根内，否则 `WORKSPACE_PATH_DENIED`(422)；`full_access` 例外（允许根外，但仍拒绝非法路径）。
- 单文件读/写上限 2 MB；目录列举上限 500；`file_delete` 允许文件与**空目录**，非空目录 `WORKSPACE_DIR_NOT_EMPTY`(409)。
- 两端错误码、字段名、状态码必须一致；新增端点写入契约快照 v1.3。

## Review Focus

1. **路径穿越**：`../../etc/passwd`、绝对路径、指向根外的符号链接 —— 必须 `WORKSPACE_PATH_DENIED`，在 Task 2/5 的测试里钉住。
2. **read_only 泄漏**：只读档下 `file_write`/`file_delete` 仍能成功（漏判） —— Task 2/5。
3. **非空目录删除**：`file_delete` 递归删除用户数据 —— Task 2/5。
4. **同名目录覆盖**：并发/重复创建把别人的工作区内容覆盖 —— Task 1/4 的后缀测试。
5. **档位切回只读后旧权限仍生效**（缓存导致） —— Task 2/5 的“切换后立即生效”测试。

---

## 文件结构

```text
backend/
├── migrations/versions/20261127_0009_workspace_permissions.py     # 新增
├── src/prism_agent_kit/
│   ├── core/models.py                     # Workspace.permission_mode/name/user
│   ├── db/{models,mappers,repositories/workspaces}.py
│   ├── application/workspace_service.py   # 命名/后缀/档位
│   ├── tools/workspace_tools.py           # + file_delete、档位校验
│   └── api/{schemas,routes/workspaces}.py # permission_mode 字段、PATCH
└── tests/{api,application,tools}/...      # 新增用例

backend-java/src/main/
├── resources/db/migration/V5__workspaces.sql
├── java/com/prism/agent/{core/domain,persistence,application,api}/...
└── test/java/com/prism/agent/{api,application,tools}/...

ui/src/features/workspace/…                # 文件树 + 档位开关
tests/contract/test_workspaces.py          # 新增（两端共用）
contracts/openapi/prism-agent-api.yaml     # v1.3
```

---

### Task 1: Python 工作区表与命名/档位

**Files:**
- Create: `backend/migrations/versions/20261127_0009_workspace_permissions.py`
- Modify: `backend/src/prism_agent_kit/core/models.py`、`db/models.py`、`db/mappers.py`、`db/repositories/workspaces.py`
- Modify: `backend/src/prism_agent_kit/application/workspace_service.py`
- Modify: `backend/src/prism_agent_kit/api/schemas.py`、`api/routes/workspaces.py`
- Test: `backend/tests/application/test_workspace_permissions.py`

**Interfaces:**
- Produces: `Workspace.permission_mode: str`（默认 `workspace_write`）、`Workspace.name: str | None`、`Workspace.user: str | None`
- Produces: `WorkspaceService.create(path: str | None, name: str | None, label: str | None, permission_mode: str) -> Workspace`；`name` 非空时按 `<root>/<user>/<name>` 生成目录并自动加后缀
- Produces: `WorkspaceService.update_permission(workspace_id: str, mode: str) -> Workspace`
- Produces: `PATCH /workspaces/{id}` 接受 `{permission_mode}`；`WorkspaceView` 增加 `permission_mode`、`name`
- Produces: `POST /sessions/{sessionId}/workspace` 接受 `{workspace_id}`，写 `sessions.workspace_id` 并返回 SessionView（绑定后文件工具才有根）

- [ ] **Step 1: 写失败测试**

```python
async def test_named_workspace_gets_suffix_on_conflict(service, tmp_path, monkeypatch):
    monkeypatch.setenv("PRISM_AGENT_KIT_WORKSPACE_ROOT", str(tmp_path))
    first = await service.create(name="demo", path=None, label=None, permission_mode="workspace_write")
    second = await service.create(name="demo", path=None, label=None, permission_mode="workspace_write")
    assert first.root_path != second.root_path
    assert second.root_path.endswith("demo-2")

async def test_invalid_permission_mode_is_422(service):
    with pytest.raises(AgentKitError) as error:
        await service.create(name="x", path=None, label=None, permission_mode="root")
    assert error.value.http_status == 422
```

- [ ] **Step 2: 运行确认失败**：`cd backend && uv run pytest tests/application/test_workspace_permissions.py -q`（`permission_mode` 不存在）
- [ ] **Step 3: 实现**：迁移加 3 列（`permission_mode` 默认 `workspace_write`、`name`、`user` 可空）；服务内 `_ensure_named_dir` 用 `mkdir(parents=True, exist_ok=False)` 循环加后缀；校验枚举白名单；`PATCH` 只允许改档位与 label。
- [ ] **Step 4: 运行确认通过** + `uv run alembic upgrade head && uv run alembic downgrade -1 && uv run alembic upgrade head`
- [ ] **Step 5: 提交** `git commit -am "feat(backend): 工作区命名目录与权限档位"`

---

### Task 2: Python 文件工具与档位执行

**Files:**
- Modify: `backend/src/prism_agent_kit/tools/workspace_tools.py`
- Modify: `backend/src/prism_agent_kit/tools/executor.py`（如权限判断在此层）
- Test: `backend/tests/tools/test_workspace_permissions.py`

**Interfaces:**
- Consumes: `Workspace.permission_mode`（Task 1）
- Produces: `file_delete(path)` 工具（文件或空目录）
- Produces: 统一策略 `ensure_allowed(role: Literal["read","write"], workspace, target: Path) -> None`：`read_only` 拒绝写/删；`workspace_write` 要求 `target.resolve()` 在根内；`full_access` 跳过根内校验

- [ ] **Step 1: 写失败测试**

```python
async def test_read_only_blocks_write(tool_ctx_read_only):
    with pytest.raises(ToolExecutionError) as error:
        await execute("file_write", {"path": "a.txt", "content": "x", "mode": "create"}, tool_ctx_read_only)
    assert error.value.code == "WORKSPACE_READ_ONLY"

async def test_workspace_write_blocks_escape(tool_ctx_write):
    with pytest.raises(ToolExecutionError) as error:
        await execute("file_read", {"path": "../../etc/passwd"}, tool_ctx_write)
    assert error.value.code == "WORKSPACE_PATH_DENIED"

async def test_delete_non_empty_dir_rejected(tool_ctx_write):
    ...  # 建 a/b.txt 后 delete("a") → WORKSPACE_DIR_NOT_EMPTY
```

- [ ] **Step 2: 运行确认失败**
- [ ] **Step 3: 实现**：所有工具入口先过 `ensure_allowed`；`file_delete` 用 `unlink()` 或 `rmdir()`（非空捕获 `OSError` → 409）；缓存不参与判断（每次读工作区记录）
- [ ] **Step 4: 运行确认通过**：`uv run pytest tests/tools -q`
- [ ] **Step 5: 提交** `git commit -am "feat(backend): 文件工具按权限档位执行并支持删除空目录"`

---

### Task 3: 契约 v1.3 与双端用例

**Files:**
- Create: `tests/contract/test_workspaces.py`
- Modify: `contracts/openapi/prism-agent-api.yaml`（脚本重导出）

**Interfaces:**
- Produces: 用例 `test_create_named_workspace_and_suffix`、`test_permission_mode_default_and_patch`、`test_bind_workspace_to_session`、`test_read_only_rejects_write`、`test_delete_empty_dir_only`

- [ ] **Step 1: 写用例**（对 Python 先跑，Java 未实现时红）
- [ ] **Step 2: 运行确认失败**
- [ ] **Step 3: 导出快照** `bash scripts/export-openapi.sh`，确认新增 `permission_mode` 字段与 `PATCH /workspaces/{id}`，事件数仍 24
- [ ] **Step 4: 运行确认通过**（Python）
- [ ] **Step 5: 提交** `git commit -am "test(contract): 工作区与文件工具 v1.3 用例"`

---

### Task 4: Java 工作区表与 API

**Files:**
- Create: `backend-java/src/main/resources/db/migration/V5__workspaces.sql`
- Create: `backend-java/src/main/java/com/prism/agent/{core/domain/Workspace.java,persistence/entity/WorkspaceEntity.java,persistence/mapper/WorkspaceMapper.java,persistence/repository/WorkspaceRepository.java,persistence/repository/MyBatisWorkspaceRepository.java,application/service/WorkspaceService.java,api/dto/{WorkspaceRequest,WorkspaceView,WorkspaceTreeView}.java,api/controller/WorkspaceController.java}`
- Test: `backend-java/src/test/java/com/prism/agent/api/WorkspaceApiTest.java`

**Interfaces:**
- Produces: `Workspace(id, rootPath, label, permissionMode, name, user, active, indexStatus, fileCount, indexedAt, createdAt, updatedAt)`
- Produces: `GET /workspaces`、`POST /workspaces`、`GET /workspaces/{id}`、`PATCH /workspaces/{id}`、`POST /workspaces/{id}/activate`、`DELETE /workspaces/{id}`、`GET /workspaces/{id}/tree?path=`、`POST /sessions/{sessionId}/workspace`
- Produces: 与 Task 1 相同的命名/后缀规则与枚举校验（错误码 `WORKSPACE_PATH_INVALID`/`VALIDATION_ERROR` 与 Python 对齐）

- [ ] **Step 1: 写失败测试**：创建（自动后缀）、PATCH 档位、默认档位、tree 一级列表
- [ ] **Step 2: 运行确认失败**（404）
- [ ] **Step 3: 实现**：V5 建表（`root_path` 唯一、`permission_mode` 枚举字符串）；服务用 `Files.createDirectories` + 后缀循环；tree 只列一层、上限 500
- [ ] **Step 4: 运行确认通过**：`./mvnw -Dtest=WorkspaceApiTest test`
- [ ] **Step 5: 提交** `git commit -am "feat(java): 工作区 API 与权限档位"`

---

### Task 5: Java 文件工具与档位执行

**Files:**
- Create: `backend-java/src/main/java/com/prism/agent/tools/WorkspaceToolExecutor.java`、`WorkspaceFileTools.java`
- Modify: `backend-java/src/main/java/com/prism/agent/tools/ToolRegistry.java`（注册本地工具）
- Modify: 引擎工具派发点（本地工具同步执行，不走 remote 等待）
- Test: `backend-java/src/test/java/com/prism/agent/tools/WorkspaceToolPermissionsTest.java`

**Interfaces:**
- Produces: 工具 `file_list/file_read/file_search/file_write/file_delete`，`ExecutionMode.LOCAL`
- Produces: `ensureAllowed(Workspace workspace, Path target, boolean write)` 抛 `ApiException(WORKSPACE_READ_ONLY 403 / WORKSPACE_PATH_DENIED 422)`

- [ ] **Step 1: 写失败测试**：只读拒写、越界拒绝（`../../etc/passwd`）、删空目录成功、删非空目录 409、切换档位后立即生效
- [ ] **Step 2: 运行确认失败**
- [ ] **Step 3: 实现**：`root.resolve()` 前缀比较用 `Path.startsWith`；写用临时文件 + `ATOMIC_MOVE`；读上限 2 MB
- [ ] **Step 4: 运行确认通过**：`./mvnw verify`
- [ ] **Step 5: 提交** `git commit -am "feat(java): 本地文件工具与权限档位执行"`

---

### Task 6: UI 工作区与档位开关

**Files:**
- Modify: `ui/src/lib/api/contracts.ts`（`permission_mode`、workspace DTO）
- Modify: `ui/src/lib/api/client.ts`（workspaces 方法）
- Create/Modify: `ui/src/features/workspace/{WorkspacePanel.vue,workspace.ts}`
- Test: `ui/src/features/workspace/workspace.test.ts`

**Interfaces:**
- Produces: 文件树（一级懒加载）、档位下拉、`full_access` 选择时弹确认框，确认后才 `PATCH`
- Produces: `workspaceSchema` 含 `permission_mode` 与 `name`，zod 校验缺字段即失败

- [ ] **Step 1: 写失败测试**：schema 缺 `permission_mode` 报错；选择 `full_access` 未确认不调用 PATCH
- [ ] **Step 2: 运行确认失败**：`cd ui && pnpm test --run src/features/workspace`
- [ ] **Step 3: 实现**
- [ ] **Step 4: 运行确认通过**：`pnpm check && pnpm test && pnpm build`
- [ ] **Step 5: 提交** `git commit -am "feat(ui): 工作区文件树与权限档位开关"`

---

### Task 7: 双端验证与收尾

**Files:**
- Modify: `docs/compatibility/feature-parity.md`、`AGENTS.md`（权限档位与 K-09）

- [ ] **Step 1: 双端跑契约** `pytest test_workspaces.py -q`（8000/8001）
- [ ] **Step 2: E2E**：绑定命名工作区 → 只读写被拒 → 切 `workspace_write` 写成功 → 读回 → 删空目录 → 删非空目录 409
- [ ] **Step 3: 重建镜像并部署** `docker compose build backend-python backend-java ui-python ui-java`（UI 一次构建、两容器同 tag）
- [ ] **Step 4: 全量门槛** Python `pytest/ruff/mypy`、Java `verify`、UI `check/test/build`
- [ ] **Step 5: 提交** `git commit -am "docs: Phase 4 工作区与权限档位收尾"`

---

## 自检记录

- **Spec 覆盖**：§2.1（目录/后缀/穿越）→ Task 1/2/4/5；§2.2（三档权限、K-09）→ Task 1/2/4/5；§2.3（文件工具、删空目录）→ Task 2/5；§3（双端并行 + UI 档位 + 会话绑定）→ Task 1/3/4/5/6；§6（契约 v1.3）→ Task 3。
- **Review Focus 对应**：穿越→Task 2/5；read_only 泄漏→Task 2/5；非空目录→Task 2/5；同名覆盖→Task 1/4；切档即时生效→Task 2/5。
- **类型一致**：`permission_mode` 三端同名；`WorkspaceView` 字段两端一致；错误码 `WORKSPACE_READ_ONLY/WORKSPACE_PATH_DENIED/WORKSPACE_DIR_NOT_EMPTY` 在 2/5 使用同一拼写。
- **比例**：7 个任务，未展开实现体；纯策略函数与 API 形状已固定。
