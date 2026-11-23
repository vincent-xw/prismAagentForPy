# 工作区与文件工具 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 Python 版 Agent 在用户绑定的本地工作区内列目录、读文本、全文检索并（经用户审批）写文件，UI 提供工作区页与审批卡片。

**Architecture:** 新增 `workspaces` 表与 FTS5 `workspace_documents` 虚拟表；`WorkspaceService` 统一路径校验、目录树、读文件与检索，`WorkspaceIndexer` + `WorkspaceIndexTaskManager` 负责后台索引；`file_write` 通过新增的 `waiting_for_approval` 运行状态挂起，由 `ToolApprovalService` 在用户决策后执行并闭合该轮。

**Tech Stack:** Python 3.12、FastAPI、SQLAlchemy 2 Async + aiosqlite、Alembic、SQLite FTS5（trigram）、Pydantic v2；Vue 3 + TypeScript + zod + Vitest。

**Spec:** `docs/superpowers/specs/2026-11-23-workspace-file-tools-design.md`

## Global Constraints

- 不新增运行时依赖：FTS5 / `sqlite3` 来自标准库；目录选择用系统命令（`osascript` / `zenity` / PowerShell）。
- SQLite 是唯一数据库；任何结构变更必须带 Alembic 迁移；FTS5 虚拟表手写 `op.execute`。
- 所有文件系统 I/O 走 `asyncio.to_thread`，不得在异步请求路径阻塞事件循环。
- 配置只经 `pydantic-settings`（`PRISM_AGENT_KIT_` 前缀）从环境变量或 `.env` 读取。
- 对外接口前缀 `/api/v1`，全部复用现有 API Token 鉴权。
- 状态事实以 SQLite 为准；终止 Run 必须闭合 ToolCall；模型可见历史必须可重建；不允许把部分工具结果喂给模型。
- 后端函数与复杂逻辑写中文注释，标识符用英文；默认不做字段兜底。
- 质量门槛：`ruff check`、`ruff format --check`、`mypy src`、`pytest` 全部通过；UI 提交前 `pnpm check`、`pnpm test`、`pnpm build` 通过。
- UI 面向桌面窗口，窄窗只做合理堆叠，不做移动端专门适配。
- 审批超时默认 1800 秒；单文件索引上限 1 MiB；单工作区文件上限 20,000。

## Review Focus

1. **2–3 字中文检索**：`trigram` 对少于 3 字的中文 `MATCH` 返回空——必须走 `instr(content, ?)` 回退并真的返回命中，而不是静默空结果（拥有任务：Task 4）。
2. **路径穿越与符号链接逃逸**：`../`、绝对路径、指向根外的 symlink 必须被拒绝（读、写、索引三处都不许漏）（拥有任务：Task 5、Task 8）。
3. **审批期间切换活跃工作区**：写入必须落在 Run 创建时绑定的目录，而不是新的活跃目录（拥有任务：Task 11）。
4. **同一轮混合远端工具与写入**：必须能闭合到 `waiting_for_tool` 或 `queued`，不得卡死或重复 requeue（拥有任务：Task 11）。
5. **索引进程中途退出**：重启后不得永远停在"索引中"，要复位为 `failed` 并允许用户重建（拥有任务：Task 7）。

---

### Task 1: 枚举、状态机、错误码与配置扩展

**Files:**
- Modify: `backend/src/prism_agent_kit/core/enums.py`
- Modify: `backend/src/prism_agent_kit/core/state.py`
- Modify: `backend/src/prism_agent_kit/core/errors.py`
- Modify: `backend/src/prism_agent_kit/core/config.py`
- Test: `backend/tests/core/test_state.py`, `backend/tests/core/test_config.py`

**Interfaces:**
- Produces: `RunStatus.WAITING_FOR_APPROVAL`、`ToolCallStatus.AWAITING_APPROVAL`、`IndexStatus{IDLE,INDEXING,READY,FAILED}`、`EventType.{RUN_WAITING_FOR_APPROVAL,TOOL_APPROVAL_REQUIRED,TOOL_APPROVED,TOOL_REJECTED}`、13 个新 `ErrorCode`、`Settings.{workspace_index_max_file_bytes, workspace_index_max_files, workspace_tool_approval_timeout_seconds, workspace_require_write_approval}`。

- [ ] **Step 1: 写失败测试**

在 `backend/tests/core/test_state.py` 追加：

```python
@pytest.mark.parametrize(
    "current,target",
    [
        (RunStatus.RUNNING, RunStatus.WAITING_FOR_APPROVAL),
        (RunStatus.WAITING_FOR_APPROVAL, RunStatus.QUEUED),
        (RunStatus.WAITING_FOR_APPROVAL, RunStatus.WAITING_FOR_TOOL),
        (RunStatus.WAITING_FOR_APPROVAL, RunStatus.CANCELLED),
    ],
)
def test_approval_transitions_allowed(current: RunStatus, target: RunStatus) -> None:
    ensure_run_transition(current, target)


def test_approval_cannot_go_back_to_running() -> None:
    with pytest.raises(AgentKitError) as exc:
        ensure_run_transition(RunStatus.WAITING_FOR_APPROVAL, RunStatus.RUNNING)
    assert exc.value.code is ErrorCode.INVALID_RUN_TRANSITION
```

在 `backend/tests/core/test_config.py` 追加：

```python
def test_workspace_defaults() -> None:
    settings = Settings()
    assert settings.workspace_index_max_file_bytes == 1_048_576
    assert settings.workspace_index_max_files == 20_000
    assert settings.workspace_tool_approval_timeout_seconds == 1_800
    assert settings.workspace_require_write_approval is True
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && uv run pytest tests/core/test_state.py tests/core/test_config.py -q`
Expected: FAIL（`RunStatus` 无 `WAITING_FOR_APPROVAL`、`Settings` 无 `workspace_*`）

- [ ] **Step 3: 实现**

