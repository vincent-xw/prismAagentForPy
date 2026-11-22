import { expect, test, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import ConnectionWizard from '@/features/connection/ConnectionWizard.vue'
import { createConnection } from '@/features/connection/connection'

test('关闭引导不伪造验证成功，再开仍可继续', async () => {
  const connection = createConnection({
    basePath: '/api/v1',
    storage: sessionStorage,
    fetcher: vi.fn<typeof fetch>(),
    onCredentialsChanged: () => {},
  })
  const wrapper = mount(ConnectionWizard, {
    props: { connection, open: true },
    attachTo: document.body,
  })
  await nextTick()
  expect(document.body.textContent).toContain('连接服务')
  expect(document.body.textContent).toContain('验证访问')
  expect(connection.state.status).toBe('unverified')
  const close = document.querySelector<HTMLButtonElement>('[data-testid="wizard-later"]')!
  close.click()
  await nextTick()
  expect(wrapper.emitted('update:open')?.[0]).toEqual([false])
  expect(connection.state.status).toBe('unverified')
  wrapper.unmount()
})
