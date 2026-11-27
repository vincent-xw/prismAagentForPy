import { mount } from '@vue/test-utils'
import { expect, test, vi } from 'vitest'

import SessionIdCopy from '@/features/sessions/SessionIdCopy.vue'

test('副标题展示 Session ID 并可复制', async () => {
  const writeText = vi.fn(async () => {})
  vi.stubGlobal('navigator', { clipboard: { writeText } })
  const wrapper = mount(SessionIdCopy, { props: { sessionId: 'sess-123' } })

  expect(wrapper.text()).toContain('sess-123')
  await wrapper.get('button[aria-label="复制会话 ID"]').trigger('click')

  expect(writeText).toHaveBeenCalledWith('sess-123')
  expect(wrapper.find('button[aria-label="已复制会话 ID"]').exists()).toBe(true)
})
