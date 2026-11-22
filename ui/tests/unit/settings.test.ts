import { expect, test, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import SettingsPage from '@/features/settings/SettingsPage.vue'
import { createConnection } from '@/features/connection/connection'
import { useTheme } from '@/app/theme/useTheme'

test('设置展示实际空工具目录，外观选择修改主题偏好', async () => {
  vi.stubGlobal('matchMedia', () => Object.assign(new EventTarget(), { matches: false }))
  const theme = useTheme()
  const connection = createConnection({
    basePath: '/api/v1',
    storage: sessionStorage,
    fetcher: vi.fn<typeof fetch>().mockResolvedValue(Response.json({ items: [] })),
    onCredentialsChanged: () => {},
  })
  await connection.verifyAccess('test')
  const wrapper = mount(SettingsPage, { props: { connection, theme } })
  expect(wrapper.text()).toContain('尚未注册工具')
  await wrapper.get('button[data-theme-choice="dark"]').trigger('click')
  expect(theme.preference.value).toBe('dark')
  expect(wrapper.text()).not.toContain('模型密钥')
  wrapper.unmount()
  theme.dispose()
})