- `core/enums.py`：`RunStatus` 加 `WAITING_FOR_APPROVAL = "waiting_for_approval"`；`ToolCallStatus` 加 `AWAITING_APPROVAL = "awaiting_approval"`；新增 `class IndexStatus(StrEnum)`（4 个值）；`EventType` 加 4 个事件。
- `core/state.py`：`RUNNING` 允许 `{..., WAITING_FOR_APPROVAL}`；新增键 `WAITING_FOR_APPROVAL: frozenset({QUEUED, WAITING_FOR_TOOL, FAILED, CANCELLED})`。
- `core/errors.py`：追加 `WORKSPACE_NOT_FOUND`、`WORKSPACE_NOT_BOUND`、`WORKSPACE_PATH_INVALID`、`WORKSPACE_PATH_OUTSIDE`、`WORKSPACE_FILE_NOT_FOUND`、`WORKSPACE_FILE_TOO_LARGE`、`WORKSPACE_FILE_BINARY`、`WORKSPACE_FILE_ENCODING`、`WORKSPACE_INDEX_UNAVAILABLE`、`WORKSPACE_INDEX_FAILED`、`WORKSPACE_PICKER_UNAVAILABLE`、`TOOL_REJECTED`、`TOOL_APPROVAL_TIMEOUT`。
- `core/config.py`：4 个字段，`workspace_index_max_file_bytes: int = 1_048_576`、`workspace_index_max_files: int = 20_000`、`workspace_tool_approval_timeout_seconds: int = 1_800`、`workspace_require_write_approval: bool = True`。

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && uv run pytest tests/core/test_state.py tests/core/test_config.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/prism_agent_kit/core/enums.py backend/src/prism_agent_kit/core/state.py backend/src/prism_agent_kit/core/errors.py backend/src/prism_agent_kit/core/config.py backend/tests/core/test_state.py backend/tests/core/test_config.py
git commit -m "feat(core): 增加审批状态、工作区错误码与配置项"
```

---

### Task 2: 数据模型与迁移

**Files:**
- Modify: `backend/src/prism_agent_kit/db/models.py`
- Create: `backend/migrations/versions/20261123_0003_workspace.py`
- Test: `backend/tests/db/test_migration.py`

**Interfaces:**
- Produces: `WorkspaceRow`（表 `workspaces`）；`RunRow.workspace_id`（可空 FK `workspaces.id`，`ondelete=SET NULL`）；重建后的 `ux_runs_one_active_per_session`（含 `waiting_for_approval`）；FTS5 表 `workspace_documents`。

- [ ] **Step 1: 写失败测试**

在 `backend/tests/db/test_migration.py` 追加：

```python
def test_workspace_schema_applied(migrated_database_path: Path) -> None:
    with sqlite3.connect(migrated_database_path) as conn:
        workspace_cols = {row[1] for row in conn.execute("PRAGMA table_info(workspaces)")}
        assert {
            "id", "root_path", "label", "is_active", "index_status",
            "index_error", "file_count", "indexed_at", "created_at", "updated_at",
        } <= workspace_cols
        run_cols = {row[1] for row in conn.execute("PRAGMA table_info(runs)")}
        assert "workspace_id" in run_cols
        index_sql = conn.execute(
            "SELECT sql FROM sqlite_master WHERE name = 'ux_runs_one_active_per_session'"
        ).fetchone()[0]
        assert "waiting_for_approval" in index_sql
        fts_sql = conn.execute(
            "SELECT sql FROM sqlite_master WHERE name = 'workspace_documents'"
        ).fetchone()[0]
        assert "trigram" in fts_sql
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && uv run pytest tests/db/test_migration.py -q`
Expected: FAIL（no such table: workspaces 或列不存在）

- [ ] **Step 3: 实现**

- `db/models.py`：新增 `WorkspaceRow`（字段按 spec §8.1；`is_active` 用 `Integer`、`index_status` 用 `String(16)`），并在 `RunRow` 加 `workspace_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("workspaces.id", ondelete="SET NULL"))`；把 `RunRow.__table_args__` 中的 `sqlite_where` 改为 `text("status IN ('queued', 'running', 'waiting_for_tool', 'waiting_for_approval')")`。
- 迁移文件 `20261123_0003_workspace.py`（`revision = "20261123_0003"`，`down_revision = "20261122_0002"`）：
  1. `op.create_table("workspaces", ...)` 全部列 + `sa.PrimaryKeyConstraint("id", name="pk_workspaces")` + `sa.UniqueConstraint("root_path", name="ux_workspaces_root_path")`。
  2. `op.create_index("ux_workspaces_single_active", "workspaces", ["is_active"], unique=True, sqlite_where=sa.text("is_active = 1"))`。
  3. `op.add_column("runs", sa.Column("workspace_id", sa.String(length=36), nullable=True))`（`op.create_foreign_key` 在 SQLite 需 batch 模式；改用 `op.batch_alter_table("runs")` 包裹 add_column + create_foreign_key）。
  4. `op.drop_index("ux_runs_one_active_per_session", table_name="runs")` 后按新条件重建。
  5. `op.execute("CREATE VIRTUAL TABLE workspace_documents USING fts5(workspace_id UNINDEXED, rel_path UNINDEXED, content, tokenize = 'trigram')")`。
  `downgrade()` 逆序：drop 虚拟表、还原索引条件、drop column、drop workspaces。

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && uv run pytest tests/db/test_migration.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/prism_agent_kit/db/models.py backend/migrations/versions/20261123_0003_workspace.py backend/tests/db/test_migration.py
git commit -m "feat(db): 工作区表、Run 绑定字段与 FTS5 文档表迁移"
```

---

### Task 3: Workspace 领域模型、映射与仓储

**Files:**
- Create: `backend/src/prism_agent_kit/core/workspace.py`
- Create: `backend/src/prism_agent_kit/db/repositories/workspaces.py`
- Modify: `backend/src/prism_agent_kit/db/mappers.py`
- Modify: `backend/src/prism_agent_kit/db/uow.py`
- Test: `backend/tests/db/test_workspace_repository.py`

**Interfaces:**
- Produces：`Workspace`（Pydantic：`id, root_path, label, is_active, index_status: IndexStatus, index_error, file_count, indexed_at, created_at, updated_at`）；`WorkspaceRepository`：`create(workspace) -> Workspace`、`get(workspace_id) -> Workspace`、`get_active() -> Workspace | None`、`list_all() -> list[Workspace]`、`activate(workspace_id) -> Workspace`、`update_index_state(workspace_id, *, status, file_count=None, error=None, indexed_at=None) -> Workspace`、`delete(workspace_id) -> None`；`UnitOfWork.workspaces`。

- [ ] **Step 1: 写失败测试**

```python
async def test_activate_keeps_single_active(uow_factory: UnitOfWorkFactory, tmp_path: Path) -> None:
    async with uow_factory() as uow:
        first = await uow.workspaces.create(Workspace(root_path=str(tmp_path / "a")))
        second = await uow.workspaces.create(Workspace(root_path=str(tmp_path / "b")))
        await uow.workspaces.activate(first.id)
        await uow.commit()
    async with uow_factory() as uow:
        await uow.workspaces.activate(second.id)
        await uow.commit()
    async with uow_factory() as uow:
        active = await uow.workspaces.get_active()
        assert active is not None and active.id == second.id
        assert all(not item.is_active for item in await uow.workspaces.list_all() if item.id == first.id)


async def test_delete_active_workspace_rejected(uow_factory: UnitOfWorkFactory, tmp_path: Path) -> None:
    async with uow_factory() as uow:
        workspace = await uow.workspaces.create(Workspace(root_path=str(tmp_path / "a")))
        await uow.workspaces.activate(workspace.id)
        await uow.commit()
    async with uow_factory() as uow:
        with pytest.raises(AgentKitError) as exc:
            await uow.workspaces.delete(workspace.id)
        assert exc.value.code is ErrorCode.RUN_CONFLICT
        assert exc.value.details["reason"] == "workspace_active"
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && uv run pytest tests/db/test_workspace_repository.py -q`
Expected: FAIL（`Workspace` 不存在）

- [ ] **Step 3: 实现**

- `core/workspace.py`：`Workspace` 领域模型（`index_status: IndexStatus = IndexStatus.IDLE`，时间字段用 `utc_now`）。
- `db/mappers.py`：`workspace_to_row` / `workspace_to_domain`（`is_active` 在领域层用 `bool`，存储用 0/1）。
- `db/repositories/workspaces.py`：`activate` 先 `UPDATE workspaces SET is_active = 0 WHERE is_active = 1`，再置目标为 1；`get` 未命中抛 `WORKSPACE_NOT_FOUND`(404)；`delete` 对活跃工作区抛 `RUN_CONFLICT`(409)。
- `db/uow.py`：构造 `WorkspaceRepository(session)` 并暴露为 `self.workspaces`。

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && uv run pytest tests/db/test_workspace_repository.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/prism_agent_kit/core/workspace.py backend/src/prism_agent_kit/db/repositories/workspaces.py backend/src/prism_agent_kit/db/mappers.py backend/src/prism_agent_kit/db/uow.py backend/tests/db/test_workspace_repository.py
git commit -m "feat(db): 工作区领域模型与仓储"
```

---

### Task 4: FTS 文档仓储（含中文回退）

**Files:**
- Create: `backend/src/prism_agent_kit/db/repositories/workspace_documents.py`
- Modify: `backend/src/prism_agent_kit/db/uow.py`
- Test: `backend/tests/db/test_workspace_documents.py`

**Interfaces:**
- Produces：`IndexedDocument(path: str, content: str)`、`SearchHit(path: str, snippet: str)`、`ensure_fts_supported(connection) -> bool`；`WorkspaceDocumentRepository`：`replace_all(workspace_id, documents) -> int`、`upsert(workspace_id, document) -> None`、`delete_file(workspace_id, path) -> None`、`delete_workspace(workspace_id) -> None`、`count(workspace_id) -> int`、`search(workspace_id, query, *, limit, path_prefix) -> list[SearchHit]`；`UnitOfWork.workspace_documents`。

- [ ] **Step 1: 写失败测试**

```python
async def test_search_hits_chinese_and_two_char_fallback(uow_factory: UnitOfWorkFactory) -> None:
    async with uow_factory() as uow:
        await uow.workspace_documents.replace_all(
            "ws-1",
            [
                IndexedDocument(path="docs/guide.md", content="这是一个关于工作区检索的中文测试文档"),
                IndexedDocument(path="docs/other.md", content="unrelated english text"),
            ],
        )
        await uow.commit()
    async with uow_factory() as uow:
        long_hits = await uow.workspace_documents.search("ws-1", "工作区检索", limit=10, path_prefix=None)
        assert [hit.path for hit in long_hits] == ["docs/guide.md"]
        assert "工作区" in long_hits[0].snippet
        short_hits = await uow.workspace_documents.search("ws-1", "检索", limit=10, path_prefix=None)
        assert [hit.path for hit in short_hits] == ["docs/guide.md"]


