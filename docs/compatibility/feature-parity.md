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
| Health | Verified | Implemented | Pending | Pending | Pending | Java 返回 `workspace_fts=unsupported` |
| Session 创建/列表/查询 | Verified | Implemented | Pending | Pending | Pending | Java 已对齐 snake_case、404 信封、`updated_at DESC, id DESC` |
| Session 工作区绑定 | Verified | Pending | Pending | Pending | Pending | `POST /sessions/{id}/workspace` |
| Run / Message / ToolCall | Verified | Pending | Pending | Pending | Pending | Phase 3a |
| SSE 事件与重放 | Verified | Pending | Pending | Pending | Pending | Phase 3a |
| 取消 / 超时 / 恢复 | Verified | Pending | Pending | Pending | Pending | Phase 3a |
| 上下文裁剪与压缩 | Verified | Pending | Pending | Pending | Pending | Phase 3b |
| 轨迹投影 | Verified | Pending | Pending | Pending | Pending | Phase 3b |
| Model Profile | Verified | Pending | Pending | Pending | Pending | Phase 3b |
| 会话标题生成 | Verified | Pending | Pending | Pending | Pending | Phase 3b |
| Workspace / 文件工具 / 审批 | Verified | Pending | Pending | Pending | Pending | Phase 4 |
| MCP Client | Verified | Pending | Pending | Pending | Pending | Phase 5 |
| Skills | Verified | Pending | Pending | Pending | Pending | Phase 6 |
| 命名工作区（V1.5 扩展） | Not started | Not started | Pending | Pending | Pending | 两端同时实现 |

`Python = Verified` 表示已有语言内测试与运行验证；跨语言一致性仍需 Phase 2 起的契约与 parity 测试证明。
