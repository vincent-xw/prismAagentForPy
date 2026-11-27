# Phase 3b 设计：上下文压缩 / 轨迹 / 模型档案（含 UI 凭据）

- 状态：待评审
- 日期：2026-11-27
- 前置：Phase 2（容器化）、Phase 3a（Run/SSE/工具回路）已验收
- 关联：`2026-11-27-java-runtime-v14-parity-design.md`、`2026-11-27-v1.4-compaction-trajectory-model-profile-design.md`

## 0. 已确认的结论

1. 3b 范围 = **上下文压缩、轨迹、模型档案、会话标题**，外加一条新能力：**模型密钥可在 UI 配置，配完后不再依赖环境变量**。
2. 密钥落盘采用 **方案 A**：明文存库（`model_profiles.api_key`），接口只回 `has_key`，永不回显；数据文件按 0600 处理。
3. **保留环境变量回退**：`api_key` 为空时仍按 `api_key_env` 从进程环境取，已有部署不被打断。
4. **API Token 仍来自环境变量**（`PRISM_API_TOKEN`）：认证无法自举，UI 登录前没有可信通道。
5. `MODEL_TOKEN_ENCODING` 在“有激活档案且未配置”时默认 `cl100k_base`，不再强制一行 env。
6. 这是 V1.4 之后的**第二项契约扩展（v1.2）**：`POST/PATCH /model-profiles` 接受可选 `api_key`，响应新增 `has_key`。Python 与 Java 同阶段实现。

## 1. 为什么要改（密钥部分）

现状：档案只存 `api_key_env`（环境变量名），值由后端进程环境提供。这样 `.env` 至少要有 3 行（API Token、Token 编码、模型密钥），且改密钥必须重建容器。

目标：**在 UI 里填一次密钥，立即生效，不再碰 `.env`**。代价是密钥进入数据库文件，必须把边界写清楚：

- DB 文件（SQLite / MySQL 数据卷）权限收紧到 0600/仅容器用户可读；
- 任何 API 响应、日志、SSE、错误详情都不得出现密钥值，只允许 `has_key`；
- 备份或整卷泄漏等于密钥泄漏——这条明确写进 README，不再宣称“密钥不落库”；
- 环境变量回退保留，作为无 UI 配置时的兼容路径。

## 2. 模型档案（Python 与 Java 同一契约）

### 2.1 数据

`model_profiles`：`id, name, base_url, model, api_key_env, api_key, context_window, max_output_tokens, is_active, created_at, updated_at`

- `api_key` 可空：有值即 UI 配置，优先使用；为空则回退 `os.environ[api_key_env]`。
- `name` 唯一；全局单 active（生成列/唯一索引实现）。
- 校验：`name ≤128`、`base_url` 必须 http(s)、`context_window > 0`、`0 < max_output_tokens < context_window`、`api_key_env` 形如环境变量名。

### 2.2 API（扩展后）

| Method | Path | 变化 |
|---|---|---|
| GET | `/model-profiles` | 响应新增 `has_key` |
| POST | `/model-profiles` | 接受可选 `api_key` |
| PATCH | `/model-profiles/{id}` | 接受可选 `api_key`；**不传 = 不修改**，传空串 = 清除 |
| DELETE | `/model-profiles/{id}` | 不变（active 409） |
| POST | `/{id}/activate` | 不变 |
| POST | `/{id}/probe` | 优先用库内 key，回退 env；失败仍 200 + `{ok:false,error}` |

响应永不包含 `api_key`，只给 `has_key: bool`。

### 2.3 Run 快照与 Provider 解析

创建 Run 时快照 `model_profile_id/model/context_window/max_output_tokens`；Provider 按 Run 解析（档案 id + `updated_at` 缓存），运行中的 Step 不切换。密钥解析顺序：库内 `api_key` → `api_key_env` 指向的 env → 422 `MODEL_PROFILE_INVALID`（创建 Run 前预检，不落库）。

### 2.4 会话标题

Run 创建提交后、`title == null` 且开关开启时**同步**生成：输入前 500 字、`max_tokens=64`、超时 8s、取首行去引号截 20 字；失败只告警，不阻断创建。

## 3. 上下文压缩（Python 语义，Java 复刻）

### 3.1 顺序与阈值

每个 Step 组装前：

1. **确定性裁剪**：单个 tool 结果 > 8000 字符时保留头/尾各 2000，中间插 `…(pruned N chars)…`；只改发送副本，不改库。
2. **估算**：`预算 = context_window - max_output_tokens - 2048`；估算超预算 85% 触发摘要压缩。
3. **选段**：按 user / assistant+tool 为单元，从尾部累计到 `retain = min(20000, 预算×0.2)`；不切断 assistant/tool 配对，切点不得晚于最后一条 user。
4. **摘要**：8 段结构化 Markdown（目标与进展、关键决策、文件与代码、错误与修复、未完成事项、约束、用户偏好、下一步），工具输出截 2000；重复压缩把旧摘要作为 `<previous-summary>` 输入。
5. **落库**：`compaction_checkpoints(summary, first_kept_message_id, tokens_before, tokens_after)`；原文一条不删；后续请求 = `id ≥ first_kept_message_id` 的消息 + 一条合成 checkpoint 消息（`kind=checkpoint`，不入库）。
6. **降级**：无可用段 → `compaction.skipped`；摘要失败/超时 → `compaction.failed` 并沿用原上下文；provider 报 `CONTEXT_OVERFLOW` → 强制压缩一次再重试。
7. **手动压缩**：`POST /sessions/{id}/compact`；有活动 Run → 409 `COMPACTION_BUSY`；返回 `{compacted:false,reason}` 或 `{checkpoint_id,tokens_before,tokens_after}`。

