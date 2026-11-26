# PrismAgentKit Skills 设计（V1.3）

- 状态：待评审
- 日期：2026-11-26
- 关联：MCP Client 设计（V1.2）；上游参考 `agent-runtime-bff` 的 `skill-*` 模块与 DSH 的 `@deepseek-ai/dsh-skill` / `dsh-tool-skill` / `dsh-skill-filesystem`
- 外部依据：Anthropic Agent Skills 工程博客、Pi skills 文档、OpenAI Codex skills 文档（对比见 §2）

## 0. 已确认的结论

- V1.3 做**全套**：清单常驻 + `skill` 工具隐式加载 + 输入框 `/` 显式选择并高亮。
- 显式选中的技能只对**下一条消息**生效，但正文作为一条**持久化上下文消息**写入会话历史，后续轮次靠历史连续，不重复注入全文。
- 技能目录：自己的 `~/.prism/skills/`（品牌目录名待定，先可配置）+ 通用 `~/.agent/skills/`；并兼容规范里的 `~/.agents/skills/`。
- 采用 Claude/DSH 一致的渐进披露：清单只放 name/description（+路径），正文按需加载；`references/` 属于第三层，按需读取。

## 1. 背景与意图

V1.2 让 Agent 能接外部 MCP 工具，但它仍然"只会做事，不会按你的方法做事"。Skills 把可复用的流程与领域知识打包成目录（`SKILL.md` + 可选 references/scripts/assets），让 Agent 在合适时机加载并遵循。

四家实现（§2）已经收敛出共同形态，本项目按"实验 Runtime"的定位对齐这套形态，而不是自创一套。

## 2. 四家实现对比（设计依据）

| | 清单常驻 | 正文加载 | 显式触发 | 隐式触发 | 目录 |
|---|---|---|---|---|---|
| Claude（Anthropic 博客） | 启动时 system prompt 注入 name+description | 模型判断相关时读 `SKILL.md`；更深层文件按需读 | `@` 技能 | 是 | 个人/项目/插件（Claude Code：`~/.claude/skills`、`.claude/skills`） |
| DSH（源码） | 每会话发布 `skill-catalog`（name+截断 description） | `skill` 工具按名加载；或用户消息首行 `/<name>` 确定性识别后以 `<skill_content>` 注入 instructions | `/<name>`（只认 user 来源） | 是（catalog + `skill` 工具） | 项目 `.dsh/skills`、`.agents/skills`；用户 `~/.dsh/skills`、`~/.agents/skills`；bundled；带监听 |
| Pi（docs） | 启动注入 name+description+路径 | 模型按路径读；`/skill:name` 强制加载 | `/skill:name`，参数追加为请求 | 是 | 用户/项目目录 + `~/.agents/skills`、`.agents/skills` |
| Codex（docs） | 清单含 name+description+路径，默认≤2% 上下文（未知 8000 字符，上限 1 万 token），超限截 description/省略并告警 | 选中后读全文 | `/skills`、`$` 提及 | 是 | `.agents/skills`（cwd→repo root）、`$HOME/.agents/skills`、`/etc/codex/skills`、bundled |

共同结论：**渐进披露是核心**；正文进入历史一次即可连续；清单必须有长度预算；显式触发要做确定性解析。

## 3. 目标

1. 发现并解析技能包：`SKILL.md`（YAML frontmatter + 正文），支持 `references/`、`scripts/`、`assets/` 目录。
2. 会话每个 Run 的 system prompt 追加技能清单（name、description、路径），按预算截断。
3. 提供 `skill` 内置工具：按 name 加载正文；带 `path` 时读取该技能下的文本资源（渐进披露第三层）。
4. 输入框 `/` 弹菜单：列出可用技能（name + description），支持键入过滤、上下键/回车/点击选择、Esc 关闭。
5. 选中技能在输入框上方以**高亮标签**呈现（可点 × 清除），发送时随 Run 传递。
6. 显式选中的技能正文作为 `skill_context` 消息写入会话历史（只写一次），UI 以一条可折叠的"已加载技能"标记展示。
7. 技能包对用户可见：`GET /skills` 列表、`GET /skills/{name}` 读取详情供 UI 预览。
8. 全链路不执行技能内脚本（V1.3 明确不做执行）；不做作者化生成。

## 4. 非目标

- 不做技能的自然语言创建/编辑/删除（作者化流程留后续版本）。
- 不执行 `scripts/`、不自动上传 `assets/`（只做文本读取与清单）。
- 不做 Workflow 里的 `call_skill`（Workflow 未迁移）。
- 不做项目级目录（`.agent/skills`）、不做目录监听热更新（V1.3 每次请求现扫，性能足够）。
- 不做多技能同时显式选择（一次消息最多一个显式技能；隐式可由模型调多次 `skill`）。
- 不做技能市场/安装器。

