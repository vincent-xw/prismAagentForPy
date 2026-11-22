import { defineConfig, devices } from '@playwright/test'

// 缺少真实环境就明确失败，禁止静默跳过并声称联调成功。
for (const key of ['PRISM_UI_API_TARGET', 'PRISM_UI_E2E_TOKEN', 'VITE_API_BASE_PATH']) {
  if (!process.env[key]) throw new Error(`真实 Core 联调未执行：缺少 ${key}。`)
}
export default defineConfig({
  testDir: './tests/e2e',
  testMatch: '**/*.live.spec.ts',
  workers: 1,
  use: { baseURL: 'http://127.0.0.1:3000', trace: 'off', video: 'off', screenshot: 'off' },
  projects: [{ name: 'live-chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: {
    command: 'pnpm dev',
    url: 'http://127.0.0.1:3000',
    reuseExistingServer: false,
    env: {
      PRISM_UI_API_TARGET: process.env.PRISM_UI_API_TARGET!,
      VITE_API_BASE_PATH: process.env.VITE_API_BASE_PATH!,
    },
  },
})
