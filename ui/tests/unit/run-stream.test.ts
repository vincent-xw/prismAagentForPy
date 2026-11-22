import { afterEach, expect, test, vi } from 'vitest'
import { createRunStream } from '@/lib/api/run-stream'
import { runDto } from '../support/fixtures'
import { frame, streamResponse } from '../support/streams'

afterEach(() => vi.useRealTimers())
function options(fetcher: typeof fetch) {
  return {
    basePath: '/api/v1',
    runId: 'r1',
    getToken: () => 'test',
    fetcher,
    getLastEventId: () => null,
    getRun: async () => runDto(),
    onRun: async () => {},
    onEvent: async () => {},
    onConnectionState: () => {},
  }
}
test('终态关闭不重连，401 不重连', async () => {
  const done = vi
    .fn<typeof fetch>()
    .mockResolvedValue(streamResponse([frame('run.succeeded', { message_id: 2 }, '1')]))
  await createRunStream(options(done)).start()
  expect(done).toHaveBeenCalledTimes(1)
  const denied = vi
    .fn<typeof fetch>()
    .mockResolvedValue(
      Response.json(
        { error: { code: 'UNAUTHORIZED', message: 'denied', request_id: 'q', details: {} } },
        { status: 401 },
      ),
    )
  await expect(createRunStream(options(denied)).start()).rejects.toMatchObject({ status: 401 })
  expect(denied).toHaveBeenCalledTimes(1)
})
test('中断按 500/1000/2000ms 最多三次重连', async () => {
  vi.useFakeTimers()
  const fetcher = vi.fn<typeof fetch>().mockImplementation(async () => streamResponse([]))
  const stream = createRunStream(options(fetcher))
  const pending = stream.start()
  const assertion = expect(pending).rejects.toThrow('中断')
  await vi.advanceTimersByTimeAsync(0)
  expect(fetcher).toHaveBeenCalledTimes(1)
  await vi.advanceTimersByTimeAsync(499)
  expect(fetcher).toHaveBeenCalledTimes(1)
  await vi.advanceTimersByTimeAsync(1)
  expect(fetcher).toHaveBeenCalledTimes(2)
  await vi.advanceTimersByTimeAsync(1000)
  expect(fetcher).toHaveBeenCalledTimes(3)
  await vi.advanceTimersByTimeAsync(2000)
  await assertion
  expect(fetcher).toHaveBeenCalledTimes(4)
})
test('停止取消待重连定时器，终态有限重放不因无终态事件循环', async () => {
  vi.useFakeTimers()
  const fetcher = vi.fn<typeof fetch>().mockImplementation(async () => streamResponse([]))
  const stream = createRunStream(options(fetcher))
  const pending = stream.start()
  await vi.advanceTimersByTimeAsync(0)
  stream.stop()
  await pending
  await vi.runAllTimersAsync()
  expect(fetcher).toHaveBeenCalledTimes(1)
  expect(vi.getTimerCount()).toBe(0)
  await createRunStream({
    ...options(fetcher),
    getRun: async () => runDto({ status: 'succeeded' }),
  }).start()
  expect(fetcher).toHaveBeenCalledTimes(2)
})
