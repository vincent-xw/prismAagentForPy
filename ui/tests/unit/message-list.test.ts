import { mount } from '@vue/test-utils'
import { expect, test } from 'vitest'

import MessageList from '@/features/sessions/MessageList.vue'
import { messageDto } from '../support/fixtures'

test('assistant 消息里的 Markdown 表格渲染为 table', () => {
  const wrapper = mount(MessageList, {
    props: {
      messages: [
        messageDto({
          role: 'assistant',
          content: '| 名称 | 数量 |\n| --- | --- |\n| 苹果 | 2 |',
        }),
      ],
      projection: null,
      loading: false,
    },
  })

  expect(wrapper.find('table').exists()).toBe(true)
  expect(wrapper.text()).toContain('苹果')
  expect(wrapper.text()).not.toContain('| --- |')
})

test('user 消息保持纯文本展示', () => {
  const wrapper = mount(MessageList, {
    props: {
      messages: [messageDto({ role: 'user', content: '| a | b |' })],
      projection: null,
      loading: false,
    },
  })

  expect(wrapper.find('table').exists()).toBe(false)
})
