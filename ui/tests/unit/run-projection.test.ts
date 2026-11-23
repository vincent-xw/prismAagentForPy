import { expect, test } from 'vitest'
import {
  applyRunEvent,
  createRunProjection,
  reconcileRunMessages,
} from '@/features/runs/projection'
import { parseCoreEvent } from '@/lib/api/contracts'
import { messageDto, runDto } from '../support/fixtures'

const event = (type: string, id: string | null, data = {}) =>
  parseCoreEvent(type, id, { type, run_id: 'r1', ...data })
const request = () =>
  event('tool.requested', '1', {
    call_id: 'c1',
    tool_name: 'demo',
    execution_mode: 'remote',
    input: { q: 1 },
    input_digest: 'digest',
  })

test('终态 Run 重放不显示已经持久化的临时 delta', () => {
  const state = createRunProjection(runDto({ status: 'succeeded' }))
  applyRunEvent(state, event('message.delta', null, { text: '已落库' }))
  expect(state.transientText).toBe('')
})
test('持久事件去重与跨 Run 校验', () => {
  const state = createRunProjection(runDto())
  applyRunEvent(state, request())
  applyRunEvent(state, request())
  expect(state.tools).toHaveLength(1)
  expect(() => applyRunEvent(state, { ...request(), run_id: 'other' })).toThrow()
})
test('持久消息替换当前片段，不清除下一轮临时输出', () => {
  const state = createRunProjection(runDto())
  applyRunEvent(state, event('message.delta', null, { text: '你好' }))
  applyRunEvent(state, event('assistant.completed', '1', { message_id: 2, tool_call_ids: [] }))
  applyRunEvent(state, event('message.delta', null, { text: '第二轮' }))
  reconcileRunMessages(state, [messageDto({ id: 2, role: 'assistant', content: '你好' })])
  expect(state.pendingSegments).toHaveLength(0)
  expect(state.transientText).toBe('第二轮')
})
test('成功不从输出形状猜测，消息未关联时明确 incomplete', () => {
  const state = createRunProjection(runDto())
  applyRunEvent(state, request())
  applyRunEvent(
    state,
    event('tool.completed', '2', { call_id: 'c1', tool_name: 'demo', message_id: 3 }),
  )
  expect(state.tools[0]?.status).toBe('incomplete')
  reconcileRunMessages(state, [
    messageDto({ id: 3, role: 'tool', tool_call_id: 'c1', content: { error: '只是数据' } }),
  ])
  expect(state.tools[0]?.status).toBe('succeeded')
  expect(state.tools[0]?.output).toEqual({ error: '只是数据' })
})
test.each([
  ['tool.failed', 'RUN_CANCELLED', 'cancelled'],
  ['tool.expired', 'REMOTE_TOOL_TIMEOUT', 'expired'],
  ['tool.failed', 'PROCESS_INTERRUPTED', 'failed'],
])('工具 %s/%s 恢复为 %s', (type, code, expected) => {
  const state = createRunProjection(runDto())
  applyRunEvent(state, request())
  applyRunEvent(
    state,
    event(type, '2', {
      call_id: 'c1',
      tool_name: 'demo',
      message_id: 3,
      error_code: code,
      error_message: 'closed',
    }),
  )
  const messages = [
    messageDto({ id: 3, role: 'tool', tool_call_id: 'c1', content: { error: { code } } }),
  ]
  reconcileRunMessages(state, messages)
  expect(state.tools[0]?.status).toBe(expected)
  const restored = createRunProjection(runDto())
  applyRunEvent(restored, request())
  applyRunEvent(
    restored,
    event(type, '2', {
      call_id: 'c1',
      tool_name: 'demo',
      message_id: 3,
      error_code: code,
      error_message: 'closed',
    }),
  )
  reconcileRunMessages(restored, messages)
  expect(restored.tools).toEqual(state.tools)
})

import { createRunProjection as _createRunProjection } from '@/features/runs/projection'
import { runDto as _runDto } from '../support/fixtures'

test('从事件投影出待审批调用并在批准后移除', () => {
  const state = _createRunProjection(_runDto())
  const required = applyRunEvent(state, {
    id: '1',
    type: 'tool.approval_required',
    run_id: 'r1',
    call_id: 'c1',
    tool_name: 'file_write',
    path: 'a.md',
    mode: 'overwrite',
    bytes: 3,
  } as never)
  expect(required.pendingApprovals).toEqual([
    { callId: 'c1', toolName: 'file_write', path: 'a.md', mode: 'overwrite', bytes: 3 },
  ])
  const approved = applyRunEvent(state, {
    id: '2',
    type: 'tool.approved',
    run_id: 'r1',
    call_id: 'c1',
  } as never)
  expect(approved.pendingApprovals).toEqual([])
})

test('脱敏的 tool.requested 仍能驱动待审批卡片', () => {
  const state = _createRunProjection(_runDto())
  applyRunEvent(state, {
    id: '1',
    type: 'tool.requested',
    run_id: 'r1',
    call_id: 'c1',
    tool_name: 'file_write',
    execution_mode: 'local',
    path: '周报.md',
    mode: 'create',
    bytes: 669,
    input_digest: 'sha256:x',
  } as never)
  applyRunEvent(state, {
    id: '2',
    type: 'tool.approval_required',
    run_id: 'r1',
    call_id: 'c1',
    tool_name: 'file_write',
    path: '周报.md',
    mode: 'create',
    bytes: 669,
  } as never)

  expect(state.tools).toHaveLength(1)
  expect(state.pendingApprovals).toEqual([
    { callId: 'c1', toolName: 'file_write', path: '周报.md', mode: 'create', bytes: 669 },
  ])
})
