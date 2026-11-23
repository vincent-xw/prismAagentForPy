import { expect, test, vi } from 'vitest'

import { openRunStream } from '@/lib/api/sse'
import { frame, streamResponse } from '../support/streams'

test('单条无法解析的事件被跳过，后续事件继续处理', async () => {
  const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
  const fetcher = vi
    .fn<typeof fetch>()
    .mockResolvedValue(
      streamResponse([
        'event: tool.requested\ndata: {"type":"tool.requested","run_id":"r1"}\n\n',
        frame('run.started', {}, '2'),
      ]),
    )
  const received: string[] = []
  await openRunStream({
    basePath: '/api/v1',
    runId: 'r1',
    getToken: () => 'test',
    afterEventId: null,
    signal: new AbortController().signal,
    fetcher,
    onEvent: async (event) => {
      received.push(event.type)
    },
  })

  expect(received).toEqual(['run.started'])
  expect(warn).toHaveBeenCalled()
})
