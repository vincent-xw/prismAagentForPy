import { expect, test, vi } from 'vitest'
import { createCoreClient } from '@/lib/api/client'
import { runDto } from '../support/fixtures'

test('创建 Run 只发送明确 input，并附带鉴权', async () => {
  const fetcher = vi.fn<typeof fetch>().mockResolvedValue(Response.json(runDto(), { status: 202 }))
  const client = createCoreClient({ basePath: '/api/v1', getToken: () => 'test-token', fetcher })
  await client.createRun('s1', { input: '你好' })
  expect(fetcher.mock.calls[0]?.[0]).toBe('/api/v1/sessions/s1/runs')
  const options = fetcher.mock.calls[0]?.[1]
  expect(options?.body).toBe('{"input":"你好"}')
  expect(new Headers(options?.headers).get('Authorization')).toBe('Bearer test-token')
})
test('区分 HTTP 错误和非法响应，保留实际状态', async () => {
  const fetcher = vi.fn<typeof fetch>()
  const client = createCoreClient({ basePath: '/api/v1', getToken: () => null, fetcher })
  fetcher.mockResolvedValueOnce(
    Response.json(
      { error: { code: 'UNAUTHORIZED', message: '无权限', details: {}, request_id: 'req1' } },
      { status: 401 },
    ),
  )
  await expect(client.listTools()).rejects.toMatchObject({
    kind: 'http',
    status: 401,
    code: 'UNAUTHORIZED',
    requestId: 'req1',
  })
  fetcher.mockResolvedValueOnce(new Response('<html>bad gateway</html>', { status: 502 }))
  await expect(client.listTools()).rejects.toMatchObject({ kind: 'protocol', status: 502 })
  fetcher.mockResolvedValueOnce(Response.json({ items: [{}] }))
  await expect(client.listSessions()).rejects.toMatchObject({ kind: 'protocol' })
})
test('POST 丢响应不重发，健康检查不携带 Token', async () => {
  const fetcher = vi.fn<typeof fetch>().mockRejectedValue(new TypeError('lost'))
  const client = createCoreClient({ basePath: '/api/v1', getToken: () => 'secret', fetcher })
  await expect(client.createRun('s1', { input: '你好' })).rejects.toMatchObject({ kind: 'network' })
  expect(fetcher).toHaveBeenCalledTimes(1)
  fetcher.mockResolvedValueOnce(
    Response.json({ status: 'ok', service: 'Prism', version: '1', environment: 'test' }),
  )
  await client.health()
  expect(new Headers(fetcher.mock.calls[1]?.[1]?.headers).has('Authorization')).toBe(false)
})
