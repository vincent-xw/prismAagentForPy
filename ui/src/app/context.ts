import { inject, shallowRef, type InjectionKey } from 'vue'
import { useTheme } from './theme/useTheme'
import { parseApiBasePath } from '@/lib/api/config'
import { createCoreClient } from '@/lib/api/client'
import { createRunStream } from '@/lib/api/run-stream'
import { createConnection } from '@/features/connection/connection'
import { createConversation, type ConversationController } from '@/features/sessions/conversation'

// 凭据存储获取本身也可能被浏览器拒绝；失败交由连接服务显式呈现。
function sessionStore(): Storage {
  try {
    return window.sessionStorage
  } catch {
    const unavailable = () => {
      throw new Error('浏览器拒绝凭据存储。')
    }
    return {
      length: 0,
      clear: unavailable,
      getItem: unavailable,
      key: unavailable,
      removeItem: unavailable,
      setItem: unavailable,
    }
  }
}
export function createAppContext() {
  const basePath = parseApiBasePath(import.meta.env.VITE_API_BASE_PATH)
  const theme = useTheme()
  const conversation = shallowRef<ConversationController>()
  const fetcher = window.fetch.bind(window)
  const connection = createConnection({
    basePath,
    fetcher,
    storage: sessionStore(),
    onCredentialsChanged: resetConversation,
  })
  const client = createCoreClient({ basePath, fetcher, getToken: connection.getToken })
  function makeConversation() {
    return createConversation({
      client,
      createStream: (options) =>
        createRunStream({ ...options, basePath, fetcher, getToken: connection.getToken }),
      onUnauthorized: () => {
        connection.invalidate()
      },
    })
  }
  function resetConversation() {
    const old = conversation.value
    const selected = old?.state.selectedSessionId
    const drafts = old ? { ...old.state.drafts } : {}
    old?.dispose()
    const next = makeConversation()
    Object.assign(next.state.drafts, drafts)
    next.state.selectedSessionId = selected ?? null
    conversation.value = next
  }
  resetConversation()
  async function initialize() {
    // 内置凭据默认可用：启动时不再做访问验证，直接进入工作台。
    return
  }
  function dispose() {
    conversation.value?.dispose()
    theme.dispose()
  }
  return { basePath, theme, connection, conversation, client, initialize, dispose }
}
export type AppContext = ReturnType<typeof createAppContext>
export const appContextKey: InjectionKey<AppContext> = Symbol('PrismAppContext')
export function useAppContext(): AppContext {
  const context = inject(appContextKey)
  if (!context) throw new Error('Prism 应用服务未装配。')
  return context
}
