import { expect, test } from '@playwright/test'
import { installCoreFixture } from './core-fixture'

test('打开即进入工作台，不再要求填写 API Token', async ({ page }) => {
  await installCoreFixture(page)
  await page.goto('/')

  await expect(page.getByRole('dialog')).toHaveCount(0)
  await expect(page.getByText('API Token', { exact: true })).toHaveCount(0)
  await expect(page.getByRole('link', { name: '设置', exact: true })).toBeVisible()
})

test('设置页显示内置凭据已连接', async ({ page }) => {
  await installCoreFixture(page)
  await page.goto('/settings')

  await expect(
    page.getByText('已连接（内置凭据，无需手动填写 Token）', { exact: true }),
  ).toBeVisible()
  await expect(page.getByRole('button', { name: '验证', exact: true })).toHaveCount(0)
})
