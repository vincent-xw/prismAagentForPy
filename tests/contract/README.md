# 跨语言 HTTP 契约测试

语言无关的黑盒测试：同一套断言分别打向 Python 与 Java 后端。

## 规则

- 只通过环境变量切换目标：`PRISM_CONTRACT_BASE_URL`、`PRISM_CONTRACT_TOKEN`（UI 用例另需 `PRISM_CONTRACT_UI_BASE_URL`）。
- 不得 `import` 任何后端代码、不得读后端数据库、不得依赖进程内状态。
- 新增断言必须能在两端同时通过；若只能在一端通过，先判断是协议差异还是实现缺陷，不许用 `skip` 掩盖。
- 每个用例必须自己清理创建的数据（使用专用 token 与独立测试库）。

## 运行

```bash
cd tests/contract
PRISM_CONTRACT_BASE_URL=http://192.168.31.90:8000 \
PRISM_CONTRACT_TOKEN=<token> \
uv run --project . pytest -q
```