async def test_prefix_filter_and_delete_workspace(uow_factory: UnitOfWorkFactory) -> None:
    async with uow_factory() as uow:
        await uow.workspace_documents.replace_all("ws-1", [
            IndexedDocument(path="a/x.md", content="alpha keyword"),
            IndexedDocument(path="b/y.md", content="alpha keyword"),
        ])
        await uow.commit()
    async with uow_factory() as uow:
        hits = await uow.workspace_documents.search("ws-1", "alpha", limit=10, path_prefix="b/")
        assert [hit.path for hit in hits] == ["b/y.md"]
        await uow.workspace_documents.delete_workspace("ws-1")
        await uow.commit()
    async with uow_factory() as uow:
        assert await uow.workspace_documents.count("ws-1") == 0
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && uv run pytest tests/db/test_workspace_documents.py -q`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现**

- 用 `sqlalchemy.text` 执行 FTS5 语句（含 `workspace_id` 过滤）。
- `search`：`len(query.strip()) >= 3` 走 `MATCH` + `bm25` 排序 + `snippet(workspace_documents, 2, '[', ']', '…', 16)`；否则走 `instr(content, :q) > 0`，用 Python 截取命中前后各 40 字构造 `snippet`（前后加 `…`）。`path_prefix` 用 `rel_path LIKE :prefix || '%'`。
- `upsert` 先 `delete_file` 再插入；`replace_all` 先 `delete_workspace` 再批量 insert（每批 200 行）。
- `ensure_fts_supported`：在只读连接上试建临时 trigram 虚拟表并 drop，捕获 `sqlite3.OperationalError` 返回 `False`。

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && uv run pytest tests/db/test_workspace_documents.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/prism_agent_kit/db/repositories/workspace_documents.py backend/src/prism_agent_kit/db/uow.py backend/tests/db/test_workspace_documents.py
git commit -m "feat(db): FTS5 文档仓储与中文短查询回退"
```

---

### Task 5: 路径安全

**Files:**
- Create: `backend/src/prism_agent_kit/core/workspace_paths.py`
- Test: `backend/tests/core/test_workspace_paths.py`

**Interfaces:**
- Produces：`resolve_in_workspace(root: str | Path, rel: str | None) -> Path`；`EXCLUDED_DIR_NAMES: frozenset[str]`。

- [ ] **Step 1: 写失败测试**

```python
def test_rejects_traversal_and_absolute(tmp_path: Path) -> None:
    root = tmp_path / "ws"; root.mkdir()
    with pytest.raises(AgentKitError) as exc:
        resolve_in_workspace(root, "../outside.txt")
    assert exc.value.code is ErrorCode.WORKSPACE_PATH_OUTSIDE
    with pytest.raises(AgentKitError):
        resolve_in_workspace(root, "/etc/passwd")


def test_rejects_symlink_escape(tmp_path: Path) -> None:
    root = tmp_path / "ws"; root.mkdir()
    outside = tmp_path / "secret"; outside.mkdir()
    (root / "link").symlink_to(outside, target_is_directory=True)
    with pytest.raises(AgentKitError) as exc:
        resolve_in_workspace(root, "link/secret.txt")
    assert exc.value.code is ErrorCode.WORKSPACE_PATH_OUTSIDE


def test_allows_nested_and_root(tmp_path: Path) -> None:
    root = tmp_path / "ws"; (root / "docs").mkdir(parents=True)
    assert resolve_in_workspace(root, "docs/a.md") == (root / "docs/a.md").resolve()
    assert resolve_in_workspace(root, "") == root.resolve()


def test_rejects_nul(tmp_path: Path) -> None:
    root = tmp_path / "ws"; root.mkdir()
    with pytest.raises(AgentKitError) as exc:
        resolve_in_workspace(root, "a\x00b")
    assert exc.value.code is ErrorCode.WORKSPACE_PATH_INVALID
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && uv run pytest tests/core/test_workspace_paths.py -q`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现**

`resolve_in_workspace`：拒绝 `\x00` 与 `rel` 为空串时返回根；`candidate = (root / rel).resolve()`（`strict=False`）；`real_root = Path(root).resolve()`；用 `os.path.commonpath([str(candidate), str(real_root)]) == str(real_root)` 判定包含关系，否则 `WORKSPACE_PATH_OUTSIDE`(403)。`EXCLUDED_DIR_NAMES = frozenset({".git","node_modules","dist","build",".dart_tool","coverage"})`。

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && uv run pytest tests/core/test_workspace_paths.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/prism_agent_kit/core/workspace_paths.py backend/tests/core/test_workspace_paths.py
git commit -m "feat(core): 工作区路径安全校验"
```

---

### Task 6: WorkspaceService（绑定、树、读文件、搜索、目录选择）

**Files:**
- Create: `backend/src/prism_agent_kit/application/workspace_service.py`
- Test: `backend/tests/application/test_workspace_service.py`

**Interfaces:**
- Consumes：`UnitOfWorkFactory`、`WorkspaceRepository`、`WorkspaceDocumentRepository`、`resolve_in_workspace`、`WorkspaceIndexTaskManager.submit`（Task 7，`mode="full"`）。
- Produces：`WorkspaceService(uow_factory=..., index_tasks=..., max_file_bytes=..., max_files=...)`，方法 `list() / active() / get(id) / create(path, label=None) / activate(id) / delete(id) / root_for(workspace_id) -> Path | None / tree(id, rel=".") -> list[TreeEntry] / read_file(id, rel, max_bytes=65536) -> FileContent / search(id, query, *, limit=20, path_prefix=None) -> list[SearchHit] / pick_directory() -> str`；`TreeEntry(name, type, size, modified_at)`、`FileContent(path, content, truncated, size)`。

- [ ] **Step 1: 写失败测试**

```python
async def test_create_workspace_normalizes_and_activates(service: WorkspaceService, tmp_path: Path) -> None:
    root = tmp_path / "proj"; root.mkdir()
    workspace = await service.create(str(root / "."))
    assert workspace.root_path == str(root.resolve())
    assert workspace.is_active is True


async def test_create_rejects_relative_or_file(service: WorkspaceService, tmp_path: Path) -> None:
    (tmp_path / "f.txt").write_text("x", encoding="utf-8")
    with pytest.raises(AgentKitError) as exc:
        await service.create("relative/path")
    assert exc.value.code is ErrorCode.WORKSPACE_PATH_INVALID
    with pytest.raises(AgentKitError):
        await service.create(str(tmp_path / "f.txt"))


