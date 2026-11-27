import { mount } from '@vue/test-utils'
import { expect, test } from 'vitest'

import RunInspector from '@/features/runs/RunInspector.vue'
import { createRunProjection } from '@/features/runs/projection'
import { runDto } from '../support/fixtures'

const run = runDto({ status: 'succeeded' })

test('执行详情只展示工具明细', () => {
  const wrapper = mount(RunInspector, {
    props: { projection: createRunProjection(run) },
    global: { stubs: { ToolCallCard: true } },
  })

  expect(wrapper.text()).toContain('工具调用')
  expect(wrapper.text()).toContain('本次运行没有工具调用')
  expect(wrapper.text()).not.toContain('RUN STATUS')
  expect(wrapper.text()).not.toContain('执行步数')
})
