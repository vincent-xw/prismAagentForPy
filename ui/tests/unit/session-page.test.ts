import { expect, test, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { shallowRef, ref } from 'vue'
import SessionPage from '@/features/sessions/SessionPage.vue'
import { appContextKey, type AppContext } from '@/app/context'
import { createConversation } from '@/features/sessions/conversation'
import { createCoreClient } from '@/lib/api/client'
import { createConnection } from '@/features/connection/connection'
import { createRunProjection } from '@/features/runs/projection'
import { runDto } from '../support/fixtures'

test('查看历史执行详情仍展示当前活动 Run 的流式输出', () => {
  vi.stubGlobal('matchMedia', () => Object.assign(new EventTarget(), { matches: false }))
  const client = createCoreClient({
    basePath: '/api/v1',
    getToken: () => null,
    fetcher: vi.fn<typeof fetch>(),
  })
  const controller = createConversation({
    client,
    createStream: () => ({ start: async () => {}, stop: () => {} }),
  })
  controller.state.selectedSessionId = 's1'
  controller.state.runs.r1 = createRunProjection(runDto())
  controller.state.runs.r1.transientText = '当前正在输出'
  controller.state.runs.old = createRunProjection(runDto({ id: 'old', status: 'succeeded' }))
  controller.state.selectedRunId = 'old'
  const connection = createConnection({
    basePath: '/api/v1',
    fetcher: vi.fn<typeof fetch>(),
    storage: sessionStorage,
    onCredentialsChanged: () => {},
  })
  const wrapper = mount(SessionPage, {
    global: {
      provide: {
        [appContextKey as symbol]: {
          conversation: shallowRef(controller),
          connection,
          wizardOpen: ref(false),
        } as AppContext,
      },
    },
  })
  expect(wrapper.get('[role="log"]').text()).toContain('当前正在输出')
  wrapper.unmount()
  controller.dispose()
})
