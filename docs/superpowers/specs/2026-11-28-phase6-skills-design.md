# Phase 6 设计：Skills（Java 对齐只读技能包与运行期注入）

- 状态：待评审
- 日期：2026-11-28
- 参考实现：`backend/src/prism_agent_kit/application/skills/*`、`api/routes/skills.py`、`run_service.py` 的技能注入段
- 已确认：方案 A（全量对齐：列表/详情 + 运行期注入 + 资源读取）

## 1. 目标

1. Java 实现 `GET /skills`、`GET /skills/{name}`，字段与 Python 完全一致。
2. 扫描只读技能目录（`SKILL.md` frontmatter + 附件资源），多根目录优先级与同名 `shadowed` 规则一致。
3. Run 创建支持 `skill_name`：校验技能 → 生成 `skill_context` 消息注入模型上下文；system prompt 追加 `<available_skills>` 清单。
4. 注册 `skill` 本地工具：按需加载技能正文或单个文本资源（只读、防越界、限 60k 字符）。
5. UI 复用现有 `SkillMenu` / 技能页，无需新增页面。

## 2. 非目标

- 不执行技能 scripts（V1.3 边界）、不做技能市场、不做写入/生成、不做项目级技能目录。

## 3. 数据与规则（对齐 Python）

### 3.1 根目录（按优先级，前者覆盖后者）

1. `<PRISM_HOME>/skills`（容器内 `PRISM_PRISM_HOME=/skills` → `/skills/skills`，与 Python 现有行为一致）
2. `~/.agent/skills`
3. `~/.agents/skills`
4. `PRISM_SKILLS_PATHS` 逗号分隔的追加目录

缓存 5 秒；扫描失败的目录只告警不失败。

### 3.2 `SKILL.md` 解析

- 必须存在、非符号链接；首行 `---` 起 frontmatter，第二个 `---` 结束；YAML 必须是映射。
- `name`：`^[a-z0-9]+(?:-[a-z0-9]+)*$` 且 ≤64；`description`：非空、≤1024 字符。
- 正文 = frontmatter 之后的 trim 内容。
- 资源：只扫描 `references/`、`scripts/`、`assets/`（递归），记录 `{path, kind, bytes}`；`kind` = 子目录名（references/scripts/assets），与 Python 一致。

### 3.3 同名处理

按根目录顺序先到先得；后出现的同名技能标记 `shadowed: true` 仍然返回；`get(name)` 只取未遮蔽项，未找到 → `SKILL_NOT_FOUND(404)`。

### 3.4 清单渲染（system prompt）

```
<available_skills>
- <name>: <description> (path: <绝对路径>)
</available_skills>
```
按 name 排序；超 8000 字符时先把 description 截到 200 再重渲染；仍超则丢弃整条并追加 `（已省略 N 个技能）`（与 Python 一致）。

## 4. 运行期注入

创建 Run 时若 `skill_name` 非空：

1. `SkillCatalog.get` 校验；失败时**保留 Python 的错误码**并统一 422（如未知技能 → `SKILL_NOT_FOUND`，details 带 `skill_name`）；目录不可用 → 503 `SKILL_CATALOG_UNAVAILABLE`。
2. system prompt 追加清单（若存在技能）。
3. 事务内先写一条 `kind=skill_context`、`role=user` 的消息：
   `<skill_content name="{name}">\n{body}\n</skill_content>`，超 20000 字符截断并追加 `（技能正文已截断）`；
4. 再写用户输入消息与 Run（`runs.skill_name` 落库）。
5. Java 的 `RunCreateRequest` **已有** `skillName`（Phase 3 落库），这里只需接上校验与注入；`RunView` 不新增字段（与 Python 一致）。

## 5. `skill` 工具

- 名称 `skill`，`ExecutionMode.LOCAL`，`requires_approval=false`。
- 入参 `{name: string, path?: string}`；无 `path` 返回正文 + 资源清单（前 50 条）；有 `path` 读取单个文本资源。
- 输出 `{content, truncated, resources?}`，上限 60000 字符。
- 资源路径必须落在技能目录内（`resolve` 后校验），拒绝绝对路径与 `..`；越界/不存在/非文本 → 400 `SKILL_PATH_INVALID`/`SKILL_INVALID`；>204800 字节 → 400 `SKILL_RESOURCE_TOO_LARGE`（Python 技能包错误统一 400）。
- Java 分发改动：`LocalToolInvoker` 增加 `skill` 分支（`mcp__` → MCP，`skill` → 技能工具，其余 → 工作区文件工具）。

## 6. Java 落点

| 组件 | 说明 |
|---|---|
| `core/skills/{SkillSummary,SkillPackage,SkillResource,SkillCatalog}.java` | 扫描/解析/缓存/渲染 |
| `core/skills/Frontmatter.java` | 手写 frontmatter 切分 + SnakeYAML 解析（只取 `name`/`description`） |
| `application/service/SkillService.java` | 视图组装与错误映射 |
| `api/controller/SkillController.java` | 两个端点 |
| `application/service/RunService.java` | `skill_name` 校验 + skill_context 注入 |
| `tools/SkillTool.java` + `LocalToolInvoker` | 运行时按需加载 |
| `config/PrismProperties` | `prism-home`、`skills.paths`、预算三个数值；`docker-compose.yml` 给 backend-java 补 `PRISM_PRISM_HOME=/skills` 与三个预算 env |

依赖：`org.yaml:snakeyaml:2.4`（显式声明；Spring Boot 已传递但避免隐式）。

## 7. 契约与测试

- 快照：`/skills`、`/skills/{name}`、`RunCreate.skill_name` Python 已存在，v1.5 只补 Java 实现，无字段变更。
- Java 单元：frontmatter 解析、同名遮蔽、清单预算、资源越界。
- Java API：列表/详情、未知技能 404、状态字段；Run 创建带 skill_name 产生 `skill_context` 消息（stub provider）。
- 契约：`tests/contract/test_skills.py`（双端列表字段、详情正文、未知 404）。
- E2E：仓库内放一个示例技能目录挂载 `/skills`，在 UI 选择技能创建 Run，模型回复可见 `<skill_content>` 生效。

## 8. 错误码（以 Python 为准）

| 场景 | 状态码 | code |
|---|---|---|
| 技能包解析/路径/过大/非 UTF-8 | 400 | `SKILL_INVALID` / `SKILL_PATH_INVALID` / `SKILL_RESOURCE_TOO_LARGE` |
| `/skills/{name}` 未找到 | 400 | `SKILL_NOT_FOUND` |
| 创建 Run 引用未知技能 | 422 | `SKILL_NOT_FOUND`（details.skill_name） |
| 技能目录未装配 | 503 | `SKILL_CATALOG_UNAVAILABLE` |

## 9. 已知差异

- Python 技能根含 `~/.agent|.agents/skills` 历史目录；Java 照抄，容器内实际只有 `/skills/skills`。
- 技能 scripts 不执行（V1.3 边界），两端一致。
