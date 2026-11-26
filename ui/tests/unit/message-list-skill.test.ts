import { mount } from '@vue/test-utils'
import { expect, test } from 'vitest'

import MessageList from '@/features/sessions/MessageList.vue'
import { messageDto } from '../support/fixtures'

test('skill_context 渲染为已加载技能且不是用户气泡', () => {
  const wrapper = mount(MessageList, {
    props: {
      messages: [
        messageDto({
          kind: 'skill_context',
          content: '<skill_content name="pdf-tools">\n# PDF\n</skill_content>',
        }),
      ],
      projection: null,
      loading: false,
    },
  })

  expect(wrapper.text()).toContain('已加载技能')
  expect(wrapper.text()).toContain('pdf-tools')
  expect(wrapper.findAll('[data-role="user"]')).toHaveLength(0)
})
