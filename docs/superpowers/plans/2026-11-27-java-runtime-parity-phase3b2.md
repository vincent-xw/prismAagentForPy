# Phase 3b-2 实施计划：压缩 / 轨迹 / 标题（Java 主体）

**Goal:** Java 端补齐上下文裁剪与压缩、轨迹只读投影、会话标题与手动压缩，行为对齐 Python V1.4。
**Spec:** `docs/superpowers/specs/2026-11-27-java-runtime-v14-parity-phase3b-design.md` §3–§5。
**参考实现（只读）:** `backend/src/prism_agent_kit/application/{compaction,trajectory_service,session_title_service,manual_compaction_service}.py`

## Global Constraints

- 压缩逻辑只改“发送副本”，**不删库内消息**；checkpoint 单独落表。
- 事件与其他事件共用 per-run `seq`；新事件 6 个：`context.trimmed`、`context.pruned`、`compaction.started/completed/failed/skipped`。
- 摘要调用与 Run 同 Provider；摘要失败只降级记事件，不失败 Run。
- 轨迹为只读投影，不新增表；工具归属按 `step.completed.tool_call_ids`。
- 预算与阈值常量必须与 Python 一致：裁剪阈值 8000/头尾 2000、预算 = window - maxOutput - 2048、触发 85%、保留 `min(20000, 预算×0.2)`。
- 质量门槛：`./mvnw verify` 全绿；契约测试跑 Java 端。

## Tasks

### Task 1: 事件与表
- `EventType` 增 `CONTEXT_TRIMMED/CONTEXT_PRUNED/COMPACTION_STARTED/COMPACTION_COMPLETED/COMPACTION_FAILED/COMPACTION_SKIPPED`（18→24）。
- `V4__compaction_checkpoints.sql`：`id CHAR(36) PK, session_id CHAR(36), run_id CHAR(36) NULL, summary MEDIUMTEXT, first_kept_message_id CHAR(36), tokens_before INT, tokens_after INT, created_at DATETIME(6)` + `KEY (session_id, created_at)`。
- 实体/仓储 `CompactionCheckpointRepository`（insert、listForSession、latestBefore）。

### Task 2: 估算与裁剪（纯函数，先测）
- 依赖 `com.knuddels:jtokkit`。
- `TokenEstimator.estimate(String)`、`estimateAll(List<Message>)`。
- `HistoryPruner.prune(List<Message>)`：单条 tool 结果 > 8000 字符时保留头/尾 2000 + `…(pruned N chars)…`；返回 `(messages, prunedChars, prunedCount)`。
- 测试：8000 边界、恰好 8001、纯文本不受影响、计数正确。

### Task 3: 上下文装配与压缩
- `ContextAssembler.build(sessionId, run)`：
  1. 读最新 checkpoint，`messages = listAfter(firstKeptMessageId)` + 合成 checkpoint 消息；
  2. `HistoryPruner` 裁剪（有裁剪则记 `context.pruned`）；
  3. 估算超 85% 或强制 → 选段（尾部累计到 retain，不切断 assistant/tool 配对）→ `compaction.started` → 摘要 → checkpoint 落库 + `compaction.completed`；失败 `compaction.failed` 并沿用原上下文；无可用段 `compaction.skipped`。
- `CompactionSummarizer`：8 段 Markdown 提示词（与 Python 同结构），超时 30s。
- 引擎接入：`SimpleAgentEngine` 用装配结果替换 `messages.listForSession`；收到 `CONTEXT_OVERFLOW` 时强制压缩一次重试。
- 测试（stub 模型）：未超阈值不压缩、超阈值压缩一次且原文仍在、摘要失败降级、溢出重试成功。

### Task 4: 轨迹
- `TrajectoryService.turns(sessionId, limit, before)`：Run 倒序取 N 后正序；steps 由 `step.started` 投影，无 step 事件合成 `legacy:true`；tools 按 `step.completed.tool_call_ids`；compactions 按时间窗归属。
- `GET /sessions/{id}/trajectory?limit=1..200&before=ISO`。
- 测试：普通两轮、legacy Run、compaction 归属、limit/before 分页。

### Task 5: 标题与手动压缩
- `SessionTitleService.maybeGenerate(sessionId)`：`title == null` 时用 Run Provider 生成（8s、64 tokens、前 500 字、截 20 字），失败只记日志；在 `RunService.create` 提交后调用。
- `POST /sessions/{id}/compact`：有活动 Run → 409 `COMPACTION_BUSY`；否则执行一次强制压缩，返回 `{compacted, checkpoint_id?, tokens_before?, tokens_after?, reason?}`。
- 测试：标题生成与失败降级、手动压缩 409 与成功。

### Task 6: 契约与收尾
- `tests/contract/test_trajectory.py`；`test_runs.py` 补压缩场景（需要桩模型触发阈值）。
- parity 文档更新；重建镜像，双端跑 3b 契约。

## 自检

- 覆盖 spec §3（压缩）、§4（轨迹）、§5（标题/手动压缩）；凭据部分已在 3b-1。
- 每任务都有可执行断言；纯函数（pruner/token）先测，再集成。
- 风险：jtokkit 与 tiktoken 计数不同 → 按 K-05 只比对触发顺序，不比对 token 数值。
