# PrismAgentKit UI

独立的前端工程基建，使用 Vue 3、TypeScript、Vite 和 pnpm。当前提供初始化页面，不包含业务功能。

## 环境要求

- Node.js `^22.13.0 || >=24.0.0`。
- pnpm `11.9.0`，由 `package.json` 的 `packageManager` 固定。
- TypeScript 使用 6.0 系列，与当前 ESLint TypeScript 插件的支持范围保持一致。

## 本地开发

在仓库根目录执行：

```bash
cd ui
rtk pnpm install --frozen-lockfile
rtk cp .env.example .env
rtk pnpm dev
```

页面地址：`http://127.0.0.1:3000`。开发端口固定，端口占用时会直接报错。

`.env` 中必须明确填写 `PRISM_UI_API_TARGET`，未配置时开发服务器会直接报错，不自动选择后端地址。示例值为 `http://127.0.0.1:8000`，请按实际运行地址调整。

## 前后端联调

开发服务器将 `/api/` 下的请求转发至 `PRISM_UI_API_TARGET`，保留完整路径。例如：

```text
浏览器请求：http://127.0.0.1:3000/api/v1/health
转发目标：  http://127.0.0.1:8000/api/v1/health
```

前端和后端分别启动。该配置只作用于开发服务器，生产环境需由部署入口配置 `/api/` 反向代理；`preview` 仅用于静态产物预览。

`PRISM_UI_` 前缀变量由开发工具读取，不注入浏览器。未来添加 `VITE_` 前缀变量时，其中不得放置密钥或服务端凭据。

## 常用命令

以下命令均在 `ui/` 下运行：

| 命令                | 用途                                    |
| ------------------- | --------------------------------------- |
| `rtk pnpm dev`      | 启动开发服务器                          |
| `rtk pnpm check`    | 执行 ESLint、格式检查和类型检查         |
| `rtk pnpm build`    | 类型检查后生成 `dist/`                  |
| `rtk pnpm preview`  | 在 `http://127.0.0.1:4173` 预览构建产物 |
| `rtk pnpm lint:fix` | 自动修复可修复的代码检查问题            |
| `rtk pnpm format`   | 格式化前端文件                          |

后续安装依赖使用 `rtk pnpm install`；自动化环境使用 `rtk pnpm install --frozen-lockfile`。依赖变更需同时提交 `package.json` 和 `pnpm-lock.yaml`。

## 目录

```text
ui/
├── .env.example          # 本地联调配置示例
├── eslint.config.js      # Vue 与 TypeScript 检查规则
├── index.html            # HTML 入口
├── package.json
├── pnpm-lock.yaml
├── tsconfig*.json        # 浏览器与开发工具的类型配置
├── vite.config.ts        # 构建、路径别名与开发代理
└── src/
    ├── App.vue           # 初始化页面
    ├── main.ts           # 应用入口
    └── styles/main.css   # 基础样式
```

`@/` 指向 `src/`，Vite 和 TypeScript 使用一致的别名配置。建议编辑器安装 Vue - Official 扩展。
