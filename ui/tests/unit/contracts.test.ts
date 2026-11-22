import { expect, test } from 'vitest'
import { sessionSchema, runSchema, toolsSchema, parseCoreEvent } from '@/lib/api/contracts'
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
