import type { z } from 'zod'
import {
  errorSchema,
  healthSchema,
  messagesSchema,
  runSchema,
  sessionSchema,
  sessionsSchema,
  toolsSchema,
} from './contracts'

export class CoreApiError extends Error {
  // 业务错误字段仅在服务实际返回时赋值，不补造 code 或 request_id。
  code?: string
  requestId?: string
  details?: unknown
  constructor(
    public kind: 'http' | 'network' | 'protocol',
    message: string,
    public status?: number,
  ) {
    super(message)
    this.name = 'CoreApiError'
  }
}
export interface ClientOptions {
  basePath: string
  getToken: () => string | null
  fetcher: typeof fetch
}

// HTTP 和 SSE 共用错误分类，非法 HTML 错误页仍保留实际 HTTP 状态。
export async function assertResponse(response: Response): Promise<void> {
  if (response.ok) return
  let value: unknown
  try {
    value = await response.json()
  } catch {
    throw new CoreApiError(
      'protocol',
      `服务返回非 JSON 错误响应（HTTP ${response.status}）。`,
      response.status,
    )
  }
  const parsed = errorSchema.safeParse(value)
  if (!parsed.success)
    throw new CoreApiError(
      'protocol',
      `错误响应不符合 Core 协议（HTTP ${response.status}）。`,
      response.status,
    )
  const error = new CoreApiError('http', parsed.data.error.message, response.status)
  error.code = parsed.data.error.code
  error.requestId = parsed.data.error.request_id
  error.details = parsed.data.error.details
  throw error
}
export function createCoreClient({ basePath, getToken, fetcher }: ClientOptions) {
  async function request<T>(
    path: string,
    schema: z.ZodType<T>,
    method: 'GET' | 'POST',
    body: unknown,
    signal?: AbortSignal,
    protectedRequest = true,
  ): Promise<T> {
    const headers = new Headers({ Accept: 'application/json' })
    const token = getToken()
    if (protectedRequest && token !== null) headers.set('Authorization', `Bearer ${token}`)
    if (body !== undefined) headers.set('Content-Type', 'application/json')
    let response: Response
    try {
      response = await fetcher(`${basePath}${path}`, {
        method,
        headers,
        ...(body === undefined ? {} : { body: JSON.stringify(body) }),
        ...(signal ? { signal } : {}),
      })
    } catch (error) {
      if (signal?.aborted) throw error
      throw new CoreApiError(
        'network',
        '无法连接服务。请求结果可能未确认，请先刷新会话，不要重复发送。',
      )
    }
    await assertResponse(response)
    try {
      return schema.parse(await response.json())
    } catch {
      throw new CoreApiError(
        'protocol',
        '服务响应不符合 Core 协议，请检查服务版本。',
        response.status,
      )
    }
  }
  return {
    health: (signal?: AbortSignal) =>
      request('/health', healthSchema, 'GET', undefined, signal, false),
    listSessions: (signal?: AbortSignal) =>
      request('/sessions', sessionsSchema, 'GET', undefined, signal),
    createSession: (title: string | null, signal?: AbortSignal) =>
      request('/sessions', sessionSchema, 'POST', { title }, signal),
    getSession: (id: string, signal?: AbortSignal) =>
      request(`/sessions/${encodeURIComponent(id)}`, sessionSchema, 'GET', undefined, signal),
    listMessages: (id: string, signal?: AbortSignal) =>
      request(
        `/sessions/${encodeURIComponent(id)}/messages`,
        messagesSchema,
        'GET',
        undefined,
        signal,
      ),
    createRun: (sessionId: string, body: { input: string }, signal?: AbortSignal) =>
      request(`/sessions/${encodeURIComponent(sessionId)}/runs`, runSchema, 'POST', body, signal),
    getRun: (id: string, signal?: AbortSignal) =>
      request(`/runs/${encodeURIComponent(id)}`, runSchema, 'GET', undefined, signal),
    cancelRun: (id: string, signal?: AbortSignal) =>
      request(`/runs/${encodeURIComponent(id)}/cancel`, runSchema, 'POST', undefined, signal),
    listTools: (signal?: AbortSignal) => request('/tools', toolsSchema, 'GET', undefined, signal),
  }
}
export type CoreClient = ReturnType<typeof createCoreClient>
