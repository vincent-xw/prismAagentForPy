import type { z } from 'zod'
import {
  approvalPreviewSchema,
  approvalResponseSchema,
  compactResultSchema,
  errorSchema,
  fileResponseSchema,
  healthSchema,
  mcpServerSchema as mcpServerSchemaRef,
  mcpServersSchema,
  mcpToolsSchema,
  modelProfileProbeSchema,
  modelProfilesSchema,
  modelProfileSchema,
  messagesSchema,
  runSchema,
  searchResponseSchema,
  sessionSchema,
  sessionsSchema,
  skillDetailSchema,
  skillsSchema,
  toolsSchema,
  trajectorySchema,
  treeResponseSchema,
  workspaceListSchema,
  workspacePickSchema,
  workspaceSchema,
} from './contracts'
import type { McpServerPayload, ModelProfilePayload } from './contracts'

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
    method: 'GET' | 'POST' | 'PATCH' | 'DELETE',
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
  async function requestVoid(
    path: string,
    method: 'PATCH' | 'DELETE',
    body: unknown,
    signal?: AbortSignal,
  ): Promise<void> {
    const headers = new Headers({ Accept: 'application/json' })
    const token = getToken()
    if (token !== null) headers.set('Authorization', `Bearer ${token}`)
    if (body !== undefined) headers.set('Content-Type', 'application/json')
    const response = await fetcher(`${basePath}${path}`, {
      method,
      headers,
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
      ...(signal ? { signal } : {}),
    })
    await assertResponse(response)
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
    setSessionWorkspace: (id: string, workspaceId: string | null, signal?: AbortSignal) =>
      request(
        `/sessions/${encodeURIComponent(id)}/workspace`,
        sessionSchema,
        'POST',
        { workspace_id: workspaceId },
        signal,
      ),
    listMessages: (id: string, signal?: AbortSignal) =>
      request(
        `/sessions/${encodeURIComponent(id)}/messages`,
        messagesSchema,
        'GET',
        undefined,
        signal,
      ),
    createRun: (
      sessionId: string,
      body: { input: string; skill_name?: string | null },
      signal?: AbortSignal,
    ) =>
      request(`/sessions/${encodeURIComponent(sessionId)}/runs`, runSchema, 'POST', body, signal),
    listSkills: (signal?: AbortSignal) =>
      request('/skills', skillsSchema, 'GET', undefined, signal),
    getSkill: (name: string, signal?: AbortSignal) =>
      request(`/skills/${encodeURIComponent(name)}`, skillDetailSchema, 'GET', undefined, signal),
    getRun: (id: string, signal?: AbortSignal) =>
      request(`/runs/${encodeURIComponent(id)}`, runSchema, 'GET', undefined, signal),
    cancelRun: (id: string, signal?: AbortSignal) =>
      request(`/runs/${encodeURIComponent(id)}/cancel`, runSchema, 'POST', undefined, signal),
    listTools: (signal?: AbortSignal) => request('/tools', toolsSchema, 'GET', undefined, signal),
    listWorkspaces: (signal?: AbortSignal) =>
      request('/workspaces', workspaceListSchema, 'GET', undefined, signal),
    pickWorkspace: (signal?: AbortSignal) =>
      request('/workspaces/pick', workspacePickSchema, 'POST', undefined, signal),
    createWorkspace: (path: string, label: string | null, signal?: AbortSignal) =>
      request('/workspaces', workspaceSchema, 'POST', { path, label }, signal),
    getWorkspace: (id: string, signal?: AbortSignal) =>
      request(`/workspaces/${encodeURIComponent(id)}`, workspaceSchema, 'GET', undefined, signal),
    activateWorkspace: (id: string, signal?: AbortSignal) =>
      request(
        `/workspaces/${encodeURIComponent(id)}/activate`,
        workspaceSchema,
        'POST',
        undefined,
        signal,
      ),
    reindexWorkspace: (id: string, signal?: AbortSignal) =>
      request(
        `/workspaces/${encodeURIComponent(id)}/reindex`,
        workspaceSchema,
        'POST',
        undefined,
        signal,
      ),
    getTree: (id: string, path: string, signal?: AbortSignal) =>
      request(
        `/workspaces/${encodeURIComponent(id)}/tree?path=${encodeURIComponent(path)}`,
        treeResponseSchema,
        'GET',
        undefined,
        signal,
      ),
    getFile: (id: string, path: string, signal?: AbortSignal) =>
      request(
        `/workspaces/${encodeURIComponent(id)}/file?path=${encodeURIComponent(path)}`,
        fileResponseSchema,
        'GET',
        undefined,
        signal,
      ),
    searchWorkspace: (id: string, query: string, signal?: AbortSignal) =>
      request(
        `/workspaces/${encodeURIComponent(id)}/search?q=${encodeURIComponent(query)}`,
        searchResponseSchema,
        'GET',
        undefined,
        signal,
      ),
    getTrajectory: (sessionId: string, signal?: AbortSignal) =>
      request(
        `/sessions/${encodeURIComponent(sessionId)}/trajectory`,
        trajectorySchema,
        'GET',
        undefined,
        signal,
      ),
    compactSession: (sessionId: string, signal?: AbortSignal) =>
      request(
        `/sessions/${encodeURIComponent(sessionId)}/compact`,
        compactResultSchema,
        'POST',
        undefined,
        signal,
      ),
    listModelProfiles: (signal?: AbortSignal) =>
      request('/model-profiles', modelProfilesSchema, 'GET', undefined, signal),
    createModelProfile: (payload: ModelProfilePayload, signal?: AbortSignal) =>
      request('/model-profiles', modelProfileSchema, 'POST', payload, signal),
    updateModelProfile: (id: string, payload: ModelProfilePayload, signal?: AbortSignal) =>
      request(
        `/model-profiles/${encodeURIComponent(id)}`,
        modelProfileSchema,
        'PATCH',
        payload,
        signal,
      ),
    deleteModelProfile: (id: string, signal?: AbortSignal) =>
      requestVoid(`/model-profiles/${encodeURIComponent(id)}`, 'DELETE', undefined, signal),
    activateModelProfile: (id: string, signal?: AbortSignal) =>
      request(
        `/model-profiles/${encodeURIComponent(id)}/activate`,
        modelProfileSchema,
        'POST',
        undefined,
        signal,
      ),
    probeModelProfile: (id: string, signal?: AbortSignal) =>
      request(
        `/model-profiles/${encodeURIComponent(id)}/probe`,
        modelProfileProbeSchema,
        'POST',
        undefined,
        signal,
      ),
    listMcpServers: (signal?: AbortSignal) =>
      request('/mcp/servers', mcpServersSchema, 'GET', undefined, signal),
    createMcpServer: (payload: McpServerPayload, signal?: AbortSignal) =>
      request('/mcp/servers', mcpServerSchemaRef, 'POST', payload, signal),
    updateMcpServer: (id: string, payload: McpServerPayload, signal?: AbortSignal) =>
      request(
        `/mcp/servers/${encodeURIComponent(id)}`,
        mcpServerSchemaRef,
        'PATCH',
        payload,
        signal,
      ),
    deleteMcpServer: (id: string, signal?: AbortSignal) =>
      requestVoid(`/mcp/servers/${encodeURIComponent(id)}`, 'DELETE', undefined, signal),
    setMcpEnabled: (id: string, enabled: boolean, signal?: AbortSignal) =>
      request(
        `/mcp/servers/${encodeURIComponent(id)}/${enabled ? 'enable' : 'disable'}`,
        mcpServerSchemaRef,
        'POST',
        undefined,
        signal,
      ),
    reconnectMcp: (id: string, signal?: AbortSignal) =>
      request(
        `/mcp/servers/${encodeURIComponent(id)}/reconnect`,
        mcpServerSchemaRef,
        'POST',
        undefined,
        signal,
      ),
    getMcpTools: (id: string, signal?: AbortSignal) =>
      request(
        `/mcp/servers/${encodeURIComponent(id)}/tools`,
        mcpToolsSchema,
        'GET',
        undefined,
        signal,
      ),
    getApprovalPreview: (runId: string, callId: string, signal?: AbortSignal) =>
      request(
        `/runs/${encodeURIComponent(runId)}/tool-calls/${encodeURIComponent(callId)}/preview`,
        approvalPreviewSchema,
        'GET',
        undefined,
        signal,
      ),
    decideApproval: (
      runId: string,
      callId: string,
      decision: 'approve' | 'reject',
      reason: string | null,
      signal?: AbortSignal,
    ) =>
      request(
        `/runs/${encodeURIComponent(runId)}/tool-calls/${encodeURIComponent(callId)}/approval`,
        approvalResponseSchema,
        'POST',
        { decision, reason },
        signal,
      ),
  }
}
export type CoreClient = ReturnType<typeof createCoreClient>
