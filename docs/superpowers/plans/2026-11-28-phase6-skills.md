# Phase 6 实施计划：Skills（Java 对齐 + 运行期注入）

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Java 实现只读技能目录、`/skills` 契约、Run `skill_name` 注入与 `skill` 工具，并用共享示例技能做双端验收。

**Architecture:** `core/skills` 负责扫描/解析/缓存/渲染；`RunService` 在创建 Run 时注入 `skill_context`；`LocalToolInvoker` 增加 `skill` 分支按需读资源。目录为共享只读挂载，两端各自扫描。

**Tech Stack:** Spring Boot 3.5 / SnakeYAML、MyBatis-Plus；Python 作为行为基线；契约 pytest。

**Spec:** `docs/superpowers/specs/2026-11-28-phase6-skills-design.md`

## Global Constraints

- 错误码以 Python 为准：技能包错误 400（`SKILL_INVALID`/`SKILL_PATH_INVALID`/`SKILL_RESOURCE_TOO_LARGE`/`SKILL_NOT_FOUND`）；Run 创建未知技能 422 `SKILL_NOT_FOUND`；目录不可用 503 `SKILL_CATALOG_UNAVAILABLE`。
- 技能名 `^[a-z0-9]+(?:-[a-z0-9]+)*$` ≤64；description 非空 ≤1024。
- 资源只扫 `references/`、`scripts/`、`assets/`（递归），`kind` = 子目录名。
- 清单 8000 字符预算，先截 description 到 200，再整条丢弃并追加 `（已省略 N 个技能）`。
- 注入：`<skill_content name="...">body</skill_content>`，上限 20000 字符，超限追加 `（技能正文已截断）`。
- `skill` 工具上限 60000 字符；资源 ≤204800 字节。
- 缓存 5 秒；同名先到先得，后项 `shadowed=true`。

## Review Focus

1. **路径穿越**：`/skills/{name}` 的资源读取出现 `..` 或绝对路径 —— Task 1/4。
2. **同名遮蔽**：后出现的同名技能覆盖了先出现的 —— Task 1。
3. **注入顺序**：`skill_context` 必须排在 user 消息之前 —— Task 3。
4. **清单预算**：超 8000 后没有省略提示或直接截断半条 —— Task 1。
5. **分发错路**：`skill` 被工作区执行器接走 —— Task 4。

---

### Task 1: Java 技能目录核心

**Files:** `core/skills/{SkillSummary,SkillResource,SkillPackage,Frontmatter,SkillCatalog}.java`、`config/PrismProperties.java`、`pom.xml`（snakeyaml）、`src/test/java/com/prism/agent/core/skills/SkillCatalogTest.java`

**Interfaces:**
- `SkillCatalog(List<Path> roots, int maxChars, double cacheSeconds)`；`list()`, `winners()`, `get(name)`, `renderCatalog()`
- `SkillSummary(name, description, path, root, shadowed)`
- `SkillPackage(name, description, body, resources, directory)`
- 根目录：`${prism.skills.prism-home}/skills`、`~/.agent/skills`、`~/.agents/skills`、`prism.skills.paths`

- [ ] **Step 1: 写失败测试**：frontmatter 正常/缺闭合/非法名；同名遮蔽；清单预算省略；资源只收三个子目录
- [ ] **Step 2: 运行确认失败**
- [ ] **Step 3: 实现**：手写 frontmatter 切分 + SnakeYAML 只取 name/description；`Files.walk` 资源；5s 缓存
- [ ] **Step 4: 运行确认通过**：`./mvnw -Dtest=SkillCatalogTest test`
- [ ] **Step 5: 提交** `git commit -am "feat(java): 只读技能目录扫描与清单渲染"`

### Task 2: `/skills` API

**Files:** `api/dto/SkillViews.java`、`api/controller/SkillController.java`、`application/service/SkillService.java`、`src/test/java/com/prism/agent/api/SkillsApiTest.java`

**Interfaces:**
- `GET /skills` → `{items:[{name,description,path,root,shadowed}]}`
- `GET /skills/{name}` → `{name,description,content,resources:[{path,kind,bytes}]}`
- 未找到 → 400 `SKILL_NOT_FOUND`

- [ ] **Step 1: 写失败测试**：列表含示例技能、详情正文、未知 404→400 断言
- [ ] **Step 2-4: TDD 实现并跑绿**
- [ ] **Step 5: 提交**

### Task 3: Run 注入

**Files:** `application/service/RunService.java`、`src/test/java/com/prism/agent/application/RunSkillInjectionTest.java`

**Interfaces:**
- `RunService.create(..., skillName)`：校验 → 渲染清单进 system prompt → 事务内先写 `skill_context` 再写 user 消息
- `MessageKind.SKILL_CONTEXT` 已存在

- [ ] **Step 1: 写失败测试**：带 skillName 创建 Run 后消息顺序 `[skill_context, user]`，正文含 `<skill_content`；未知技能 422
- [ ] **Step 2-4: TDD 实现并跑绿**
- [ ] **Step 5: 提交**

### Task 4: `skill` 工具与分发

**Files:** `tools/SkillTool.java`、`tools/LocalToolInvoker.java`、`src/test/java/com/prism/agent/tools/SkillToolTest.java`

**Interfaces:**
- 工具 `skill`（LOCAL，免审批）：`{name, path?}` → `{content, truncated, resources?}`
- 越界/`..`/绝对路径 → 400 `SKILL_PATH_INVALID`

- [ ] **Step 1: 写失败测试**：读正文、读 references、越界拒绝
- [ ] **Step 2-4: TDD 实现并跑绿**
- [ ] **Step 5: 提交**

### Task 5: 契约与示例技能验收

**Files:** `tests/contract/test_skills.py`、`docker-compose.yml`（backend-java 增加 `PRISM_PRISM_HOME=/skills`、预算 env）

- [ ] **Step 1: 契约用例**：列表含 `prism-demo`、详情含正文与 `references/checklist.md`、未知技能 400
- [ ] **Step 2: 双端跑** `pytest test_skills.py -q`
- [ ] **Step 3: 快照无变化**（Python 已有路径），确认 `RunCreate` 的 `skill_name` 已在快照
- [ ] **Step 4: 提交**

### Task 6: 部署与 E2E

- [ ] **Step 1: 重建镜像并部署**（示例技能已在镜像挂载 `skills/` 中）
- [ ] **Step 2: 两端 E2E**：`GET /skills` 出现 `prism-demo` → UI 选择技能创建 Run → 消息里有 `skill_context` → 模型回复符合技能要求
- [ ] **Step 3: 全量门槛**：Python `pytest/ruff/mypy`、Java `verify`、UI `check/test/build`
- [ ] **Step 4: parity 更新** Skills 行 → Contract Passed
- [ ] **Step 5: 提交**

## 自检

- 覆盖 spec §3（目录）、§4（注入）、§5（工具）、§7（测试）；错误码与 Python 对齐。
- Review Focus 五条分别落到 Task 1/3/4。
- 复用现有 UI（`SkillMenu`、`skillsSchema`、`createRun(skill_name)`），不改 UI 代码。
