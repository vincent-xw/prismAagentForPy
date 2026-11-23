import { expect, test, vi } from 'vitest'
import { decodeSse, openRunStream } from '@/lib/api/sse'
import { frame, streamResponse } from '../support/streams'

test('逐字节中文 UTF-8、CRLF、心跳和多行 data 被正确解析', async () => {
  const bytes = new TextEncoder().encode(
    ': ping\r\nevent: test\r\ndata: 你好\r\ndata: 第二行\r\n\r\n',
  )
  const body = new ReadableStream<Uint8Array>({
    start(c) {
      for (const byte of bytes) c.enqueue(Uint8Array.of(byte))
      c.close()
    },
  })
  const events = []
  for await (const event of decodeSse(body, new AbortController().signal)) events.push(event)
  expect(events).toEqual([{ event: 'test', id: null, data: '你好\n第二行' }])
})
test('流携带 Token 和整数游标，等待异步事件处理后终止', async () => {
  const onEvent = vi.fn(async () => {})
  const fetcher = vi
    .fn<typeof fetch>()
    .mockResolvedValue(streamResponse([frame('run.succeeded', { message_id: 2 }, '42')]))
  const result = await openRunStream({
    basePath: '/api/v1',
    runId: 'r1',
    getToken: () => 'test-token',
    afterEventId: '41',
    onEvent,
    signal: new AbortController().signal,
    fetcher,
  })
  expect(result).toBe('terminal')
  expect(onEvent.mock.calls.length).toBe(1)
  const headers = new Headers(fetcher.mock.calls[0]?.[1]?.headers)
  expect(headers.get('Last-Event-ID')).toBe('41')
  expect(headers.get('Authorization')).toBe('Bearer test-token')
})
test('拒绝非 SSE 响应与错误 run_id', async () => {
  for (const response of [
    Response.json({}),
    streamResponse([frame('run.started', { run_id: 'other' }, '1')]),
  ]) {
    await expect(
      openRunStream({
        basePath: '/api/v1',
        runId: 'r1',
        getToken: () => null,
        afterEventId: null,
        onEvent: async () => {},
        signal: new AbortController().signal,
        fetcher: vi.fn<typeof fetch>().mockResolvedValue(response),
      }),
    ).rejects.toMatchObject({ kind: 'protocol' })
  }
})

test('非法游标事件被跳过而不是中断整个流', async () => {
  const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
  const onEvent = vi.fn(async () => {})
  const result = await openRunStream({
    basePath: '/api/v1',
    runId: 'r1',
    getToken: () => null,
    afterEventId: null,
    onEvent,
    signal: new AbortController().signal,
    fetcher: vi
      .fn<typeof fetch>()
      .mockResolvedValue(streamResponse([frame('run.started', {}, 'evt_42')])),
  })
  expect(result).toBe('interrupted')
  expect(onEvent).not.toHaveBeenCalled()
  expect(warn).toHaveBeenCalled()
})
