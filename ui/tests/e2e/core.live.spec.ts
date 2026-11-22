import { expect, test } from '@playwright/test'

test('真实 Core 两轮对话、持久消息和刷新恢复', async ({ page }) => {
  test.setTimeout(180_000)
  const token = process.env.PRISM_UI_E2E_TOKEN!
  // 此配置禁止 trace/HAR，测试不打印凭据，也不截图凭据表单。
  await page.addInitScript((value) => sessionStorage.setItem('prism-ui.api-token', value), token)
  await page.goto('/')
  await page.getByRole('button', { name: '新建会话', exact: true }).first().click()
  await expect(page).toHaveURL(/\/sessions\//)
  let round = 0
  for (const input of ['请简短回复：你好。', '请简短回复：继续。']) {
    await page.getByRole('textbox', { name: '消息' }).fill(input)
    await page.getByRole('button', { name: '发送消息' }).click()
    const answers = page.getByRole('log').locator('article')
    await expect(answers).toHaveCount(++round, { timeout: 120_000 })
    await expect(page.getByRole('button', { name: '停止运行' })).toHaveCount(0)
    await expect(answers.last()).toContainText(/\S/)
  }
  const before = await page.getByRole('log').locator('article').allTextContents()
  await page.reload()
  await expect(page.getByRole('log').locator('article')).toHaveText(before)
})
