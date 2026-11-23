import { mount } from '@vue/test-utils'
import { shallowRef } from 'vue'
import { expect, test, vi } from 'vitest'

import ExecutionPage from '@/features/runs/ExecutionPage.vue'
import { appContextKey } from '@/app/context'
import { createRunProjection } from '@/features/runs/projection'
import { runDto } from '../support/fixtures'

vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { sessionId: 's1' }, query: {} }),
  useRouter: () => ({ push: vi.fn() }),
}))

test('执行详情作为独立页面渲染当前 Run', () => {
  const controller = {
    state: {
      selectedSessionId: 's1',
      sessions: [],
      selectedRunId: 'r1',
      runs: { r1: createRunProjection(runDto()) },
    },
    selectRun: vi.fn(async () => {}),
    openSession: vi.fn(async () => {}),
  }
  const wrapper = mount(ExecutionPage, {
    global: {
      provide: {
        [appContextKey as symbol]: { conversation: shallowRef(controller) },
      },
    },
  })

  expect(wrapper.text()).toContain('执行详情')
  expect(wrapper.text()).toContain('r1')
})
