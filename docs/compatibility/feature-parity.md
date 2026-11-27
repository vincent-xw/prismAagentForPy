# 双后端 Feature Parity 矩阵

状态取值：`Pending` / `Implemented` / `Contract Passed` / `Behavior Passed` / `E2E Passed` / `Known Difference` / `Blocked`。

判定规则：

- `Implemented`：代码存在并有语言内测试，但**尚未**通过跨语言契约测试。
- `Contract Passed`：`tests/contract` 对两端全绿（Phase 2 建立）。
- `Behavior Passed`：`tests/parity` 在同一模型夹具下事件序列/状态机对齐（Phase 3 起）。
- `E2E Passed`：同一套 Playwright 分别跑通两个 UI 地址。
- 不得以"接口返回 200"或"服务能启动"作为完成证据。

## 当前状态（2026-11-27 / Phase 1）

| Feature | Python | Java | API | Behavior | E2E | Notes |
|---|---|---|---|---|---|---|
| Health | Verified | Implemented | **Contract Passed** | Pending | Pending | Java 无 FTS5，`workspace_fts=unsupported`（见 Known Differences） |
| Session 创建/列表/查询 | Verified | Implemented | **Contract Passed** | Pending | **E2E Passed** | 两端契约测试通过（含 401/404 信封）；双 UI 新建会话 |
| Session 工作区绑定 | Verified | Implemented | **Contract Passed** | Pending | Pending | `test_workspaces.py` 绑定用例双端通过 |
| Run / Message / ToolCall | Verified | Implemented | **Contract Passed** | **Behavior Passed** | **E2E Passed** | 文本/工具回环事件序列与消息序列一致；SSE `id` 为全局事件 id |
| SSE 事件与重放 | Verified | Implemented | **Contract Passed** | **Behavior Passed** | **E2E Passed** | 事件序列/重放/终态关流双端一致 |
| 取消 / 超时 / 恢复 | Verified | Implemented | Pending | Pending | Pending | 取消/BUSY 已双端对比；超时/恢复仅 Java 语言内测试 |
| 上下文裁剪与压缩 | Verified | Implemented | Pending | Pending | Pending | `CompactionTest`；token 计数差异按 K-05 不比对 |
| 轨迹投影 | Verified | Implemented | **Contract Passed** | Pending | **E2E Passed** | 契约双端通过；双 UI 轨迹页可见 Turn/Step（行为序列未逐端对比） |
| Model Profile | Verified | Implemented | **Contract Passed** | Pending | Pending | `test_model_profiles.py` 双端通过；密钥只写、只回 `has_key` |
| 会话标题生成 | Verified | Implemented | Pending | Pending | Pending | 依赖模型 Provider，无密钥时仅告警 |
| 上下文使用量展示 | Verified | Implemented | **Contract Passed** | **Behavior Passed** | **E2E Passed** | 预算公式一致、used>0、percent 容差 10；双 UI 输入框下方可见 |
| Workspace / 文件工具 / 权限档位 | Verified | Implemented | **Contract Passed** | Pending | Pending | 文件工具在 parity 工具回环中双端执行成功；权限 UI 未做 E2E |
| MCP Client | Verified | Implemented | **Contract Passed** | Pending | Pending | `test_mcp.py` 双端通过；Java 官方 SDK（stdio + Streamable HTTP） |
| Skills | Verified | Implemented | **Contract Passed** | **Behavior Passed** | **E2E Passed** | 注入消息序列一致；双 UI 技能菜单可见 prism-demo |
| 命名工作区（V1.5 扩展） | Verified | Implemented | **Contract Passed** | Pending | Pending | 同名自动加后缀；`test_workspaces.py` 双端通过 |

`Python = Verified` 表示已有语言内测试与运行验证；跨语言一致性仍需 Phase 2 起的契约与 parity 测试证明。

## Known Differences（刻意差异，不追平）

| 差异 | Python | Java | 原因 |
|---|---|---|---|
| 逐工具审批（K-09） | `approval`/`preview` 端点 + 3 个审批事件 | 不注册；事件总数 24 | 权限档位即策略，已确认不做 |
| 目录选择器 API | `POST /workspaces/pick` | 不注册 | UI 已改为“输入目录”，不再需要原生选择器 |
| 工作区全文检索 | SQLite FTS5（`workspace_fts=ok`） | LIKE/关键字扫描（`unsupported`） | 无 FTS5 依赖；返回结构一致，排序/相关度可能不同 |
| Token 估算器 | tiktoken | jtokkit | 数值允许偏差；契约只断言阈值与相对高低 |

## 容器化状态（Phase 2）

- Compose 五服务在 `192.168.31.90` 全部 healthy：`backend-python`、`backend-java`、`ui-python`、`ui-java`、`mysql-java`。
- 两个 UI 容器使用同一镜像 `prism-agent-ui:dev`，Image ID 一致（`77fc872a1edb`），仅 `API_TARGET` 不同。
- 契约测试：Python 后端 4 passed、Java 后端 4 passed、两个 UI 反代各 4 passed。
- 隔离验证：停掉 `backend-java` 后 Python 后端与 `ui-python` 仍可用；重启后 Java 恢复 healthy。
- 已知差异：Java 的 `workspace_fts` 仍为 `unsupported`（Phase 4 实现索引后改为真实探测）。
