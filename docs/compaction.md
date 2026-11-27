# 上下文压缩、轨迹与模型档案（V1.4）

## 上下文压缩

每个 Run 的每个 Step 在组装上下文前执行：

1. **确定性裁剪**：超过 `COMPACTION_PRUNE_THRESHOLD_CHARS`（默认 8000）的 tool 结果保留头尾各 2000 字符，中间插入 `…(pruned N chars)…`；只影响发送副本。
2. **估算与触发**：用 token 估算器计算输入；超过输入预算的 `COMPACTION_THRESHOLD_RATIO`（默认 0.85）时开始压缩。
3. **选段**：从最旧开始保留约 `COMPACTION_RETAIN_TOKENS`（默认 20000）或预算的 `COMPACTION_RETAIN_RATIO`（默认 0.2），单位是 assistant+tool 组，绝不切断配对。
4. **摘要**：用当前 Run 的 Provider/模型生成 8 段结构化 checkpoint（Primary Request / Concepts / Files / Errors / Pending / Current / Next / Critical）；重复压缩会合并上一份摘要。
5. **生效**：写入 `compaction_checkpoints`，后续请求只带 `first_kept_message_id` 之后的消息 + checkpoint 摘要；原文保留在 `messages`，轨迹可查。

失败与兜底：摘要超时/失败记录 `compaction.failed` 并继续用未压缩上下文；provider 报上下文溢出时强制压缩一次并重试；仍超出 100% 预算时由 Assembler 丢弃最旧非保护单元并记 `context.trimmed`。

手动压缩：会话空闲时点击「压缩上下文」或 `POST /api/v1/sessions/{id}/compact`；运行中的会话返回 `COMPACTION_BUSY`。

## 轨迹

会话内「轨迹」Tab（`/sessions/:id/trajectory`）按 Turn → Step → Tool 展示模型、token 用量、耗时、stop reason、工具调用与压缩记录。新 Run 使用 `step.started/completed` 事件；旧 Run 从现有事件合成一个 `legacy` Step 并标注“未记录 usage”。

## 模型档案

「模型」页面维护多份档案（名称、base_url、model、密钥环境变量、context window、max output）。密钥只保存环境变量名，明文从后端进程环境读取。切换为全局生效：下一次请求起所有会话使用新档案；运行中的 Step 不受影响。没有档案时回退 `.env` 的 `MODEL_*` 配置。