async def test_tree_excludes_git_and_reads_truncated(service: WorkspaceService, tmp_path: Path) -> None:
    root = tmp_path / "proj"; (root / ".git").mkdir(parents=True)
    (root / "docs").mkdir()
    (root / "docs" / "a.txt").write_text("x" * 50, encoding="utf-8")
    ws = await service.create(str(root))
    entries = await service.tree(ws.id, ".")
    assert {entry.name for entry in entries} == {"docs"}
    content = await service.read_file(ws.id, "docs/a.txt", max_bytes=10)
    assert content.truncated is True and len(content.content) == 10


async def test_read_rejects_binary(service: WorkspaceService, tmp_path: Path) -> None:
    root = tmp_path / "proj"; root.mkdir()
    (root / "bin.dat").write_bytes(b"abc\x00def")
    ws = await service.create(str(root))
    with pytest.raises(AgentKitError) as exc:
        await service.read_file(ws.id, "bin.dat")
    assert exc.value.code is ErrorCode.WORKSPACE_FILE_BINARY
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && uv run pytest tests/application/test_workspace_service.py -q`
Expected: FAIL

- [ ] **Step 3: 实现**

- `create`：校验绝对路径、存在、是目录、`resolve()` 后落库；若 `root_path` 已存在则返回现有并激活；工作区根若包含 `settings` 的数据库文件所在目录（用注入的 `data_dir: Path | None` 判断）抛 `WORKSPACE_PATH_INVALID`。
- `tree`/`read_file`：全部在 `asyncio.to_thread` 中做 `os.scandir` / 读文件；`read_file` 用 `lstat` 判普通文件、大小、NUL 检测与 UTF-8 严格解码。
- `pick_directory`：`subprocess.run([...], capture_output=True, timeout=120)`；darwin 用 `osascript -e 'POSIX path of (choose folder with prompt "选择工作区目录")'`，linux 用 `zenity --file-selection --directory`，win32 用 PowerShell 片段；非零退出/超时/缺命令统一抛 `WORKSPACE_PICKER_UNAVAILABLE`(409)，`details={"reason": ...}`。
- 激活后调用 `await self._index_tasks.submit(workspace_id, mode="full")`。

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && uv run pytest tests/application/test_workspace_service.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/prism_agent_kit/application/workspace_service.py backend/tests/application/test_workspace_service.py
git commit -m "feat(workspace): 工作区服务与原生目录选择"
```

---

### Task 7: 索引器与索引任务管理器

**Files:**
- Create: `backend/src/prism_agent_kit/application/workspace_indexer.py`
- Create: `backend/src/prism_agent_kit/application/index_tasks.py`
- Test: `backend/tests/application/test_workspace_indexer.py`

**Interfaces:**
- Consumes：`WorkspaceRepository`、`WorkspaceDocumentRepository`、`resolve_in_workspace`。
- Produces：`IndexReport(status: IndexStatus, file_count: int, error: str | None)`；`WorkspaceIndexer.rebuild(workspace_id) -> IndexReport`、`index_file(workspace_id, rel_path) -> IndexReport`；`WorkspaceIndexTaskManager(indexer=..., uow_factory=...)`，方法 `submit(workspace_id, *, mode="full", rel_path=None) -> None`、`reset_interrupted() -> int`、`drain() -> None`、`stop() -> None`。

- [ ] **Step 1: 写失败测试**

```python
async def test_rebuild_indexes_only_indexable_files(indexer: WorkspaceIndexer, uow_factory, tmp_path: Path) -> None:
    root = tmp_path / "proj"
    (root / ".git").mkdir(parents=True)
    (root / "node_modules").mkdir()
    (root / "docs").mkdir()
    (root / "docs" / "a.md").write_text("工作区检索测试", encoding="utf-8")
    (root / ".git" / "x.md").write_text("should skip", encoding="utf-8")
    (root / ".env").write_text("SECRET=1", encoding="utf-8")
    (root / "big.txt").write_text("x" * (2 * 1024 * 1024), encoding="utf-8")
    (root / "bin.dat").write_bytes(b"a\x00b")
    async with uow_factory() as uow:
        ws = await uow.workspaces.create(Workspace(root_path=str(root)))
        await uow.commit()
    report = await indexer.rebuild(ws.id)
    assert report.status is IndexStatus.READY
    assert report.file_count == 1
    async with uow_factory() as uow:
        hits = await uow.workspace_documents.search(ws.id, "工作区检索", limit=10, path_prefix=None)
        assert [hit.path for hit in hits] == ["docs/a.md"]


async def test_reset_interrupted_marks_failed(indexer, uow_factory, tmp_path: Path) -> None:
    async with uow_factory() as uow:
        ws = await uow.workspaces.create(Workspace(root_path=str(tmp_path / "p")))
        await uow.workspaces.update_index_state(ws.id, status=IndexStatus.INDEXING)
        await uow.commit()
    manager = WorkspaceIndexTaskManager(indexer=indexer, uow_factory=uow_factory)
    assert await manager.reset_interrupted() == 1
    async with uow_factory() as uow:
        refreshed = await uow.workspaces.get(ws.id)
        assert refreshed.index_status is IndexStatus.FAILED
        assert refreshed.index_error == "process_interrupted"
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && uv run pytest tests/application/test_workspace_indexer.py -q`
Expected: FAIL

- [ ] **Step 3: 实现**

- 遍历：`os.walk`（跳过 `EXCLUDED_DIR_NAMES`），按 spec §9.4 过滤扩展名/文件名/符号链接/大小；累计超过 `max_files` 或 200 MiB 时停止并记 `index_error="truncated_at_limit"`。
- `rebuild`：置 `indexing` → 读文件（`to_thread`）→ `replace_all` → `update_index_state(READY, file_count=..., indexed_at=now)`；异常时置 `FAILED` 并返回 `IndexReport(status=FAILED, error=...)`，保留旧文档。
- `index_file`：单文件 upsert，成功后 `file_count = count(workspace_id)`。
- `WorkspaceIndexTaskManager.submit`：若已有该工作区任务在跑则直接返回；`asyncio.create_task` 登记，完成时移除；`drain()` 供测试等待；`stop()` cancel 全部并 `gather`。

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && uv run pytest tests/application/test_workspace_indexer.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/prism_agent_kit/application/workspace_indexer.py backend/src/prism_agent_kit/application/index_tasks.py backend/tests/application/test_workspace_indexer.py
git commit -m "feat(workspace): 全文索引器与后台索引任务管理"
```

---

### Task 8: 工具契约与四个工作区工具

**Files:**
- Modify: `backend/src/prism_agent_kit/tools/contracts.py`
- Create: `backend/src/prism_agent_kit/tools/workspace_tools.py`
- Test: `backend/tests/tools/test_workspace_tools.py`

**Interfaces:**
- Produces：`ToolDefinition.requires_approval: bool = False`；`ToolExecutionContext.workspace_root: Path | None = None`；`build_workspace_tools() -> list[ToolDefinition]`（`file_list`、`file_read`、`file_search`、`file_write`，其中 `file_write` 的 `requires_approval=True`）。

- [ ] **Step 1: 写失败测试**

```python
async def test_file_list_and_read(tmp_path: Path) -> None:
    root = tmp_path / "ws"; (root / "docs").mkdir(parents=True)
    (root / "docs" / "a.md").write_text("hello", encoding="utf-8")
    tools = {tool.name: tool for tool in build_workspace_tools()}
    context = ToolExecutionContext(run_id="r", session_id="s", call_id="c", cancel=asyncio.Event(), workspace_root=root)
    listed = await tools["file_list"].handler(FileListInput(path="."), context)
    assert [entry.name for entry in listed.entries] == ["docs"]
    read = await tools["file_read"].handler(FileReadInput(path="docs/a.md", max_bytes=3), context)
    assert read.truncated is True and read.content == "hel"


