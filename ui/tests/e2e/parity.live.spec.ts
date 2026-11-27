import { expect, test } from '@playwright/test'

test('核心工作台：对话、上下文用量、轨迹与技能页', async ({ page }) => {
  test.setTimeout(180_000)
  const token = process.env.PRISM_UI_E2E_TOKEN!
  await page.addInitScript((value) => sessionStorage.setItem('prism-ui.api-token', value), token)
  await page.goto('/')

  await page.getByRole('button', { name: '新建会话', exact: true }).first().click()
  await expect(page).toHaveURL(/\/sessions\//)

  // 输入 / 打开技能菜单，共享示例技能应可见
  const composer = page.getByRole('textbox', { name: '消息' })
  await composer.click()
  await composer.fill('/')
  await expect(page.getByRole('option', { name: /prism-demo/ })).toBeVisible()
  await page.keyboard.press('Escape')
  await composer.fill('')

  await composer.fill('请简短回复：你好。')
  await page.getByRole('button', { name: '发送消息' }).click()
  const answers = page.getByRole('log').locator('article')
  await expect(answers).toHaveCount(1, { timeout: 120_000 })
  await expect(answers.last()).toContainText(/\S/)

  // 输入框下方的上下文用量
  await expect(page.getByText(/上下文 \d/)).toBeVisible()

  // 轨迹页能读到 Turn/Step
  await page.getByRole('link', { name: '轨迹' }).click()
  await expect(page).toHaveURL(/\/trajectory$/)
  await expect(page.getByText(/Step 1|步骤 1/).first()).toBeVisible({ timeout: 30_000 })
})