### 3.2 事件（新增 6 个）

`context.pruned{pruned_chars,pruned_count}`、`context.trimmed{trimmed_count,trimmed_tokens}`、`compaction.started{tokens_before,forced}`、`compaction.completed{checkpoint_id,tokens_before,tokens_after,usage}`、`compaction.failed{error,error_code}`、`compaction.skipped{reason}`。事件与其他事件同一 `seq` 序列。

## 4. 轨迹

`GET /sessions/{id}/trajectory?limit=50&before=<iso>` → `{turns:[{run,steps,compactions}]}`

- Turn = Run，倒序取 N 个后按 `created_at` 正序输出。
- Step：按 `step.started` 的 `step_index` 生成；无 step 事件的旧 Run 合成一个 `legacy:true` 的 Step（usage/duration 为 null）；工具按 `step.completed.tool_call_ids` 归属；`assistant_message_id` 恒 null（与 Python 一致）。
- compactions 按 `created_at ∈ [run.created_at, run.finished_at]` 归属；未归属且 `before` 为空时挂到最后一个 Turn。

## 5. Java 侧落点

| 能力 | Java 组件 |
|---|---|
| 档案表 + API | `model_profiles`（V3 迁移）、`ModelProfileRepository/Service/Controller`、DTO 加 `hasKey` |
| 密钥解析 | `ProfileCredentialResolver`：库内 → env → 422 |
| Provider 解析 | `ProviderResolver`（按 Run 快照 + 档案 `updated_at` 缓存） |
| 上下文装配 | `ContextAssembler`（消息配对校验、预算、裁剪）、`TokenEstimator`（jtokkit） |
| 压缩 | `Pruner`、`CompactionService`（同一 Provider 摘要）、`CompactionCheckpoint` 仓储 |
| 轨迹 | `TrajectoryService` + `TrajectoryController`（只读投影） |
| 标题 | `SessionTitleService`（复用 Run 的 Provider） |
| 手动压缩 | `SessionCompactionService`（活动 Run 检查 → 409） |

Java 的 `TokenEstimator` 用 jtokkit；与 tiktoken 的数值差异按已定规则（K-05）不比对具体 token，只比对**触发顺序与相对位置**。

## 6. 契约治理

- 契约快照升 **v1.2**：Python 侧这些端点**本来就存在**（35 paths / 42 operations 已包含 `/model-profiles*`、`/sessions/{id}/trajectory`、`/sessions/{id}/compact`），v1.2 只新增字段语义（`api_key` 可写、`has_key` 只读），**path 与 operation 数量不变**。
- `contracts/events/events.schema.json` 保持 27 个事件不变；Java 的事件枚举当前只有 18 个，3b 要补到 24 个（+`context.trimmed`、`context.pruned`、`compaction.*` 4 个），剩余 3 个审批事件（`tool.approval_required/approved/rejected`）属于 Phase 4。
- 新增 `tests/contract/test_model_profiles.py`、`test_trajectory.py`，并补 `test_runs.py` 的压缩场景。
- 破坏性变更判定：新增可选字段（`api_key`/`has_key`）属向后兼容；但“密钥落库”改变了安全承诺，必须在 README 与 `docs/compatibility/` 里显式记录。

## 7. 安全与运维

- SQLite/MySQL 数据卷权限 0600；README 增加“备份即密钥备份”的警告。
- 日志、错误 details、SSE payload、trajectory 投影一律不含密钥；`has_key` 是唯一对外信号。
- 清除密钥：`PATCH` 传 `api_key: ""`；删除档案不影响历史 Run（Run 已快照模型名与窗口，但 Provider 解析失败时按 502 处理并记录明确错误）。

## 8. 非目标

- 不做多用户与权限模型；不做密钥轮换审计；不做 KMS/钥匙串集成。
- 不改压缩算法本身（保持与 Python V1.4 一致），只做跨语言复刻。
- 不做轨迹的时间轴缩放、跨会话搜索。

## 9. 需要你确认

1. 方案 A（明文入库 + `has_key` + env 回退）作为最终形态——你已选 A，本文按 A 展开。
2. 契约扩展 v1.2 需要 **Python 与 Java 同阶段改**，这会动 Python 的 `model_profiles` 表（Alembic 迁移）与密钥读取路径；确认接受后再写实施计划。
3. `MODEL_TOKEN_ENCODING` 默认 `cl100k_base` 的兜底，是否同意（否则仍需一行 env）。
