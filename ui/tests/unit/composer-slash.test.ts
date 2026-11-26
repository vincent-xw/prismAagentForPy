import { flushPromises, mount } from '@vue/test-utils'
import { expect, test, vi } from 'vitest'

import { appContextKey } from '@/app/context'
import MessageComposer from '@/features/sessions/MessageComposer.vue'

const skill = {
  name: 'pdf-tools',
  description: 'Extract PDFs',
  path: '/s/pdf-tools',
  root: '/s',
  shadowed: false,
}

function mountComposer() {
  const client = { listSkills: vi.fn().mockResolvedValue({ items: [skill] }) }
  const wrapper = mount(MessageComposer, {
    props: { modelValue: '', disabled: false, busy: false, sending: false, stopping: false },
    global: { provide: { [appContextKey as symbol]: { client } } },
  })
  return { wrapper, client }
}

test('输入 / 打开菜单，Enter 选中不发送', async () => {
  const { wrapper } = mountComposer()
  await flushPromises()

  const textarea = wrapper.get('textarea')
  await textarea.setValue('/pdf')
  await wrapper.setProps({ modelValue: '/pdf' })
  expect(wrapper.text()).toContain('pdf-tools')

  await textarea.trigger('keydown', { key: 'Enter' })
  expect(wrapper.emitted('send')).toBeUndefined()
  expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual([''])
  expect(wrapper.text()).toContain('◈ pdf-tools')
})

test('IME 组合态 Enter 不发送', async () => {
  const { wrapper } = mountComposer()
  await flushPromises()
  await wrapper.get('textarea').setValue('/')
  await wrapper.setProps({ modelValue: '/' })

  await wrapper.get('textarea').trigger('keydown', { key: 'Enter', isComposing: true })
  expect(wrapper.emitted('send')).toBeUndefined()
})

test('发送时携带选中的技能名', async () => {
  const { wrapper } = mountComposer()
  await flushPromises()
  await wrapper.get('textarea').setValue('/pdf')
  await wrapper.setProps({ modelValue: '/pdf' })
  await wrapper.get('textarea').trigger('keydown', { key: 'Enter' })
  await wrapper.setProps({ modelValue: '整理这份 PDF' })

  await wrapper.get('button[aria-label="发送消息"]').trigger('click')
  expect(wrapper.emitted('send')?.[0]).toEqual([{ text: '整理这份 PDF', skillName: 'pdf-tools' }])
})
