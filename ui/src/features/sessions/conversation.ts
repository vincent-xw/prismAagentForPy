import { reactive } from 'vue'
import { CoreApiError, type CoreClient } from '@/lib/api/client'
import { isTerminal, type MessageDto, type SessionDto, type RunDto } from '@/lib/api/contracts'
import type { ConnectionState, RunStream } from '@/lib/api/run-stream'
import {
  applyRunEvent,
  createRunProjection,
  reconcileRunMessages,
  type RunProjection,
} from '@/features/runs/projection'

export interface StreamCallbacks {
  runId: string
  getLastEventId: () => string | null
  getRun: (signal: AbortSignal) => Promise<RunDto>
  onRun: (run: RunDto) => Promise<void>
  onEvent: Parameters<typeof applyRunEvent>[1] extends infer E ? (event: E) => Promise<void> : never
  onConnectionState: (state: ConnectionState) => void
}
export type StreamFactory = (options: StreamCallbacks) => RunStream

// 控制器拥有请求和订阅；页面只消费响应式事实，不直接处理协议。
export function createConversation({
  client,
  createStream,
  onUnauthorized,
}: {
  client: CoreClient
  createStream: StreamFactory
  onUnauthorized?: () => void
}) {
  const state = reactive({
    sessions: [] as SessionDto[],
    selectedSessionId: null as string | null,
    drafts: {} as Record<string, string>,
    messages: {} as Record<string, MessageDto[]>,
    runs: {} as Record<string, RunProjection>,
    selectedRunId: null as string | null,
    sending: {} as Record<string, boolean>,
    cancelling: {} as Record<string, boolean>,
    loading: false,
    error: null as string | null,
    connection: 'closed' as ConnectionState,
  })
  let disposed = false
  let pageVersion = 0
  let streamVersion = 0
  let stream: RunStream | null = null
  const histories = new Set<RunStream>()
  const lifetime = new AbortController()
  let pageRequest: AbortController | null = null
  function closeStream() {
    streamVersion++
    stream?.stop()
    stream = null
  }
  function report(error: unknown) {
    if (disposed) return
    state.error = error instanceof Error ? error.message : '操作失败。'
    if (error instanceof CoreApiError && error.status === 401) {
      dispose()
      onUnauthorized?.()
    }
  }
  function validateRun(run: RunDto, sessionId: string) {
    if (run.session_id !== sessionId) throw new CoreApiError('protocol', '运行会话归属不一致。')
  }
  async function refreshMessages(sessionId: string, signal = lifetime.signal) {
    const response = await client.listMessages(sessionId, signal)
    if (response.items.some((message) => message.session_id !== sessionId))
      throw new CoreApiError('protocol', '消息会话归属不一致。')
    if (disposed || signal.aborted) return
    state.messages[sessionId] = response.items
    for (const projection of Object.values(state.runs)) {
      if (projection.run.session_id === sessionId) reconcileRunMessages(projection, response.items)
    }
  }
  async function connect(runId: string) {
    const projection = state.runs[runId]
    if (!projection || disposed) return
    closeStream()
    const version = streamVersion
    const sessionId = projection.run.session_id
    const valid = () =>
      !disposed && version === streamVersion && state.selectedSessionId === sessionId
    stream = createStream({
      runId,
      getLastEventId: () => projection.lastEventId,
      getRun: (signal) => client.getRun(runId, signal),
      onRun: async (run) => {
        if (!valid()) return
        validateRun(run, sessionId)
        projection.run = run
        // 生命周期快照意味着首次连接或断线恢复；临时 delta 无法重放，
        // 清除未经持久化确认的片段，随后以消息和完整事件恢复，避免重复残留。
        projection.transientText = ''
        projection.transientReasoning = ''
        try {
          await refreshMessages(sessionId)
        } catch (error) {
          // 已接受的 Run 继续建立事件订阅，瞬时消息查询失败单独反馈。
          // 401 会由 report 释放整个控制器；协议错误也不能伪造消息。
          report(error)
        }
        if (valid() && isTerminal(run)) {
          projection.transientText = ''
          projection.transientReasoning = ''
        }
      },
      onEvent: async (event) => {
        if (!valid()) return
        // 只有关联消息刷新成功才保留游标；失败重连仍能重放未处理事实。
        const before = structuredClone(JSON.parse(JSON.stringify(projection))) as RunProjection
        try {
          applyRunEvent(projection, event)
          if (event.id !== null) {
            const run = await client.getRun(runId, lifetime.signal)
            if (!valid()) return
            validateRun(run, sessionId)
            projection.run = run
            await refreshMessages(sessionId)
          }
        } catch (error) {
          Object.assign(projection, before)
          throw error
        }
      },
      onConnectionState: (value) => {
        if (valid()) state.connection = value
      },
    })
    void stream.start().catch((error: unknown) => {
      if (valid()) report(error)
    })
  }
  async function loadSessions() {
    try {
      const response = await client.listSessions(lifetime.signal)
      if (!disposed) state.sessions = response.items
    } catch (error) {
      report(error)
    }
  }
  async function openSession(id: string) {
    if (disposed) return
    const version = ++pageVersion
    closeStream()
    pageRequest?.abort()
    pageRequest = new AbortController()
    const signal = pageRequest.signal
    state.selectedSessionId = id
    state.selectedRunId = null
    state.loading = true
    state.error = null
    try {
      const session = await client.getSession(id, signal)
      if (disposed || version !== pageVersion) return
      if (session.id !== id) throw new CoreApiError('protocol', '会话响应归属不一致。')
      if (!state.sessions.some((item) => item.id === id)) state.sessions.unshift(session)
      await refreshMessages(id, signal)
      if (disposed || version !== pageVersion) return
      for (const cached of Object.values(state.runs)) {
        if (cached.run.session_id === id && !isTerminal(cached.run)) {
          const current = await client.getRun(cached.run.id, signal)
          if (disposed || version !== pageVersion) return
          validateRun(current, id)
          cached.run = current
        }
      }
      const latest = state.messages[id]?.at(-1)
      if (latest) {
        const run = await client.getRun(latest.run_id, signal)
        if (disposed || version !== pageVersion) return
        validateRun(run, id)
        // 页面恢复从起点投影，不复用孤立游标。
        state.runs[run.id] = createRunProjection(run)
        state.selectedRunId = run.id
        await connect(run.id)
      }
    } catch (error) {
      if (!signal.aborted && version === pageVersion) report(error)
    } finally {
      if (version === pageVersion && !disposed) state.loading = false
    }
  }
  async function createSession(title: string | null) {
    state.error = null
    try {
      const session = await client.createSession(title, lifetime.signal)
      if (disposed) return null
      state.sessions.unshift(session)
      await openSession(session.id)
      return session
    } catch (error) {
      report(error)
      return null
    }
  }
  async function send(text: string) {
    const sessionId = state.selectedSessionId
    if (!sessionId || disposed || !text.trim() || state.sending[sessionId]) return
    state.drafts[sessionId] = text
    if (
      Object.values(state.runs).some(
        (item) => item.run.session_id === sessionId && !isTerminal(item.run),
      )
    )
      return
    state.sending[sessionId] = true
    state.error = null
    try {
      const run = await client.createRun(sessionId, { input: text }, lifetime.signal)
      if (disposed) return
      validateRun(run, sessionId)
      state.runs[run.id] = createRunProjection(run)
      if (state.drafts[sessionId] === text) state.drafts[sessionId] = ''
      if (state.selectedSessionId === sessionId) {
        state.selectedRunId = run.id
        await connect(run.id)
      }
      await refreshMessages(sessionId)
    } catch (error) {
      if (disposed) return
      if (error instanceof CoreApiError && (error.status === 409 || error.kind === 'network')) {
        if (state.selectedSessionId === sessionId) await openSession(sessionId)
      }
      if (state.selectedSessionId === sessionId) report(error)
    } finally {
      state.sending[sessionId] = false
    }
  }
  async function cancel(runId: string) {
    if (disposed || state.cancelling[runId]) return
    state.cancelling[runId] = true
    try {
      const run = await client.cancelRun(runId, lifetime.signal)
      const projection = state.runs[runId]
      if (!disposed && projection) {
        validateRun(run, projection.run.session_id)
        if (!isTerminal(projection.run) || isTerminal(run)) projection.run = run
      }
    } catch (error) {
      report(error)
    } finally {
      state.cancelling[runId] = false
    }
  }
  async function selectRun(runId: string) {
    const sessionId = state.selectedSessionId
    if (!sessionId || disposed) return
    state.error = null
    try {
      const run = await client.getRun(runId, lifetime.signal)
      if (disposed || state.selectedSessionId !== sessionId) return
      validateRun(run, sessionId)
      if (!state.runs[runId]) state.runs[runId] = createRunProjection(run)
      state.selectedRunId = runId
      // 历史详情重放使用独立有限连接，不能关闭活动运行的实时订阅。
      if (isTerminal(run)) {
        const projection = state.runs[runId]!
        const history = createStream({
          runId,
          getLastEventId: () => projection.lastEventId,
          getRun: (signal) => client.getRun(runId, signal),
          onRun: async (value) => {
            if (!disposed) {
              projection.run = value
              await refreshMessages(sessionId)
            }
          },
          onEvent: async (event) => {
            if (!disposed && state.selectedSessionId === sessionId) {
              applyRunEvent(projection, event)
              await refreshMessages(sessionId)
            }
          },
          onConnectionState: () => {},
        })
        histories.add(history)
        try {
          await history.start()
        } finally {
          histories.delete(history)
        }
      }
    } catch (error) {
      report(error)
    }
  }
  function dispose() {
    disposed = true
    pageVersion++
    pageRequest?.abort()
    closeStream()
    for (const history of histories) history.stop()
    histories.clear()
    lifetime.abort()
  }
  return { state, loadSessions, createSession, openSession, send, cancel, selectRun, dispose }
}
export type ConversationController = ReturnType<typeof createConversation>
