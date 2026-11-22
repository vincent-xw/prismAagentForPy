import { expect, test } from '@playwright/test'
import { installCoreFixture } from './core-fixture'

test('首次进入不弹窗，在设置页完成健康检查与访问验证', async ({ page }) => {
  await installCoreFixture(page)
  await page.goto('/')
  await expect(page.getByRole('dialog')).toHaveCount(0)
  await expect(page.getByText('连接服务后开始对话', { exact: true })).toBeVisible()
  await page.getByRole('link', { name: '连接服务', exact: true }).click()
  await expect(page).toHaveURL(/\/settings$/)
  await page.getByRole('button', { name: '检查服务', exact: true }).click()
  await page.getByLabel('API Token', { exact: true }).fill('bad')
  await page.getByRole('button', { name: '验证', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('Token 无效')
  await page.getByLabel('API Token', { exact: true }).fill('test-token')
  await page.getByRole('button', { name: '验证', exact: true }).click()
  await expect(page.getByRole('paragraph').filter({ hasText: '访问已验证' })).toBeVisible()
  await page.getByRole('link', { name: '返回会话' }).click()
  await expect(page.getByText('连接服务后开始对话', { exact: true })).toHaveCount(0)
})

test('清除 Token 后保留草稿，并继续从设置页连接', async ({ page }) => {
  await installCoreFixture(page)
  await page.addInitScript(() => sessionStorage.setItem('prism-ui.api-token', 'test-token'))
  await page.goto('/sessions/s1')
  await page.getByRole('textbox', { name: '消息' }).fill('还没发送的草稿')
  await page.getByRole('link', { name: '设置', exact: true }).click()
  await page.getByRole('button', { name: '清除 Token' }).click()
  await page.getByRole('link', { name: '返回会话' }).click()
  await expect(page.getByRole('textbox', { name: '消息' })).toHaveValue('还没发送的草稿')
  await page.getByRole('link', { name: '连接服务', exact: true }).click()
  await expect(page).toHaveURL(/\/settings$/)
  await expect(page.getByRole('dialog')).toHaveCount(0)
})

test('浏览器拒绝存储时仍能临时验证，并明确提示仅当前页面生效', async ({ page }) => {
  await installCoreFixture(page)
  await page.addInitScript(() => {
    Storage.prototype.setItem = () => {
      throw new Error('denied')
    }
  })
  await page.goto('/settings')
  await page.getByLabel('API Token', { exact: true }).fill('test-token')
  await page.getByRole('button', { name: '验证', exact: true }).click()
  await expect(page.getByRole('paragraph').filter({ hasText: '访问已验证' })).toBeVisible()
  await expect(page.getByRole('status').filter({ hasText: '无法保存凭据' })).toContainText(
    '当前页面生效',
  )
  await page.getByRole('button', { name: '深色', exact: true }).click()
  await expect(page.getByRole('status').filter({ hasText: '无法保存外观偏好' })).toContainText(
    '当前页面生效',
  )
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark')
})
