import { expect, test, vi } from 'vitest'
import { createConnection } from '@/features/connection/connection'

test('健康检查不代表访问成功，拒绝候选 Token 不覆盖有效 Token', async () => {
  sessionStorage.clear()
  const changed = vi.fn()
  const fetcher = vi.fn<typeof fetch>().mockImplementation(async (url, options) => {
    if (String(url).endsWith('/health'))
      return Response.json({ status: 'ok', service: 'Prism', version: '1', environment: 'test' })
    const token = new Headers(options?.headers).get('Authorization')
    return token === 'Bearer good'
      ? Response.json({ items: [] })
      : Response.json(
          { error: { code: 'UNAUTHORIZED', message: '无权限', request_id: 'q', details: {} } },
          { status: 401 },
        )
  })
  const connection = createConnection({
    basePath: '/api/v1',
    fetcher,
    storage: sessionStorage,
    onCredentialsChanged: changed,
  })
  await connection.checkHealth()
  // 内置凭据：默认即就绪，无需先验证
  expect(connection.state.status).toBe('ready')
  expect(connection.getToken()).toBe('change-me')
  await connection.verifyAccess('bad')
  expect(connection.state.status).toBe('unauthorized')
  expect(connection.getToken()).toBe('change-me')
  await connection.verifyAccess('good')
  expect(connection.state.status).toBe('ready')
  expect(connection.state.tools).toEqual([])
  expect(changed).toHaveBeenCalledTimes(1)
  await connection.verifyAccess('bad')
  expect(connection.getToken()).toBe('good')
  expect(changed).toHaveBeenCalledTimes(1)
  connection.clearToken()
  expect(connection.getToken()).toBeNull()
  expect(changed).toHaveBeenCalledTimes(2)
  expect(fetcher.mock.calls.some((call) => call[1]?.method === 'POST')).toBe(false)
})
test('协议错误不能验证成功，存储失败明确提示本页有效', async () => {
  const storage = {
    getItem: () => null,
    setItem: () => {
      throw new Error('blocked')
    },
    removeItem: () => {},
    clear: () => {},
    key: () => null,
    length: 0,
  }
  const fetcher = vi.fn<typeof fetch>().mockResolvedValue(Response.json({ items: [{}] }))
  const connection = createConnection({
    basePath: '/api/v1',
    fetcher,
    storage,
    onCredentialsChanged: () => {},
  })
  await connection.verifyAccess('test')
  expect(connection.state.status).toBe('protocol-error')
  fetcher.mockResolvedValueOnce(Response.json({ items: [] }))
  await connection.verifyAccess('test')
  expect(connection.state.status).toBe('ready')
  expect(connection.state.storageError).toContain('当前页面')
})

test('凭据失效时回到未授权状态', () => {
  const connection = createConnection({
    basePath: '/api/v1',
    fetcher: vi.fn<typeof fetch>(),
    storage: sessionStorage,
    onCredentialsChanged: () => {},
  })
  connection.invalidate()
  expect(connection.state.status).toBe('unauthorized')
})
