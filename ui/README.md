# Prism Core UI

Vue 3 + TypeScript + Vite 的独立前端，使用 Tailwind CSS 4、自有语义主题和按需 shadcn-vue / Reka 组件。提供会话工作台、执行详情、独立设置页与工作区页；会话页支持写入审批。

## 启动

要求 Node.js `^22.13.0 || >=24.0.0`、pnpm `11.9.0`。在 `ui/` 执行：

```bash
rtk pnpm install --frozen-lockfile
rtk proxy cp .env.example .env
rtk pnpm dev
```

在 `.env` 显式设置：

```dotenv
PRISM_UI_API_TARGET=http://127.0.0.1:8000
VITE_API_BASE_PATH=/api/v1
```

开发服务为 `http://127.0.0.1:3000`；端口冲突直接退出。`PRISM_UI_API_TARGET` 只由 Node 侧代理读取，不写入浏览器。`VITE_API_BASE_PATH` 是同源 API 路径，缺失或非法时明确提示配置错误；生产构建也必须提供。开发代理保留 `/api/` 路径，不重写前缀。

Python Backend 位于仓库根 `backend/`。启动后端后，将 `PRISM_UI_API_TARGET` 指向实际服务地址；健康检查成功不代表模型凭据、Core 业务或 SSE 已完整可用。

## 使用范围

- 首次进入不弹窗；未连接时工作台提示并链接到设置页。设置页完成健康检查与 Token 验证，模型调用能力以实际运行结果为准。
- API Token 在受保护的工具目录查询成功后保存到当前标签页 `sessionStorage`，不进入构建变量、日志或长期存储。存储受限时明确提示仅本页有效。
- 创建会话、连续发送、停止并等待服务端终态、读取持久历史和刷新恢复。当前没有删除或重命名会话接口。
- 执行详情展示真实 Run 与工具事件。缺少消息关联时显示未完整取得，不从工具输出对象的形状推断失败。
- 桌面详情位于工作区内；窄屏才使用 Sheet。引导、导航与详情避免多层模态叠加。
- 设置支持浅色、深色、跟随系统，首次绘制前应用主题；提供连接与只读工具目录。
- 消息正文按 Markdown 渲染（含 GFM 表格），渲染前禁用原始 HTML 并经 DOMPurify 清洗；流式增量阶段保持纯文本。

## 验证

```bash
rtk pnpm check
rtk pnpm test
rtk pnpm build
rtk pnpm exec playwright install chromium
rtk pnpm test:e2e
```

常规浏览器测试使用明确的 HTTP 夹具和本地分块 SSE 服务，不要求实际 Backend 在线，未知 API 请求直接失败。测试配置独占端口 3000，不复用已有开发服务。

真实 Core 联调需在命令环境中提供 `PRISM_UI_API_TARGET`、`VITE_API_BASE_PATH`、`PRISM_UI_E2E_TOKEN` 后运行 `rtk pnpm test:e2e:live`。缺失配置直接退出，禁止静默跳过。测试会创建独立会话并发送两条模型输入；当前 API 无会话删除能力，请使用专用测试数据库。此配置不保存 trace、HAR、截图或视频。

## 原型与部署

运行开发服务器后访问 `/prototypes/core-ui.html` 查看独立原型。原型有明确的演示标记，不请求 Backend；产品请求失败不切换 Mock。

`rtk pnpm preview` 在 `127.0.0.1:4173` 提供构建结果，仅预览静态资源，不代理 Backend。正式部署应由入口服务器将 `/api/` 转发到 Core，并将 `/sessions/*`、`/settings` 等前端路由回退到 `index.html`；`/api/` 错误不得回退到 SPA 页面。

## 扩展边界

`src/app/` 装配应用与导航；`features/` 按会话、执行、连接和设置分工；`lib/api/` 集中维护 HTTP DTO 校验与 SSE。新增模块在具备真实 Backend 能力后注册路由和导航，不提前展示空白能力入口。主题统一维护在 `src/styles/tokens.css`，基础组件源码在 `src/components/ui/`，可自主维护变体与布局。
