import { expect, test } from '@playwright/test'
import { installCoreFixture, seedToken } from './core-fixture'

test('应用入口加载前已应用主题，系统偏好随媒体变化', async ({ page }) => {
  await page.emulateMedia({ colorScheme: 'dark' })
  await page.route('**/src/main.ts', () => {})
  await page.goto('/', { waitUntil: 'commit' })
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark')
  await page.unroute('**/src/main.ts')
  await installCoreFixture(page)
  await seedToken(page)
  await page.goto('/settings')
  await page.getByRole('button', { name: '跟随系统', exact: true }).click()
  await page.emulateMedia({ colorScheme: 'light' })
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light')
  await page.getByRole('button', { name: '深色', exact: true }).click()
  await page.reload()
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark')
})
