import { mount } from '@vue/test-utils'
import { expect, test, vi } from 'vitest'

import { appContextKey } from '@/app/context'
import ApprovalCard from '@/features/runs/ApprovalCard.vue'
import type { PendingApproval } from '@/features/runs/projection'

const genericItem: PendingApproval = {
  callId: 'c1',
  toolName: 'mcp__demo__search',
  kind: 'generic',
  path: '',
  mode: '',
  bytes: 0,
  inputPreview: '{"query": "订单 123"}',
}

test('通用审批展示工具名与参数，批准后回调', async () => {
  const decideApproval = vi.fn().mockResolvedValue({ call: {}, run: {} })
  const client = { decideApproval, getApprovalPreview: vi.fn() }
  const wrapper = mount(ApprovalCard, {
    props: { runId: 'run-1', item: genericItem },
    global: { provide: { [appContextKey as symbol]: { client } } },
  })

  expect(wrapper.text()).toContain('mcp__demo__search')
  expect(wrapper.text()).toContain('订单 123')
  await wrapper.get('button').trigger('click')
  expect(decideApproval).toHaveBeenCalledWith('run-1', 'c1', 'approve', null)
  expect(wrapper.emitted('decided')).toHaveLength(1)
})