## 5. 反目标

- 每轮都把技能正文塞进 system prompt（浪费上下文，且与"只生效一次"语义冲突）。
- 让模型自己拼路径去读 `~/.prism`（工作区外，读不到，也不安全）。
- 把 `/` 当成纯前端字符串替换就发送（后端不知道选中了哪个技能，无法审计、无法注入）。
- 执行技能内脚本或把二进制资源写进消息历史。
- 清单无限增长挤爆上下文。

## 6. 约束

- Python 3.12；SQLite 唯一数据库；结构变更带迁移（`20261126_0006_skill_context`）。
- 只读取文本资源，单文件 ≤ 200 KB；拒绝路径逃逸与符号链接越界。
- 清单预算：`skills_catalog_max_chars` 默认 8000，超出按 description 截断、随后按 name 排序省略并告警。
- `skill` 工具返回体预算：`skills_max_tool_result_chars` 默认 60_000 字符，超出截断并附 `truncated: true`（资源单文件仍限 200 KB）。
- 显式注入正文预算：`skills_max_context_chars` 默认 20_000 字符，超限截断并附 `（技能正文已截断）`，避免单条受保护消息永久撑爆会话预算。
- frontmatter 按 YAML 解析（PyYAML），支持 `description: |` 多行；拒绝符号链接技能目录/SKILL.md。
- 名称规范：`^[a-z0-9]+(?:-[a-z0-9]+)*$`，≤64 字符；description ≤1024。
- 技能根目录优先级（同名先到先得，后者记为 shadowed）：`~/.prism/skills` → `~/.agent/skills` → `~/.agents/skills` → 额外 `skills_paths`（逗号分隔，用于测试/自定义）。
- 前端契约运行时校验（zod），不补造字段。

## 7. 方案选择

### 7.1 正文如何"只生效一次但持续存在"

| 方案 | 取舍 |
|---|---|
| **A. 持久化上下文消息（选中）** | 选中技能的 Run 写入一条 `messages.kind='skill_context'`（role=user），正文进历史；后续轮次自然连续；UI 要按 kind 过滤展示。与 Claude/DSH 的实际做法一致 |
| B. 会话技能状态 + 每轮摘要引用 + `skill_read` 工具回读 | 历史干净，但模型常常不回读，技能质量打折；多一套状态与工具 |
| C. 前端把正文拼进用户消息 | 无后端改动但语义脏、不可审计，排除 |

### 7.2 隐式加载的载体

`skill` 内置工具（DSH 同款）：`{name, path?}` → 正文或资源文本。工具结果本身落工具消息，天然进入历史。另一种"让模型用现有 `file_read` 读"不可行，因为技能在工作区外。

### 7.3 显式触发的位置

只识别 `/` 开头并选中技能的前端状态，**由前端把技能的 name 作为 Run 参数传给后端**，后端做确定性注入；不在后端解析自然语言里的 `/` 文本（避免伪造与歧义）。

## 8. 总体设计

```text
UI MessageComposer
  ├─ 输入 "/" → GET /skills → 菜单（name+description）
  └─ 选中 → 标签 chip；发送时 POST /sessions/{id}/runs {input, skill_name}
        │
application/skills/
  ├── catalog.py     发现 + 解析 + 缓存快照 + 清单渲染（预算）
  ├── package.py     SKILL.md frontmatter/正文、资源读取（路径安全）
  └── tools.py       skill 内置工具（load / read resource）
        │
RunService.create
  ├─ system_prompt = prompt.content + catalog.render()
  ├─ 若 skill_name → 校验并写 kind='skill_context' 的 Message（在 user 消息之前）
  └─ Run.skill_name 记录（审计）
        │
engine（不改状态机）：正常组装历史，skill_context 与工具结果自然进入上下文
```

### 8.1 技能包格式

```text
~/.prism/skills/pdf-tools/
├── SKILL.md
├── references/formats.md
├── scripts/extract.sh     # V1.3 只登记存在，不执行
└── assets/template.json
```

`SKILL.md`：
```markdown
---
name: pdf-tools
description: Extract text and tables from PDF files. Use when reading or converting PDFs.
---
# PDF tools
Read `references/formats.md` before converting.
```
- 必填 `name`、`description`；可选 `license`、`metadata`（忽略未知字段，给 warning）。
- `name` 必须与目录名一致？不强制，但不一致记 warning（Pi 同款策略），工具以 frontmatter name 为准。
- 解析失败/非法字段：该技能不进入清单，日志 warning（不阻断其他技能与启动）。

