# Phase 7 实施计划：行为级 Parity + 双 UI E2E

**Goal:** 把 parity 表从 “Contract Passed” 推进到有证据的 Behavior / E2E，并把刻意差异归档为 Known Difference。

**Approach:** 用零依赖 mock 模型（确定性文本/工具调用/慢响应）在 192.168.31.90:19000 提供服务，两端各建临时模型档案激活；`tests/parity` 通过纯 HTTP 对比两端行为；Playwright 用同一 spec 分别跑 `:3000`/`:3001`。

## Global Constraints

- 测试不得 import 后端代码；只走 HTTP/SSE。
- 使用 mock 档案前记录两端原激活档案，结束后恢复；临时档案删除。
- 模型桩按 prompt 关键字确定性输出，不依赖网络模型。
- E2E 必须真实点击 UI，不允许 mock core。
- 只有实际跑过的行才改成 Behavior/E2E Passed。

## 场景与断言

| 场景 | 断言（两端对比） |
|---|---|
| 文本 Run | 终态、事件类型序列、消息 kind/role 序列一致 |
| 工具回环 | 绑定工作区 + `[[tool:file_list]]`；事件含 tool.requested/completed；tool_calls 状态一致 |
| 技能注入 | `skill_name=prism-demo`；消息序列 `[skill_context, user, assistant]` |
| BUSY + 取消 | 慢 Run 期间第二次创建 409 BUSY；取消后终态 cancelled 且出现 run.cancelled |
| 事件重放 | 终态后拉全量事件：id 单调、终态事件类型一致 |
| 上下文 | 同预算公式；used>0；percent 相对一致（容差 10 个百分点） |

## Tasks

### Task 1: parity 表与 Known Difference

- [ ] 修 Session 绑定、命名工作区两行（已实现）；Health 的 `workspace_fts` 按实际更新
- [ ] 新增 Known Difference 小节：K-09 审批、`workspaces/pick`、token 估算器、FTS 探测

### Task 2: mock 模型

- [ ] `tests/mock-model/server.py` 增加按 prompt 关键字的 `[[tool:file_list]]`、`[[slow]]` 场景与 tool 结果后的最终文本
- [ ] `scripts/mock-model.sh start|stop` 在服务器 nohup 启动，端口 19000，绑定 0.0.0.0
- [ ] 两端创建 `parity-mock` 档案并激活，确认一次文本 Run 成功；记录原激活档案

### Task 3: `tests/parity`

- [ ] 新增 `tests/parity/{conftest.py,test_behavior.py}`，复用 contract 的 client 形态但双端
- [ ] 六个场景全部断言；失败信息带两端原始响应
- [ ] 双端跑绿

### Task 4: Playwright 双 UI

- [ ] `ui/playwright.ui-parity.config.ts`：baseURL 来自 `PRISM_UI_URL`，无 webServer
- [ ] 复用 `core.live.spec.ts`；对 3000 与 3001 各跑一次（token 走 env）
- [ ] 失败时保留 trace；通过后更新 E2E 行

### Task 5: 收口

- [ ] Python `pytest/ruff/mypy`、Java `verify`、UI `check/test/build`
- [ ] parity 表按实际覆盖改为 Behavior/E2E Passed
- [ ] 提交；报告明确哪些行仍未覆盖（如有）
