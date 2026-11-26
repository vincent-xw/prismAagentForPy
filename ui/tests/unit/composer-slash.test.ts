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

test('无匹配时 Enter 只关闭菜单不发送', async () => {
  const { wrapper } = mountComposer()
  await flushPromises()
  await wrapper.get('textarea').setValue('/zzz')
  await wrapper.setProps({ modelValue: '/zzz' })
  expect(wrapper.text()).toContain('没有匹配的技能')

  await wrapper.get('textarea').trigger('keydown', { key: 'Enter' })
  expect(wrapper.emitted('send')).toBeUndefined()
})

test('按技能名过滤，不被描述里的字母带偏', async () => {
  const items = [
    { name: 'internal-comms', description: '内部沟通', path: '/s/a', root: '/s', shadowed: false },
    {
      name: 'frontend-design',
      description: 'intentional visual design',
      path: '/s/b',
      root: '/s',
      shadowed: false,
    },
    {
      name: 'security-best-practices',
      description: 'security review',
      path: '/s/c',
      root: '/s',
      shadowed: false,
    },
  ]
  const client = { listSkills: vi.fn().mockResolvedValue({ items }) }
  const wrapper = mount(MessageComposer, {
    props: { modelValue: '', disabled: false, busy: false, sending: false, stopping: false },
    global: { provide: { [appContextKey as symbol]: { client } } },
  })
  await flushPromises()

  await wrapper.get('textarea').setValue('/in')
  await wrapper.setProps({ modelValue: '/in' })

  expect(wrapper.text()).toContain('internal-comms')
  expect(wrapper.text()).not.toContain('frontend-design')
})
