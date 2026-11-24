import { mount } from '@vue/test-utils'
import { expect, test, vi } from 'vitest'

import { appContextKey } from '@/app/context'
import RunInspector from '@/features/runs/RunInspector.vue'
import { createRunProjection } from '@/features/runs/projection'
import { runDto } from '../support/fixtures'

function genericProjection() {
  const projection = createRunProjection(runDto({ status: 'waiting_for_approval' }))
  projection.pendingApprovals.push({
    callId: 'c1',
    toolName: 'mcp__demo__search',
    kind: 'generic',
    path: '',
    mode: '',
    bytes: 0,
    inputPreview: '{"query": "订单 123"}',
  })
  return projection
}

test('generic 审批展示工具名与输入参数', () => {
  const client = { getApprovalPreview: vi.fn(), decideApproval: vi.fn() }
  const wrapper = mount(RunInspector, {
    props: { projection: genericProjection() },
    global: {
      provide: { [appContextKey as symbol]: { client } },
    },
  })

  expect(wrapper.text()).toContain('mcp__demo__search')
  expect(wrapper.text()).toContain('允许执行')
  expect(wrapper.text()).toContain('订单 123')
})
