import { expect, test } from '@playwright/test'
import { installCoreFixture } from './core-fixture'

test('首次引导可以关闭续接，健康检查与访问权限分别验证', async ({ page }) => {
  await installCoreFixture(page)
  await page.goto('/')
  await expect(page.getByRole('dialog')).toBeVisible()
  await page.getByRole('button', { name: '暂时关闭' }).click()
  await expect(page.getByRole('dialog')).not.toBeVisible()
  await page.getByRole('button', { name: '连接服务', exact: true }).click()
  await page.getByRole('button', { name: '检查连接', exact: true }).click()
  await page.getByLabel('API Token', { exact: true }).fill('bad')
  await page.getByRole('button', { name: '验证访问', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('Token 无效')
  await page.getByLabel('API Token', { exact: true }).fill('test-token')
  await page.getByRole('button', { name: '验证访问', exact: true }).click()
  await expect(page.getByRole('dialog').getByText('访问已验证', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: '开始使用', exact: true }).click()
  await expect(page.getByRole('dialog')).not.toBeVisible()
})

test('引导 Escape 后焦点回到入口，清除 Token 保留草稿', async ({ page }) => {
  await installCoreFixture(page)
  await page.addInitScript(() => sessionStorage.setItem('prism-ui.api-token', 'test-token'))
  await page.goto('/sessions/s1')
  await page.getByRole('textbox', { name: '消息' }).fill('还没发送的草稿')
  await page.getByRole('link', { name: '设置', exact: true }).click()
  await page.getByRole('button', { name: '清除 Token' }).click()
  await page.getByRole('link', { name: '返回会话' }).click()
  await expect(page.getByRole('textbox', { name: '消息' })).toHaveValue('还没发送的草稿')
  const trigger = page.getByRole('button', { name: '连接服务', exact: true })
  await trigger.click()
  await page.keyboard.press('Escape')
  await expect(page.getByRole('dialog')).not.toBeVisible()
  await expect(trigger).toBeFocused()
})

test('浏览器拒绝存储时仍能临时验证，明确反馈不伪造保存', async ({ page }) => {
  await installCoreFixture(page)
  await page.addInitScript(() => {
    Storage.prototype.setItem = () => {
      throw new Error('denied')
    }
  })
  await page.goto('/')
  await page.getByRole('button', { name: '检查连接', exact: true }).click()
  await page.getByLabel('API Token', { exact: true }).fill('test-token')
  await page.getByRole('button', { name: '验证访问', exact: true }).click()
  await expect(page.getByRole('dialog')).toContainText('当前页面生效')
  await page.getByRole('button', { name: '开始使用', exact: true }).click()
  await page.getByRole('link', { name: '设置', exact: true }).click()
  await page.getByRole('button', { name: '深色', exact: true }).click()
  await expect(page.getByRole('status').filter({ hasText: '无法保存外观偏好' })).toContainText(
    '当前页面生效',
  )
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark')
})