### 8.2 清单渲染

```
<available_skills>
- pdf-tools: Extract text and tables from PDF files. Use when reading or converting PDFs. (path: /Users/x/.prism/skills/pdf-tools)
</available_skills>
```
- 追加到每次 Run 的 system prompt；总长 ≤ `skills_catalog_max_chars`。
- 超预算：先把 description 截到 200 字符；仍超则按 name 排序截断列表，并在末尾注明 `（已省略 N 个技能）`，同时写日志。

### 8.3 `skill` 工具

- 名称：`skill`；`execution_mode=LOCAL`；`requires_approval=False`（只读）。
- 输入：`{name: str, path?: str}`；输出：`{content: str, resources: [{path, kind, bytes}]}`。
- `path` 为空 → 返回 SKILL.md 正文；`path` 指定 → 读取该技能目录下文本资源（≤200 KB，UTF-8，拒绝越界/二进制）。
- 未知技能 → `SKILL_NOT_FOUND`；读取越界 → `SKILL_PATH_INVALID`；过大 → `SKILL_RESOURCE_TOO_LARGE`。
- 返回正文按 `skills_max_tool_result_chars` 截断（`truncated` 标记），避免单次工具结果把上下文预算打爆。
- 返回内容包在 `<skill_content name="...">...</skill_content>`，正文原样。

### 8.4 显式注入

- `RunCreate` 增加可选 `skill_name`。
- `RunService.create`：若提供，先 `catalog.get(name)` 校验；在同一事务里**先写** `kind='skill_context'` 的 `Message`（role=user，content=渲染后的 `<skill_content>`，`metadata` 记录 name/根目录），**再写**用户消息；`Run.skill_name=name`。
- 后续 Run 不自动重复注入；历史里的 `skill_context` 消息会参与上下文组装。
- 若该会话历史里已存在同名 `skill_context`，仍允许再次显式加载（用户可能想刷新正文），但 UI 会显示新的一条；正文重复一次是用户显式选择的结果。
- **上下文裁剪保护**：`ContextAssembler._build_units` 将 `kind='skill_context'` 的消息标记为**受保护单元**，裁剪时只允许移除其他更旧的单元，绝不先裁掉技能正文；若仅剩受保护单元 + 当前用户消息仍超预算，按现有 `CONTEXT_BUDGET_EXCEEDED` 处理（与 §15 一致）。新增 context 层测试覆盖：大正文 + 长历史时不丢技能、超预算时报错。

### 8.5 UI

- `/` 触发与过滤：光标在行首或空白后输入 `/` 时弹出菜单；**过滤串保留在 textarea 内**（如 `/pdf`），菜单随输入实时过滤；**不把过滤串替换成任何文本**。
- 键盘优先级（`MessageComposer` 的 keydown 里先于"Enter 发送"处理）：
  - 菜单打开时：`↑/↓` 移动高亮，`Enter`/`Tab` 选中当前项（`preventDefault`，不发送），`Esc` 关闭菜单且保留文本，点击也可选中；
  - 无匹配项时 `Enter` 只关闭菜单、不发送；
  - 菜单关闭后 Enter 才走原有发送逻辑（含 IME `isComposing` 判定）。
- 选中时：从 textarea 中**删除整段 `/过滤串`**（按记录的起始位置精确删除，不改动其余草稿），输入框上方出现 chip（如 `◈ pdf-tools ×`）并保持聚焦；再次输入 `/` 可更换技能；点 × 清除 chip 但不动草稿。
- 发送：`conversation.send(text, skillName)` 携带 chip 的技能名；成功后清 chip、清草稿；失败（409/网络）保留 chip 与草稿以便重试。
- 消息列表：`kind='skill_context'` 渲染为居中的淡色"已加载技能：<name>"，可展开查看全文（只读），不显示为用户气泡；`MessageView` 与 `contracts.ts` 的 `messageSchema` 同步加 `kind`（zod 非 passthrough，缺失会被丢弃）。
- 消息列表：`kind='skill_context'` 渲染为一条居中的淡色"已加载技能：pdf-tools"，点击可展开全文（只读），不显示为用户发言气泡。
- 技能菜单数据来自 `GET /skills`；获取失败时 `/` 提示"技能列表不可用"，不阻断普通发送。

## 9. 数据模型与迁移

