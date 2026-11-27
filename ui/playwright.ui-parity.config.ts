import { defineConfig, devices } from '@playwright/test'

// 对已部署的两个 UI 地址复用同一套 live spec；地址与 token 必须显式提供。
const baseURL = process.env.PRISM_UI_URL
if (!baseURL) throw new Error('缺少 PRISM_UI_URL')
if (!process.env.PRISM_UI_E2E_TOKEN) throw new Error('缺少 PRISM_UI_E2E_TOKEN')

export default defineConfig({
  testDir: './tests/e2e',
  testMatch: '**/*.live.spec.ts',
  workers: 1,
  timeout: 180_000,
  use: { baseURL, trace: 'retain-on-failure', video: 'off', screenshot: 'only-on-failure' },
  projects: [{ name: 'live-chromium', use: { ...devices['Desktop Chrome'] } }],
})