async def test_tools_without_workspace(tmp_path: Path) -> None:
    tools = {tool.name: tool for tool in build_workspace_tools()}
    context = ToolExecutionContext(run_id="r", session_id="s", call_id="c", cancel=asyncio.Event())
    with pytest.raises(AgentKitError) as exc:
        await tools["file_list"].handler(FileListInput(path="."), context)
    assert exc.value.code is ErrorCode.WORKSPACE_NOT_BOUND


async def test_write_requires_approval_and_rejects_escape(tmp_path: Path) -> None:
    tools = {tool.name: tool for tool in build_workspace_tools()}
    assert tools["file_write"].requires_approval is True
    root = tmp_path / "ws"; root.mkdir()
    context = ToolExecutionContext(run_id="r", session_id="s", call_id="c", cancel=asyncio.Event(), workspace_root=root)
    with pytest.raises(AgentKitError) as exc:
        await tools["file_write"].handler(FileWriteInput(path="../x.txt", content="x"), context)
    assert exc.value.code is ErrorCode.WORKSPACE_PATH_OUTSIDE
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && uv run pytest tests/tools/test_workspace_tools.py -q`
Expected: FAIL

- [ ] **Step 3: 实现**

`contracts.py`：`ToolExecutionContext` 加 `workspace_root: Path | None = None`（`model_config` 已允许任意类型）；`ToolDefinition` 加 `requires_approval: bool = False`。

`workspace_tools.py`：定义 `FileListInput/Output`、`FileReadInput/Output`、`FileSearchInput/Output`、`FileWriteInput/Output` Pydantic 模型（字段与 spec §10 一致），以及 `_require_root(context) -> Path` 辅助；handler 内用 `asyncio.to_thread` 做 FS 操作，写文件前用 `resolve_in_workspace` 校验并拒绝 `.git/`。

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && uv run pytest tests/tools/test_workspace_tools.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/prism_agent_kit/tools/contracts.py backend/src/prism_agent_kit/tools/workspace_tools.py backend/tests/tools/test_workspace_tools.py
git commit -m "feat(tools): 工作区文件工具与审批标记"
```

---

### Task 9: 抽取 ToolResultRecorder

**Files:**
- Create: `backend/src/prism_agent_kit/application/tool_result_recorder.py`
- Modify: `backend/src/prism_agent_kit/core/engine.py`
- Test: `backend/tests/application/test_tool_result_recorder.py`

**Interfaces:**
- Produces：`ToolResultRecorder(uow_factory=..., event_publisher=...)`，方法 `record(run_id: str, call_id: str, result: ToolExecutionResult) -> None`；引擎改为委托它，行为与现在 `_record_tool_result` 完全一致（成功写 tool 消息 + `tool.completed`，失败写错误内容 + `tool.failed`）。

- [ ] **Step 1: 写失败测试**

```python
async def test_record_success_writes_message_and_event(uow_factory, event_publisher, seeded_run_call) -> None:
    recorder = ToolResultRecorder(uow_factory=uow_factory, event_publisher=event_publisher)
    await recorder.record(seeded_run_call.run_id, seeded_run_call.call_id, ToolExecutionResult.success({"ok": True}))
    async with uow_factory() as uow:
        call = await uow.tool_calls.get(seeded_run_call.run_id, seeded_run_call.call_id)
        assert call.status is ToolCallStatus.SUCCEEDED
        events = await uow.events.list_after(seeded_run_call.run_id, after_id=0)
        assert EventType.TOOL_COMPLETED in [event.event_type for event in events]
```

（`seeded_run_call` 为测试内 helper，复用 `tests/api/helpers.py` 的造数思路，创建一个 running Run + pending ToolCall。）

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && uv run pytest tests/application/test_tool_result_recorder.py -q`
Expected: FAIL

- [ ] **Step 3: 实现**

把 `SimpleAgentEngine._record_tool_result` 的方法体原样搬进 `ToolResultRecorder.record`；引擎构造参数增加 `tool_result_recorder`，`_record_tool_result` 改为一行委托（或直接调用 recorder）。

- [ ] **Step 4: 运行确认通过（含回归）**

Run: `cd backend && uv run pytest tests/application/test_tool_result_recorder.py tests/core/test_engine_local.py tests/test_agent_e2e.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/prism_agent_kit/application/tool_result_recorder.py backend/src/prism_agent_kit/core/engine.py backend/tests/application/test_tool_result_recorder.py
git commit -m "refactor(engine): 抽取工具结果记录器供审批复用"
```

---

### Task 10: 引擎审批闸门

**Files:**
- Modify: `backend/src/prism_agent_kit/core/engine.py`
- Modify: `backend/src/prism_agent_kit/core/ports.py`
- Test: `backend/tests/core/test_engine_approval.py`

**Interfaces:**
- Consumes：`ToolDefinition.requires_approval`、`WorkspaceLocator`。
- Produces：`WorkspaceLocator(Protocol).root_for(workspace_id: str | None) -> Path | None`；`EngineOutcome.kind` 增加 `"waiting_for_approval"`；`SimpleAgentEngine.__init__` 增加 `workspace_locator: WorkspaceLocator | None = None`、`require_write_approval: bool = True`、`approval_timeout_seconds: float = 1800`。

- [ ] **Step 1: 写失败测试**

```python
async def test_engine_suspends_for_approval(engine_with_approval_tool, uow_factory) -> None:
    outcome = await engine_with_approval_tool.execute(EngineContext(run_id=run_id, cancel=asyncio.Event()))
    assert outcome.kind == "waiting_for_approval"
    async with uow_factory() as uow:
        run = await uow.runs.get(run_id)
        calls = await uow.tool_calls.list_for_run(run_id)
        assert run.status is RunStatus.WAITING_FOR_APPROVAL
        assert [call.status for call in calls] == [ToolCallStatus.AWAITING_APPROVAL]
        events = await uow.events.list_after(run_id, after_id=0)
        types = [event.event_type for event in events]
        assert EventType.RUN_WAITING_FOR_APPROVAL in types
        assert EventType.TOOL_COMPLETED not in types
```

再加一条：同轮有普通本地工具时，普通工具仍被执行为 `SUCCEEDED`，等待审批前不得写 tool 消息给 `file_write`。

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && uv run pytest tests/core/test_engine_approval.py -q`
Expected: FAIL

- [ ] **Step 3: 实现**

