import { defineConfig, devices } from '@playwright/test'

// 常规测试独占开发服务器；所有 Core 请求由明确夹具处理。
export default defineConfig({
  testDir: './tests/e2e',
  testIgnore: '**/*.live.spec.ts',
  fullyParallel: true,
  use: { baseURL: 'http://127.0.0.1:3000', trace: 'retain-on-failure' },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: {
    command: 'pnpm dev',
    url: 'http://127.0.0.1:3000',
    reuseExistingServer: false,
    env: { VITE_API_BASE_PATH: '/api/v1', PRISM_UI_API_TARGET: 'http://127.0.0.1:8000' },
  },
})
