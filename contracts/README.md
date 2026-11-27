# 公共契约（Python / Java 双端共同遵守）

## 事实来源（按优先级）

1. 运行中的 Python 后端（黑盒行为）；
2. `backend/src/prism_agent_kit/api/schemas.py` 与路由；
3. `contracts/openapi/prism-agent-api.yaml`（由 `scripts/export-openapi.sh` 从运行时代码导出）；
4. `ui/src/lib/api/contracts.ts` 的 zod 校验与 SSE 解析；
5. 现有测试夹具。

冲突时以 1/2 为准；UI 校验代表"客户端可接受性"；OpenAPI 快照只用于辅助比较，**不能单独作为一致性判据**。

## 目录

```text
contracts/
├── openapi/prism-agent-api.yaml   # 35 paths / 42 operations 快照
├── events/events.schema.json      # 27 类 SSE 事件 + 序不变量
└── README.md                      # 本文件
```

## 冻结与变更

- 快照只在 Python 真实行为变化时更新；更新必须同时说明两端影响。
- 以下变更等于破坏性变更，必须单独评审：字段名、枚举值、错误码、事件名、状态码、SSE 帧形状。
- Java 端不得"顺手"补契约里没有的字段；不得加 `Result<T>` 包装；不得改大小写。
- 重新导出：`bash scripts/export-openapi.sh`（期望输出 `35 paths`，42 个 operation）。

## 事件不变量

见 `events/events.schema.json` 的 `x-invariants`。其中最容易被实现者破坏的三条：

1. 持久事件 `id` 必须是纯数字；`message.delta`/`reasoning.delta` 必须没有 `id`。
2. 事件 `run_id` 必须等于订阅的 Run，否则 UI 直接判定协议错误。
3. 终态事件之后关闭流；终态 Run 的重连只做有限重放。
