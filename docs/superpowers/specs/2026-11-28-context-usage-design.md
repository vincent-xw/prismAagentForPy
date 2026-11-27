# 上下文使用量展示（Context Usage）设计

- 状态：已确认（方案 A），2026-11-28
- 前置：Phase 3b 上下文压缩、Phase 5 MCP

## 目标

在 UI 里展示当前会话的上下文使用量与 85% 压缩阈值，让用户知道何时该手动压缩；提供直达“压缩上下文”的入口。

## 方案（A）

新增两端同一契约：`GET /sessions/{id}/context`

```json
{
  "context_window": 65536,
  "max_output_tokens": 8192,
  "budget_tokens": 55296,
  "used_tokens": 12345,
  "percent": 22.3,
  "threshold": 0.85,
  "needs_compaction": false,
  "compactable": true,
  "last_compaction": {"tokens_before": 30000, "tokens_after": 12000, "at": "..."} 
}
```

- `budget_tokens = max(1024, context_window - max_output_tokens - 2048)`；
- `used_tokens`：有 checkpoint 时 `tokens_after + 估算(checkpoint.created_at 之后的消息)`；否则估算全部消息；
- 窗口来源：会话最近一个 Run 的快照（`model_context_window/max_output_tokens`），没有 Run 时用激活模型档案，再退回服务配置默认；
- `needs_compaction = percent >= 85`；
- `compactable = 有消息且无活动 Run`（与 compact 接口规则一致）；
- 估算器两端不同（tiktoken / jtokkit），契约只断言“是否超阈值与相对高低”，不断言具体 token 数。

## 非目标

- 不做自动压缩触发；不做逐会话预算配置；不把该统计写进 Run 契约。

## UI

会话页头部（标题右侧）显示：`上下文 42% · 12.3k/29k` 进度条 + 85% 阈值刻度；≥85% 变红并显示“压缩上下文”按钮（二次确认 → `POST /sessions/{id}/compact` → 刷新）。会话切换、Run 完成、手动压缩后刷新；无会话或无消息时显示“—”。
