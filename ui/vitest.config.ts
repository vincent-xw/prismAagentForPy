import { fileURLToPath, URL } from 'node:url'
import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vitest/config'

// 单元测试不加载开发代理，也不依赖后端环境。
export default defineConfig({
  plugins: [vue()],
  resolve: { alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) } },
  test: { include: ['tests/unit/**/*.test.ts'], environment: 'jsdom', restoreMocks: true },
})
