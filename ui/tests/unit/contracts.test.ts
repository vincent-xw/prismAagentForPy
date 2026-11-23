import { expect, test } from 'vitest'
import {
  approvalResponseSchema,
  parseCoreEvent,
  runSchema,
  sessionSchema,
  toolsSchema,
} from '@/lib/api/contracts'
import { parseApiBasePath } from '@/lib/api/config'
import { runDto, sessionDto } from '../support/fixtures'

test('保留合法 null 与空工具，拒绝必需字段缺失和非法状态', () => {
  expect(sessionSchema.parse(sessionDto()).title).toBeNull()
  expect(toolsSchema.parse({ items: [] }).items).toEqual([])
  expect(() => sessionSchema.parse({ title: null })).toThrow()
  expect(() => runSchema.parse({ ...runDto(), status: 'done' })).toThrow()
})
test('基路径拒绝缺失、跨域及查询片段', () => {
  expect(parseApiBasePath('/api/v1')).toBe('/api/v1')
  for (const input of [undefined, '', 'https://host/api', '//host/api', '/api?q=x', '/api#x']) {
    expect(() => parseApiBasePath(input)).toThrow()
  }
})
test('事件信封校验实际整数字符串游标与 delta 的无 ID 语义', () => {
  expect(
    parseCoreEvent('message.delta', null, { type: 'message.delta', run_id: 'r1', text: '你' }).id,
  ).toBeNull()
  expect(() =>
    parseCoreEvent('run.started', 'evt_42', { type: 'run.started', run_id: 'r1' }),
  ).toThrow()
  expect(() =>
    parseCoreEvent('tool.requested', '1', { type: 'tool.requested', run_id: 'r1' }),
  ).toThrow()
  expect(() => parseCoreEvent('unknown', '1', {})).toThrow()
})

test('接受审批等待状态与工作区绑定字段', () => {
  const run = runSchema.parse({ ...runDto(), status: 'waiting_for_approval', workspace_id: 'w1' })
  expect(run.status).toBe('waiting_for_approval')
  expect(run.workspace_id).toBe('w1')
})

test('审批响应必须同时包含 call 与 run', () => {
  const call = {
    id: 'c1',
    run_id: 'r1',
    tool_name: 'file_write',
    status: 'awaiting_approval',
    output: null,
    error_code: null,
    error_message: null,
    expires_at: null,
  }
  expect(approvalResponseSchema.safeParse({ call, run: runDto() }).success).toBe(true)
  expect(approvalResponseSchema.safeParse({ call }).success).toBe(false)
})

test('解析审批相关事件', () => {
  const required = parseCoreEvent('tool.approval_required', '5', {
    type: 'tool.approval_required',
    run_id: 'r1',
    call_id: 'c1',
    tool_name: 'file_write',
    path: 'a.md',
    mode: 'overwrite',
    bytes: 3,
  })
  expect(required.type).toBe('tool.approval_required')
  const waiting = parseCoreEvent('run.waiting_for_approval', '6', {
    type: 'run.waiting_for_approval',
    run_id: 'r1',
    call_ids: ['c1'],
  })
  expect(waiting.type).toBe('run.waiting_for_approval')
})
