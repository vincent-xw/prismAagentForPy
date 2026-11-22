import { reactive } from 'vue'
import { CoreApiError, createCoreClient } from '@/lib/api/client'
import type { HealthDto, ToolDto } from '@/lib/api/contracts'

const tokenKey = 'prism-ui.api-token'
export type AccessStatus =
  'unverified' | 'checking' | 'ready' | 'unauthorized' | 'unreachable' | 'protocol-error'

// 只有受保护查询成功才能确认访问，健康检查与模型能力保持独立。
export function createConnection({
  basePath,
  fetcher,
  storage,
  onCredentialsChanged,
}: {
  basePath: string
  fetcher: typeof fetch
  storage: Storage
  onCredentialsChanged: () => void
}) {
  let token: string | null = null
  let verification = 0
  const state = reactive({
    status: 'unverified' as AccessStatus,
    health: null as HealthDto | null,
    healthChecking: false,
    healthError: null as string | null,
    error: null as string | null,
    storageError: null as string | null,
    tools: [] as ToolDto[],
    step: 0,
    basePath,
  })
  try {
    token = storage.getItem(tokenKey)
  } catch {
    state.storageError = '无法读取凭据，本次连接仅在当前页面生效。'
  }
  const client = createCoreClient({ basePath, getToken: () => token, fetcher })
  function failure(error: unknown): AccessStatus {
    return error instanceof CoreApiError && error.status === 401
      ? 'unauthorized'
      : error instanceof CoreApiError && error.kind === 'protocol'
        ? 'protocol-error'
        : 'unreachable'
  }
  async function checkHealth() {
    state.healthChecking = true
    state.healthError = null
    state.health = null
    try {
      state.health = await client.health()
      return true
    } catch (error) {
      state.healthError = error instanceof Error ? error.message : '服务检查失败。'
      return false
    } finally {
      state.healthChecking = false
    }
  }
  async function verifyAccess(candidate: string) {
    const version = ++verification
    state.status = 'checking'
    state.error = null
    if (!candidate.trim()) {
      state.status = 'unverified'
      state.error = '请输入 API Token。'
      return false
    }
    try {
      const response = await createCoreClient({
        basePath,
        getToken: () => candidate,
        fetcher,
      }).listTools()
      if (version !== verification) return false
      token = candidate
      state.tools = response.items
      state.status = 'ready'
      try {
        storage.setItem(tokenKey, candidate)
        state.storageError = null
      } catch {
        state.storageError = '无法保存凭据，已验证的 Token 仅在当前页面生效。'
      }
      // 成功重验也要重建已因 401 释放的控制器，即使 Token 文本未变化。
      onCredentialsChanged()
      return true
    } catch (error) {
      if (version !== verification) return false
      state.status = failure(error)
      state.error = error instanceof Error ? error.message : '访问验证失败。'
      return false
    }
  }
  function clearToken() {
    verification++
    token = null
    state.status = 'unverified'
    state.tools = []
    state.error = null
    state.step = 1
    try {
      storage.removeItem(tokenKey)
    } catch {
      state.storageError = '浏览器拒绝清除存储，请关闭当前标签页并检查浏览器权限。'
    }
    onCredentialsChanged()
  }
  function invalidate() {
    verification++
    state.step = 1
    state.status = 'unauthorized'
    state.error = '访问凭据已失效，请重新验证。'
  }
  return { state, getToken: () => token, checkHealth, verifyAccess, clearToken, invalidate }
}
export type ConnectionController = ReturnType<typeof createConnection>
