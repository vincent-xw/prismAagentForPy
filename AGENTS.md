# PrismAgentKit Python 仓库协作说明

## 项目定位与上游关系

- 本仓库是 **PrismAgentKit 的 Python 重构版本**，不是对 Node.js 版本的简单转写。
- Node.js 版本是功能迁移、行为对齐和兼容性验证的上游参考实现。其仓库链接由项目作者确认后在 `README.md` 中补充；在链接补充前，不要自行猜测或写入上游地址。
- 迁移一个功能前，应先阅读 Node.js 版本对应的实现、测试和文档，再设计 Python 侧接口与实现。无法从上游确认的行为不得凭经验补全。
- 与 Node.js 版本存在刻意差异时，必须在对应变更说明中写清原因、影响范围与兼容策略。
- 新增能力应优先遵循 Python 生态惯例；若为了兼容上游而保留 Node.js 风格，需要说明理由。

## 迁移边界

- 除非用户明确指定某个 Node.js 功能并要求开始迁移，否则只维护脚手架、基础设施和文档，不主动实现任何上游业务功能。
- 完成用户当前指定的范围后立即停止，不自行扩展到一个或多个功能迁移阶段。
- 当前初始化阶段的目标仅是标准 Python 后端框架；健康检查和空迁移基座属于基础设施，不代表业务迁移已经开始。

## 常用命令

```bash
uv sync
uv run uvicorn prism_agent_kit.main:app --reload
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pytest
```

若终端环境已安装并约定使用 `rtk`，请按用户全局要求为命令加 `rtk` 前缀。

## 工程约定

- 使用 `src` 布局，业务代码放在 `src/prism_agent_kit/`，测试放在 `tests/`。
- 对外 HTTP 接口统一挂在 `PRISM_AGENT_KIT_API_PREFIX` 下；当前默认前缀为 `/api/v1`。
- 配置只通过 `pydantic-settings` 从环境变量或 `.env` 读取，不在业务代码中散落读取环境变量。
- 不得提交真实密钥、模型凭据、用户数据或生产连接串；只在 `.env.example` 中维护无敏感信息的示例。
- 数据库模型统一继承 `prism_agent_kit.db.base.Base`，结构变更必须附带 Alembic 迁移。
- I/O 操作使用异步实现；禁止在异步请求路径中调用阻塞式网络、文件或数据库客户端。
- API 输入输出使用 Pydantic 模型明确描述，不直接暴露 ORM 对象。
- 默认不做字段兜底。确需兜底时，必须说明触发条件、默认值来源和可观测性方案。
- 函数、变量和复杂业务逻辑使用中文注释；标识符保持符合 Python 命名习惯的英文。

## 质量门槛

- 提交前至少通过 `ruff check`、`ruff format --check`、`mypy src` 和 `pytest`。
- 新功能需要覆盖正常路径、关键边界和错误路径；仅修改文档时可不新增测试，但仍需确认命令示例有效。
- 不修复与当前任务无关的问题；发现后单独记录并告知用户。