- `ports.py`：加 `WorkspaceLocator` Protocol。
- 引擎本地工具循环（现 227–264 行）：遇到 `definition.requires_approval and self._require_write_approval` 时收集到 `approval_calls` 并 `continue`；其余照旧执行。
- 循环后若 `approval_calls`：调用新方法 `_wait_for_approval(run_id, [c.id for c in approval_calls])` —— 单个事务内对每个调用 `uow.tool_calls.await_call(y, expires_at=now + approval_timeout)`，`runs.transition(WAITING_FOR_APPROVAL)`，写 `RUN_WAITING_FOR_APPROVAL` 与每个调用的 `TOOL_APPROVAL_REQUIRED`（payload `{call_id, tool_name, path, mode, bytes}`，从 `call.input` 取值），commit + publish，返回 `EngineOutcome(kind="waiting_for_approval")`。
- 构造 `ToolExecutionContext` 时把 `workspace_root` 填为 `await self._workspace_locator.root_for(run.workspace_id)`（每次 `_run` 开头解析一次并复用；`workspace_locator is None` 时为 `None`）。
- 配置关闭审批（`require_write_approval=False`）时按普通本地工具执行。

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && uv run pytest tests/core/test_engine_approval.py tests/core/test_engine_local.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/prism_agent_kit/core/engine.py backend/src/prism_agent_kit/core/ports.py backend/tests/core/test_engine_approval.py
git commit -m "feat(engine): 写入审批闸门与等待状态"
```

---

### Task 11: 审批服务（决策、混合轮次、预览）

**Files:**
- Create: `backend/src/prism_agent_kit/application/tool_approval_service.py`
- Test: `backend/tests/application/test_tool_approval_service.py`

**Interfaces:**
- Consumes：`ToolRegistry`、`LocalToolExecutor`、`ToolResultRecorder`、`WorkspaceService.root_for`、`WorkspaceIndexTaskManager.submit(mode="file")`、`RunCancellationRegistry`。
- Produces：`ToolApprovalService(...).preview(run_id, call_id) -> ApprovalPreview(path, mode, bytes, exists, diff, truncated)`、`.decide(run_id, call_id, decision: str, reason: str | None) -> tuple[ToolCall, Run]`。

- [ ] **Step 1: 写失败测试**

```python
async def test_approve_executes_write_and_requeues(approval_ctx) -> None:
    call, run = await approval_ctx.service.decide(approval_ctx.run_id, approval_ctx.call_id, "approve", None)
    assert call.status is ToolCallStatus.SUCCEEDED
    assert run.status is RunStatus.QUEUED
    assert (approval_ctx.workspace_root / "notes.md").read_text(encoding="utf-8") == "hello"


async def test_reject_marks_tool_rejected(approval_ctx) -> None:
    call, run = await approval_ctx.service.decide(approval_ctx.run_id, approval_ctx.call_id, "reject", "不要写")
    assert call.status is ToolCallStatus.FAILED
    assert call.error_code == ErrorCode.TOOL_REJECTED.value
    assert run.status is RunStatus.QUEUED


async def test_mixed_turn_moves_to_waiting_for_tool(approval_ctx_with_remote) -> None:
    _, run = await approval_ctx_with_remote.service.decide(
        approval_ctx_with_remote.run_id, approval_ctx_with_remote.call_id, "approve", None
    )
    assert run.status is RunStatus.WAITING_FOR_TOOL


async def test_write_uses_run_workspace_after_switch(approval_ctx, other_workspace) -> None:
    # 审批前把活跃工作区切到 other_workspace，写入仍必须落在 Run 绑定的目录
    call, _ = await approval_ctx.service.decide(approval_ctx.run_id, approval_ctx.call_id, "approve", None)
    assert call.status is ToolCallStatus.SUCCEEDED
    assert (approval_ctx.workspace_root / "notes.md").exists()
    assert not (other_workspace / "notes.md").exists()


async def test_partial_approvals_keep_waiting(approval_ctx_two_calls) -> None:
    _, run = await approval_ctx_two_calls.service.decide(
        approval_ctx_two_calls.run_id, approval_ctx_two_calls.first_call_id, "approve", None
    )
    assert run.status is RunStatus.WAITING_FOR_APPROVAL
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && uv run pytest tests/application/test_tool_approval_service.py -q`
Expected: FAIL

- [ ] **Step 3: 实现**

- `decide`：服务级 `asyncio.Lock`；事务内取 run/call，校验 `awaiting_approval` 与 `expires_at`（终态按幂等返回）；`reject` → `tool_calls.fail(..., TOOL_REJECTED, reason or "用户拒绝写入")` 并写 `TOOL_REJECTED` 事件。
- `approve`：`tool_calls.start_after_approval`（`awaiting_approval → running`），取 `workspace_root = await workspace_service.root_for(run.workspace_id)`，`LocalToolExecutor.execute(definition, call.input, ToolExecutionContext(..., workspace_root=root, cancel=registry.register(run_id)))`，结束后 `unregister`，用 `ToolResultRecorder.record` 落结果与事件；写成功后 `index_tasks.submit(workspace_id, mode="file", rel_path=...)`。
- 每次决策后重算 `list_for_run`：仍有 `awaiting_approval` → 保持；无 awaiting 但有 `pending|running` 远端调用 → `runs.transition(WAITING_FOR_TOOL)` + `run.waiting_for_tool`；全终态 → `runs.transition(QUEUED)` + `run.requeued`。
- `preview`：仅 `awaiting_approval` 可读；用 `asyncio.to_thread` 读旧文件内容并与 `content` 做 `difflib.unified_diff`（3 行上下文，最多 200 行、20 KB）。

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && uv run pytest tests/application/test_tool_approval_service.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/prism_agent_kit/application/tool_approval_service.py backend/tests/application/test_tool_approval_service.py
git commit -m "feat(approval): 写入审批服务与混合轮次闭合"
```

---

### Task 12: 审批过期扫描与恢复范围

**Files:**
- Modify: `backend/src/prism_agent_kit/application/run_worker.py`
- Modify: `backend/src/prism_agent_kit/db/repositories/tool_calls.py`
- Test: `backend/tests/application/test_run_worker.py`, `backend/tests/application/test_recovery.py`

**Interfaces:**
- Produces：`ToolCallRepository.await_call(run_id, call_id, expires_at) -> ToolCall`、`start_after_approval(run_id, call_id) -> ToolCall`；`list_expired` 覆盖 `awaiting_approval`；`close_open_calls` 覆盖 `awaiting_approval`；`sweep_expired_tool_calls` 同时处理两种等待状态；`recover_interrupted_runs` 不动 `waiting_for_approval`。

- [ ] **Step 1: 写失败测试**

```python
async def test_sweep_expires_awaiting_approval(uow_factory, worker) -> None:
    # 造一个 waiting_for_approval Run + 已过期 awaiting_approval 调用
    count = await worker.sweep_expired_tool_calls()
    assert count == 1
    async with uow_factory() as uow:
        call = await uow.tool_calls.get(run_id, call_id)
        assert call.status is ToolCallStatus.EXPIRED
        run = await uow.runs.get(run_id)
        assert run.status is RunStatus.QUEUED


async def test_recovery_keeps_waiting_for_approval(uow_factory, worker) -> None:
    # 造一个 waiting_for_approval Run
    assert await worker.recover_interrupted_runs() == 0
    async with uow_factory() as uow:
        run = await uow.runs.get(run_id)
        assert run.status is RunStatus.WAITING_FOR_APPROVAL
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && uv run pytest tests/application/test_run_worker.py tests/application/test_recovery.py -q`
Expected: FAIL

- [ ] **Step 3: 实现**