- `messages` 增加 `kind TEXT NOT NULL DEFAULT 'text'`（`text` | `skill_context`）。
- `runs` 增加 `skill_name TEXT NULL`。
- 迁移 `20261126_0006_skill_context`：两条 `ALTER TABLE ... ADD COLUMN`，downgrade 对应删除。
- 不需要技能表：技能是磁盘文件，每次请求扫描（目录不大）；清单可进程内缓存 5 秒。

## 10. HTTP 接口

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/skills` | `{items: [{name, description, path, root, shadowed}]}`（已按预算排序，返回完整列表供 UI 过滤） |
| GET | `/skills/{name}` | `{name, description, content, resources: [{path, kind, bytes}]}`；未知 404 `SKILL_NOT_FOUND` |

`POST /sessions/{id}/runs` 请求体增加可选 `skill_name`；未知技能返回 422 `SKILL_NOT_FOUND`（不创建 Run）。

## 11. 错误码

`SKILL_NOT_FOUND`、`SKILL_INVALID`、`SKILL_PATH_INVALID`、`SKILL_RESOURCE_TOO_LARGE`、`SKILL_CATALOG_UNAVAILABLE`。

## 12. 测试

- 解析/发现：合法包、缺 frontmatter、name 非法、description 超长、目录名不一致 warning、坏包不阻塞其他包。
- 根目录优先级：三个目录同名 → `~/.prism` 优先，其余 shadowed。
- 清单预算：超长截断与省略告警；空目录不产生 block。
- `skill` 工具：正文加载、资源读取、路径逃逸拒绝、超大拒绝、未知技能错误码。
- 显式注入：`skill_context` 消息写在 user 消息前；只写一次；后续 Run 不重复；Run.skill_name 落库；未知 name 422 且不建 Run。
- UI：`/` 菜单过滤与键盘选择（含 Enter 不误发送、Esc 保留文本）、过滤串删除、chip 渲染/清除、发送携带 skill_name、skill_context 消息展示与默认过滤。
- 上下文：受保护单元不被裁剪；仅剩受保护单元仍超预算时报 `CONTEXT_BUDGET_EXCEEDED`；`skill` 工具结果截断。
- e2e：真实技能目录 → `/` 选择 → Run → 模型收到正文 → 第二个 Run 不再重复但历史仍在。

## 13. 阶段划分

1. **内核**：`package.py`/`catalog.py`、配置项、错误码、`GET /skills`、迁移（kind/skill_name）。
2. **工具**：`skill` 工具 + 资源读取安全 + 清单渲染接入 RunService。
3. **显式注入**：RunCreate.skill_name、事务内注入、Run 审计字段、API 错误。
4. **UI**：`/` 菜单、chip、skill_context 消息、契约与测试。
5. **验收**：集成/e2e、文档、版本 1.3.0。

工作量估计：后端 900–1200 行（含测试），UI 500–700 行。

## 14. 留待构建者决定

- 清单缓存的具体实现（TTL 5s vs mtime 快照）。
- `/` 菜单的匹配排序（前缀优先 vs 描述命中）。
- skill_context 消息在消息列表中的折叠默认态。
- 资源读取是否支持图片（V1.3 仅文本）。

## 15. 风险

- 技能目录在用户 HOME，权限/符号链接异常：发现阶段必须隔离失败目录，不阻断启动。
- 正文注入使首条消息上下文变大：清单有预算、正文按需，但显式全文仍可能很大；超过上下文预算时按现有 `CONTEXT_BUDGET_EXCEEDED` 处理，并在 UI 提示。
- 前端键位与中文输入法冲突：`/` 菜单与 IME 组合态需要判定 `isComposing`。
- 技能内容不可信：只读、不执行、不自动信任脚本；文档明确提示审查来源。

---

## 附：改动清单

- `backend/src/prism_agent_kit/core/{enums,errors,config,models}.py`：`MessageKind`、错误码、`skills_*` 配置、`Message.kind`/`Run.skill_name`。
- `db/models.py`、`db/mappers.py`、`db/repositories/messages.py`、`migrations/versions/20261126_0006_skill_context.py`。
- `application/skills/{catalog,package,tools}.py`；`application/run_service.py`（清单与注入）；`application/container.py`（装配与工具注册）。
- `api/routes/skills.py`、`api/schemas.py`、`api/router.py`、`api/routes/runs.py`（skill_name）。
- `ui/src/features/skills/{skills.ts,SkillMenu.vue}`、`features/sessions/{MessageComposer,SessionPage,MessageList,conversation}.ts/vue`、`lib/api/{contracts,client}.ts`。
- 测试：`backend/tests/application/skills/*`、`tests/api/test_skills.py`、`ui/tests/unit/skills*.test.ts`。
