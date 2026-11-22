import { fileURLToPath, URL } from 'node:url'
import vue from '@vitejs/plugin-vue'
import tailwindcss from '@tailwindcss/vite'
import { defineConfig, loadEnv } from 'vite'
import { parseApiBasePath } from './src/lib/api/config.ts'

// 联调地址只由 Node 侧读取；生产构建和静态预览不依赖后端配置。
export default defineConfig(({ command, mode, isPreview }) => {
  // 仅开发服务要求联调配置，显式区分构建与静态预览。
  const isDevelopmentServer = command === 'serve' && !isPreview
  // 环境文件始终相对 ui/ 读取，避免从仓库根目录启动时读错后端配置。
  const env = loadEnv(mode, fileURLToPath(new URL('.', import.meta.url)), 'PRISM_UI_')
  const apiTarget = env.PRISM_UI_API_TARGET
  // 开发与构建都要求显式路径；静态预览消费已构建产物。
  if (!isPreview) {
    const browserEnv = loadEnv(mode, fileURLToPath(new URL('.', import.meta.url)), 'VITE_')
    parseApiBasePath(browserEnv.VITE_API_BASE_PATH)
  }

  if (isDevelopmentServer) {
    if (!apiTarget) {
      throw new Error(
        '缺少 PRISM_UI_API_TARGET：请在 ui/ 下复制 .env.example 为 .env 并填写后端地址。',
      )
    }

    // 配置错误在启动时直接报告，避免请求发出后才发现地址不可用。
    const targetUrl = new URL(apiTarget)
    if (!['http:', 'https:'].includes(targetUrl.protocol)) {
      throw new Error('PRISM_UI_API_TARGET 必须使用 http 或 https 协议。')
    }
  }

  return {
    plugins: [vue(), tailwindcss()],
    resolve: {
      alias: {
        '@': fileURLToPath(new URL('./src', import.meta.url)),
      },
    },
    server: {
      host: '127.0.0.1',
      port: 3000,
      strictPort: true,
      // 保留 /api 路径，不重写后端的 /api/v1 接口前缀。
      proxy: isDevelopmentServer
        ? {
            '^/api/': {
              target: apiTarget,
              changeOrigin: true,
            },
          }
        : undefined,
    },
    preview: {
      host: '127.0.0.1',
      port: 4173,
      strictPort: true,
    },
  }
})