- `tool_calls.py`：`await_call`（要求 `PENDING`，置 `AWAITING_APPROVAL` 与 `expires_at`）；`start_after_approval`（要求 `AWAITING_APPROVAL`，置 `RUNNING`）；`list_expired` 的 `status.in_` 加入 `AWAITING_APPROVAL`；`close_open_calls` 的 `status.in_` 加入 `AWAITING_APPROVAL`；`_closure_status` 对 `TOOL_APPROVAL_TIMEOUT` 返回 `EXPIRED` + `TOOL_EXPIRED`。
- `run_worker.py`：`sweep_expired_tool_calls` 的 Run 状态判断 `in {WAITING_FOR_TOOL, WAITING_FOR_APPROVAL}`；`recover_interrupted_runs` 保持不变（只查 `RUNNING`）。

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && uv run pytest tests/application/test_run_worker.py tests/application/test_recovery.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/prism_agent_kit/application/run_worker.py backend/src/prism_agent_kit/db/repositories/tool_calls.py backend/tests/application/test_run_worker.py backend/tests/application/test_recovery.py
git commit -m "feat(worker): 审批超时扫描与恢复边界"
```

---

### Task 13: 工作区 HTTP、审批路由、容器装配与健康自检

**Files:**
- Create: `backend/src/prism_agent_kit/api/routes/workspaces.py`
- Modify: `backend/src/prism_agent_kit/api/routes/runs.py`
- Modify: `backend/src/prism_agent_kit/api/schemas.py`
- Modify: `backend/src/prism_agent_kit/api/dependencies.py`
- Modify: `backend/src/prism_agent_kit/application/container.py`
- Modify: `backend/src/prism_agent_kit/main.py`
- Test: `backend/tests/api/test_workspaces.py`, `backend/tests/api/test_approval.py`, `backend/tests/test_health.py`

**Interfaces:**
- Produces：`WorkspaceView / WorkspaceListResponse / TreeEntryView / FileView / SearchResponse / ApprovalRequest / ApprovalResponse / ApprovalPreviewView`；`RunView.workspace_id`；依赖 `WorkspaceServiceDependency`、`ToolApprovalServiceDependency`；容器暴露 `workspace_service`、`tool_approval_service`、`index_task_manager`；健康响应增加 `workspace_fts: "ok" | "unsupported"`。

- [ ] **Step 1: 写失败测试**

```python
def test_workspace_crud_and_tree(api_client: TestClient, tmp_path: Path) -> None:
    root = tmp_path / "ws"; (root / "docs").mkdir(parents=True)
    (root / "docs" / "a.md").write_text("工作区检索", encoding="utf-8")
    created = api_client.post("/api/v1/workspaces", json={"path": str(root)})
    assert created.status_code == 200
    workspace_id = created.json()["id"]
    tree = api_client.get(f"/api/v1/workspaces/{workspace_id}/tree", params={"path": "."})
    assert tree.status_code == 200 and tree.json()["items"][0]["name"] == "docs"


