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
| Health | Verified | Implemented | **Contract Passed** | Pending | Pending | 两端契约测试通过；Java 返回 `workspace_fts=unsupported` |
| Session 创建/列表/查询 | Verified | Implemented | **Contract Passed** | Pending | Pending | 两端契约测试通过（含 401/404 信封） |
| Session 工作区绑定 | Verified | Pending | Pending | Pending | Pending | `POST /sessions/{id}/workspace` |
| Run / Message / ToolCall | Verified | Implemented | **Contract Passed** | Pending | Pending | `tests/contract/test_runs.py`（无模型密钥时跳过模型场景） |
| SSE 事件与重放 | Verified | Implemented | **Contract Passed** | Pending | Pending | 事件 seq/重放/终态关流已双端验证 |
| 取消 / 超时 / 恢复 | Verified | Implemented | Pending | Pending | Pending | Java 语言内测试覆盖取消/恢复/过期 |
| 上下文裁剪与压缩 | Verified | Implemented | Pending | Pending | Pending | `CompactionTest`；token 计数差异按 K-05 不比对 |
| 轨迹投影 | Verified | Implemented | **Contract Passed** | Pending | Pending | `tests/contract/test_trajectory.py` 双端通过 |
| Model Profile | Verified | Implemented | **Contract Passed** | Pending | Pending | `test_model_profiles.py` 双端通过；密钥只写、只回 `has_key` |
| 会话标题生成 | Verified | Implemented | Pending | Pending | Pending | 依赖模型 Provider，无密钥时仅告警 |
| Workspace / 文件工具 / 审批 | Verified | Pending | Pending | Pending | Pending | Phase 4 |
| MCP Client | Verified | Pending | Pending | Pending | Pending | Phase 5 |
| Skills | Verified | Pending | Pending | Pending | Pending | Phase 6 |
| 命名工作区（V1.5 扩展） | Not started | Not started | Pending | Pending | Pending | 两端同时实现 |

`Python = Verified` 表示已有语言内测试与运行验证；跨语言一致性仍需 Phase 2 起的契约与 parity 测试证明。

## 容器化状态（Phase 2）

- Compose 五服务在 `192.168.31.90` 全部 healthy：`backend-python`、`backend-java`、`ui-python`、`ui-java`、`mysql-java`。
- 两个 UI 容器使用同一镜像 `prism-agent-ui:dev`，Image ID 一致（`77fc872a1edb`），仅 `API_TARGET` 不同。
- 契约测试：Python 后端 4 passed、Java 后端 4 passed、两个 UI 反代各 4 passed。
- 隔离验证：停掉 `backend-java` 后 Python 后端与 `ui-python` 仍可用；重启后 Java 恢复 healthy。
- 已知差异：Java 的 `workspace_fts` 仍为 `unsupported`（Phase 4 实现索引后改为真实探测）。
