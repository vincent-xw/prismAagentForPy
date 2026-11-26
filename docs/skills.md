# Skills 接入与使用指南（V1.3）

Skills 把可复用的流程、领域知识和配套资料打包成目录，让 Agent 在合适的时机按你的方法做事。本指南覆盖：技能包格式、放置位置、在界面/API 里怎么用、上下文与预算行为、限制与排错。

- 协议基础：遵循 [Agent Skills 规范](https://agentskills.io/specification)（`SKILL.md` + frontmatter）
- 当前版本范围：只读技能包；**不执行 `scripts/`、不做技能作者化、不做技能市场**

## 1. 工作原理（渐进披露）

1. **清单常驻**：每个 Run 的 system prompt 追加一份 `<available_skills>` 清单，只含 `name`、`description`、路径。
2. **正文按需**：
   - 模型判断任务匹配时，调用内置 `skill` 工具加载 `SKILL.md` 正文；
   - 用户在输入框用 `/` 显式选择技能，选中技能的正文只对**下一条消息**注入一次。
3. **资料按需**：`references/` 等文件属于第三层，模型可用 `skill` 工具的 `path` 参数读取，不会一次性塞进上下文。

## 2. 放在哪里（发现规则）

按以下顺序扫描，同名技能**先到先得**，后面的标记为 shadowed 并写日志：

| 优先级 | 目录 |
|---|---|
| 1 | `~/.prism/skills/`（`PRISM_AGENT_KIT_PRISM_HOME` 可改品牌目录） |
| 2 | `~/.agent/skills/` |
| 3 | `~/.agents/skills/`（规范里的复数目录） |
| 4 | `PRISM_AGENT_KIT_SKILLS_PATHS` 中逗号分隔的额外目录（测试/自定义） |

技能目录本身不要用符号链接（会被拒绝）；`SKILL.md` 也不能是符号链接。

## 3. 技能包格式

```text
~/.prism/skills/pdf-tools/
├── SKILL.md                 # 必需
├── references/
│   └── formats.md           # 可选：按需读取的文档
├── scripts/
│   └── extract.sh           # 可选：V1.3 只登记，不执行
└── assets/
    └── template.json        # 可选：只登记元数据
```

`SKILL.md` 必须是 YAML frontmatter + 正文：

```markdown
---
name: pdf-tools
description: Extract text and tables from PDF files. Use when reading, converting, or inspecting PDFs.
---

# PDF tools

Read `references/formats.md` before converting a document.
```

字段要求：

- `name`：`^[a-z0-9]+(?:-[a-z0-9]+)*$`，≤64 字符，建议与目录名一致（不一致只告警）
- `description`：≤1024 字符，写清「做什么 + 什么时候用」，它是模型路由的依据
- 未知字段忽略；非法包不会进入清单，也不影响其他技能

## 4. 快速开始

```bash
mkdir -p ~/.prism/skills/hello-world/references
cat > ~/.prism/skills/hello-world/SKILL.md <<'MD'
---
name: hello-world
description: A minimal demo skill. Use when the user asks to try the hello skill.
---

# Hello world

Reply with "hello from skill" and list the resources you see.
MD

echo "# Notes" > ~/.prism/skills/hello-world/references/notes.md
```

然后：

```bash
curl -s http://127.0.0.1:8000/api/v1/skills \
  -H "Authorization: Bearer $PRISM_AGENT_KIT_API_TOKEN" | jq
```

能看到 `hello-world` 即接入成功。

## 5. 在会话里使用

### 显式选择（推荐，确定性）

1. 在输入框输入 `/`，弹出技能菜单；继续输入过滤（如 `/pdf`）。
2. `↑/↓` 移动，`Enter`/`Tab` 选中，`Esc` 关闭；选中后 `/xxx` 会从输入框删除，上方出现 `◈ 技能名 ×` 标签。
3. 输入你的请求并发送：本条消息会携带该技能正文；发送成功后标签清除。

要点：

- 只对**下一条消息**注入正文；后续消息不再重复注入，但技能正文作为 `skill_context` 消息留在会话历史里，模型仍然"记得"。
- 历史里会多一条居中的「已加载技能：xxx」记录，可展开看全文，不会显示成你的发言。
- 该消息受上下文裁剪保护：历史再长也不会被裁掉；只有它本身超出预算时才会报 `CONTEXT_BUDGET_EXCEEDED`。

### 隐式触发

模型看到清单后，若判断任务匹配某个 `description`，会主动调用 `skill` 工具：

```json
{"name": "pdf-tools"}                    // 加载正文
{"name": "pdf-tools", "path": "references/formats.md"}  // 读取资源
```

工具只读、不需要审批；未知技能返回 `SKILL_NOT_FOUND`。

## 6. 通过 API 使用

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/v1/skills` | 技能清单（含 shadowed 标记） |
| GET | `/api/v1/skills/{name}` | 正文 + 资源清单 |
| POST | `/api/v1/sessions/{id}/runs` | 请求体可带可选 `skill_name`，未知技能返回 422 且不创建 Run |

```bash
curl -s -X POST "http://127.0.0.1:8000/api/v1/sessions/$SESSION_ID/runs" \
  -H "Authorization: Bearer $PRISM_AGENT_KIT_API_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"input":"整理这份 PDF","skill_name":"pdf-tools"}'
```

## 7. 预算与限制

| 项 | 默认 | 说明 |
|---|---|---|
| 清单预算 | `PRISM_AGENT_KIT_SKILLS_CATALOG_MAX_CHARS=8000` | 超出先把 description 截到 200，再按名称省略并标注「已省略 N 个技能」 |
| 显式注入正文 | `PRISM_AGENT_KIT_SKILLS_MAX_CONTEXT_CHARS=20000` | 超出截断并附「技能正文已截断」 |
| `skill` 工具结果 | `PRISM_AGENT_KIT_SKILLS_MAX_TOOL_RESULT_CHARS=60000` | 超出截断并带 `truncated: true`；资源列表最多 50 条 |
| 单资源文件 | 200 KB | 必须是 UTF-8 文本；二进制/超大文件拒绝 |

## 8. 安全边界

- Skill 内容是**不可信本地内容**：只读取，不执行脚本、不自动上传资源；安装前请审查来源。
- 拒绝路径逃逸（`..`、绝对路径）与符号链接越界。
- `skill` 工具只读、免审批；它不会写文件、不会访问网络。
- 与 MCP 的区别：**MCP 提供工具（能做什么），Skills 提供方法（怎么做）**；两者可以组合使用。

## 9. 配置项

都在 `backend/.env`，前缀 `PRISM_AGENT_KIT_`：

```bash
PRISM_AGENT_KIT_PRISM_HOME=~/.prism
PRISM_AGENT_KIT_SKILLS_PATHS=
PRISM_AGENT_KIT_SKILLS_CATALOG_MAX_CHARS=8000
PRISM_AGENT_KIT_SKILLS_MAX_CONTEXT_CHARS=20000
PRISM_AGENT_KIT_SKILLS_MAX_TOOL_RESULT_CHARS=60000
```

## 10. 排错

| 现象 | 排查 |
|---|---|
| `/` 菜单里没有技能 | 路径是否在 §2 的目录；`SKILL.md` frontmatter 是否合法；`GET /skills` 看 `shadowed`（被同名高优先级技能遮蔽） |
| 技能不生效 | 看后端日志 `跳过非法技能 ...`；确认 `name` 与 `description` 非空、名字格式合法 |
| `SKILL_NOT_FOUND` | 名称必须与 frontmatter 的 `name` 完全一致（不是目录名） |
| `CONTEXT_BUDGET_EXCEEDED` | 技能正文过大或被截断后仍超窗口；减小 `SKILL.md` 或调大 `MODEL_CONTEXT_WINDOW` |
| 409/网络失败后标签消失 | 当前实现发送失败时保留草稿与标签，可直接重试 |
| `/docs` 401 | 非生产环境已放行；生产环境访问文档仍需 Token |