def test_approval_endpoint_returns_call_and_run(api_client: TestClient, seeded_waiting_approval: dict) -> None:
    response = api_client.post(
        f"/api/v1/runs/{seeded_waiting_approval['run_id']}/tool-calls/{seeded_waiting_approval['call_id']}/approval",
        json={"decision": "approve"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["call"]["status"] == "succeeded" and body["run"]["status"] == "queued"


def test_health_reports_workspace_fts(api_client: TestClient) -> None:
    assert api_client.get("/api/v1/health").json()["workspace_fts"] == "ok"
```

未鉴权用例参照 `tests/api/test_auth.py` 的 `make_app(database_path, api_token=SecretStr("secret"))` 方式构造应用，断言 `GET /api/v1/workspaces` 返回 401。

（`seeded_waiting_approval` 与 `api_client` 都在 `tests/api/conftest.py`；`seeded_waiting_approval` 用 `tests/api/helpers.py` 的造数风格，构造绑定临时工作区的 Run + `awaiting_approval` 调用。）

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && uv run pytest tests/api/test_workspaces.py tests/api/test_approval.py tests/test_health.py -q`
Expected: FAIL（404）

- [ ] **Step 3: 实现**

- `routes/workspaces.py`：11 个接口按 spec §12 实现；`POST /workspaces` 返回 `WorkspaceView`；`pick` 把 `WORKSPACE_PICKER_UNAVAILABLE` 原样映射 409。
- `routes/runs.py`：新增 `GET .../preview`（`ApprovalPreviewView`）与 `POST .../approval`（返回 `{"call": ToolCallView, "run": RunView}`）。
- `schemas.py`：新增 DTO；`RunView` 加 `workspace_id: str | None` 并在 `from_domain` 填入。
- `dependencies.py`：新增两个依赖类型。
- `container.py`：装配 `WorkspaceService`、`WorkspaceIndexTaskManager`（`start()` 里 `await reset_interrupted()`）、`ToolApprovalService`；把 `build_workspace_tools()` 注册进 `ToolRegistry`；`stop()` 里 `await index_task_manager.stop()`；启动时用 `ensure_fts_supported` 计算 `workspace_fts` 存入容器供健康路由读取。
- `main.py`：注册 `create_workspaces_router()`。
- **同步扩展测试容器**：`backend/tests/api/conftest.py` 的 `ApiTestContainer` 与 `build_api_application` 需要装配 `WorkspaceService`、`WorkspaceIndexTaskManager`、`ToolApprovalService`，并把 `build_workspace_tools()` 注册进测试 `ToolRegistry`；否则新依赖在 API 测试中取不到。

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && uv run pytest tests/api -q && uv run pytest -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/prism_agent_kit/api/routes/workspaces.py backend/src/prism_agent_kit/api/routes/runs.py backend/src/prism_agent_kit/api/schemas.py backend/src/prism_agent_kit/api/dependencies.py backend/src/prism_agent_kit/application/container.py backend/src/prism_agent_kit/main.py backend/tests/api/test_workspaces.py backend/tests/api/test_approval.py backend/tests/api/conftest.py backend/tests/test_health.py
git commit -m "feat(api): 工作区与审批 HTTP 接口"
```

---

### Task 14: UI 契约与客户端方法

**Files:**
- Modify: `ui/src/lib/api/contracts.ts`
- Modify: `ui/src/lib/api/client.ts`
- Test: `ui/src/lib/api/contracts.test.ts`

**Interfaces:**
- Produces：`workspaceSchema`、`workspaceListSchema`、`treeResponseSchema`、`fileResponseSchema`、`searchResponseSchema`、`approvalPreviewSchema`、`approvalResponseSchema`；`runSchema.status` 与 `toolCallSchema.status` 扩展；事件联合类型加 4 个新事件；`runSchema.workspace_id`；`createCoreClient` 增加 10 个方法。

- [ ] **Step 1: 写失败测试**

```typescript
it('解析 waiting_for_approval 与新事件', () => {
  expect(runSchema.parse({ ...runFixture, status: 'waiting_for_approval', workspace_id: 'w1' }).status)
    .toBe('waiting_for_approval')
})
it('审批响应必须同时含 call 与 run', () => {
  expect(approvalResponseSchema.safeParse({ call: callFixture, run: runFixture }).success).toBe(true)
  expect(approvalResponseSchema.safeParse({ call: callFixture }).success).toBe(false)
})
```

- [ ] **Step 2: 运行确认失败**

Run: `cd ui && pnpm vitest run src/lib/api/contracts.test.ts`
Expected: FAIL

- [ ] **Step 3: 实现**

按 spec §13.4 扩展 `contracts.ts`（严格字段、`workspace_id: id.nullable()`）与 `client.ts` 方法（`listWorkspaces`、`pickWorkspace`、`createWorkspace`、`activateWorkspace`、`reindexWorkspace`、`getTree`、`getFile`、`searchWorkspace`、`getApprovalPreview`、`decideApproval`），统一走现有 `request`/`assertResponse`。

- [ ] **Step 4: 运行确认通过**

Run: `cd ui && pnpm vitest run src/lib/api/contracts.test.ts && pnpm typecheck`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add ui/src/lib/api/contracts.ts ui/src/lib/api/client.ts ui/src/lib/api/contracts.test.ts
git commit -m "feat(ui): 工作区与审批 API 契约"
```

---

### Task 15: 工作区页

**Files:**
- Create: `ui/src/features/workspace/WorkspacePage.vue`
- Create: `ui/src/features/workspace/workspace.ts`（状态与轮询控制器）
- Modify: `ui/src/app/modules.ts`
- Modify: `ui/src/app/router.ts`
- Test: `ui/src/features/workspace/workspace.test.ts`

**Interfaces:**
- Consumes：Task 14 的客户端方法。
- Produces：`createWorkspaceController({ client })`，暴露 `state`（`workspaces, active, indexStatus, entries, currentPath, previewFile, searchResults`）与动作 `chooseDirectory() / bindPath(path) / activate(id) / reindex() / openDirectory(rel) / openFile(rel) / search(q)`；索引中每 1500ms 轮询 `get(id)`。

- [ ] **Step 1: 写失败测试**

```typescript
it('索引中会继续轮询直到 ready', async () => {
  const controller = createWorkspaceController({ client: fakeClient })
  await controller.refreshActive()
  expect(fakeClient.getWorkspace).toHaveBeenCalledTimes(1)
  await controller.pollOnce()
  expect(fakeClient.getWorkspace).toHaveBeenCalledTimes(2)
})
it('切换工作区后清空文件与搜索状态', async () => {
  const controller = createWorkspaceController({ client: fakeClient })
  await controller.openFile('a.md')
  await controller.activate('w2')
  expect(controller.state.previewFile).toBeNull()
})
```

- [ ] **Step 2: 运行确认失败**

Run: `cd ui && pnpm vitest run src/features/workspace/workspace.test.ts`
Expected: FAIL

- [ ] **Step 3: 实现**

- `workspace.ts`：控制器与状态（`reactive`），错误转成可展示文案，不吞错。
- `WorkspacePage.vue`：三块布局（当前工作区卡片 / 文件树 / 预览与搜索），使用现有 `Button`、`Input`、`Separator`、`Sheet` 组件与语义色；未绑定态整页提示。
- `modules.ts` 加 `{ id: 'workspace', label: '工作区', path: '/workspace' }`；`router.ts` 加路由。

- [ ] **Step 4: 运行确认通过**

Run: `cd ui && pnpm vitest run src/features/workspace/workspace.test.ts && pnpm typecheck`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add ui/src/features/workspace ui/src/app/modules.ts ui/src/app/router.ts
git commit -m "feat(ui): 工作区页与索引状态"
```

---

### Task 16: 会话页写入审批卡片

**Files:**
- Modify: `ui/src/features/runs/RunInspector.vue`
- Modify: `ui/src/features/runs/ToolCallCard.vue`
- Modify: `ui/src/features/runs/projection.ts`
- Modify: `ui/src/features/sessions/SessionPage.vue`
- Modify: `ui/src/features/sessions/conversation.ts`
- Test: `ui/src/features/runs/projection.test.ts`

**Interfaces:**
- Consumes：Task 14 的 `decideApproval`、`getApprovalPreview`。
- Produces：projection 暴露 `pendingApprovals: Array<{ callId, toolName, path, mode, bytes }>`；`RunInspector` 渲染审批卡片（展开时拉 preview），`SessionPage` 顶部横幅计数。

- [ ] **Step 1: 写失败测试**

```typescript
it('从事件投影出待审批调用', () => {
  const projection = buildProjection([
    event('tool.approval_required', { call_id: 'c1', tool_name: 'file_write', path: 'a.md', mode: 'overwrite', bytes: 3 }),
  ])
  expect(projection.pendingApprovals).toEqual([
    { callId: 'c1', toolName: 'file_write', path: 'a.md', mode: 'overwrite', bytes: 3 },
  ])
})
it('approved 事件把待审批移除', () => { /* tool.approved 后 pendingApprovals 为空 */ })
```

- [ ] **Step 2: 运行确认失败**

Run: `cd ui && pnpm vitest run src/features/runs/projection.test.ts`
Expected: FAIL

- [ ] **Step 3: 实现**

- `projection.ts`：识别 4 个新事件；`pendingApprovals` 由 `approval_required` 添加、`approved/rejected` 移除。
- `RunInspector.vue`：卡片显示路径/模式/字节，展开时 `getApprovalPreview` 拉 diff；按钮调用 `decideApproval` 并用返回的 `call`、`run` 更新本地状态；提交中禁用。
- `ToolCallCard.vue`：补 `awaiting_approval` / `TOOL_REJECTED` 文案；`file_write` 不渲染正文。
- `SessionPage.vue`：`waiting_for_approval` 顶部横幅。

- [ ] **Step 4: 运行确认通过**

Run: `cd ui && pnpm vitest run src/features/runs/projection.test.ts && pnpm check && pnpm build`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add ui/src/features/runs ui/src/features/sessions
git commit -m "feat(ui): 会话页写入审批交互"
```

---

### Task 17: 文档与端到端验收

**Files:**
- Modify: `README.md`
- Modify: `backend/README.md`
- Modify: `ui/README.md`
- Modify: `backend/.env.example`
- Test: `backend/tests/test_agent_e2e.py`（追加一条含审批的端到端用例）

**Interfaces:**
- Consumes：全部前序任务。

- [ ] **Step 1: 写失败测试**

在 `backend/tests/test_agent_e2e.py` 追加：

```python
def test_e2e_write_requires_approval_then_completes(migrated_database_path: Path) -> None:
    settings = make_settings(migrated_database_path, workspace_require_write_approval=True)
    application = create_app(settings)
    provider = ScriptedModelProvider([...])  # 第一轮返回 file_write 调用，第二轮返回最终文本
    # 用 ApplicationContainer 注入 provider → 绑定 tmp_path 工作区 → 创建 Run
    # → wait_for_run_status(client, run_id, {"waiting_for_approval"})
    # → 调审批接口 approve → wait_for_run_status(..., {"succeeded"})
    assert (tmp_path / "notes.md").read_text(encoding="utf-8") == "hello"
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && uv run pytest tests/test_agent_e2e.py -q`
Expected: FAIL

- [ ] **Step 3: 实现并更新文档**

- 补齐端到端用例（用 `ScriptedModelProvider` 依次返回 `file_write` 调用与最终文本）。
- `backend/.env.example` 增加 4 个 `PRISM_AGENT_KIT_WORKSPACE_*` 配置说明。
- `README.md`「当前能力/当前不包含」更新：加入工作区与文件工具、写入审批；移除"Workspace 不在范围"的旧措辞中与本期冲突的部分。
- `backend/README.md`：新增接口表与工具说明。
- `ui/README.md`：工作区页与审批交互说明。

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && uv run pytest -q && uv run ruff check . && uv run ruff format --check . && uv run mypy src`
Expected: 全部 PASS

Run: `cd ui && pnpm check && pnpm test && pnpm build`
Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add README.md backend/README.md ui/README.md backend/.env.example backend/tests/test_agent_e2e.py
git commit -m "docs: 工作区与文件工具使用说明与端到端验收"
```

---

## Self-Review

**Spec coverage**

| 设计要求 | 任务 |
|---|---|
| 枚举/状态机/错误码/配置 | 1 |
| workspaces 表、runs.workspace_id、FTS 表、索引重建 | 2 |
| 工作区领域模型与仓储 | 3 |
| FTS 检索（含 2 字回退） | 4、17 |
| 路径安全 | 5、8 |
| 绑定/树/读/搜索/目录选择 | 6 |
| 索引器与索引任务生命周期 | 7 |
| 4 个工具与 requires_approval | 8 |
| 结果记录复用 | 9 |
| 引擎审批闸门 | 10 |
| 审批决策、混合轮次、预览 | 11、13 |
| 过期扫描与恢复边界 | 12 |
| HTTP 接口与健康自检 | 13 |
| UI 契约 / 工作区页 / 审批交互 | 14、15、16 |
| 正文脱敏、鉴权、安全边界 | 10（事件 payload）、13（鉴权测试）、16（不渲染正文） |
| 文档与验收 | 17 |

**Review Focus 对位**：2–3 字检索 → Task 4；路径逃逸 → Task 5/8；审批期间切换工作区 → Task 11 的 `test_write_uses_run_workspace_after_switch`；混合轮次 → Task 11 的 `test_mixed_turn_moves_to_waiting_for_tool`；索引中途退出 → Task 7 的 `test_reset_interrupted_marks_failed`。

**类型一致性**：`Workspace.root_path: str`、`WorkspaceService.root_for() -> Path | None`、`ToolExecutionContext.workspace_root: Path | None`、`IndexReport.status: IndexStatus`、`ToolResultRecorder.record(run_id, call_id, ToolExecutionResult)` 在 Task 9/10/11 中一致引用。
