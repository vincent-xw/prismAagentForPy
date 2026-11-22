import { CoreApiError } from './client'
import { isTerminal, type CoreEvent, type RunDto } from './contracts'
import { openRunStream } from './sse'

export type ConnectionState = 'connecting' | 'connected' | 'reconnecting' | 'closed' | 'error'
export interface RunStreamOptions {
  basePath: string
  runId: string
  getToken: () => string | null
  fetcher: typeof fetch
  getLastEventId: () => string | null
  getRun: (signal: AbortSignal) => Promise<RunDto>
  onRun: (run: RunDto) => Promise<void>
  onEvent: (event: CoreEvent) => Promise<void>
  onConnectionState: (state: ConnectionState) => void
}
export type RunStream = ReturnType<typeof createRunStream>

// 自动恢复最多三次，手动重连创建新的生命周期；永不重发创建 Run 的 POST。
export function createRunStream(options: RunStreamOptions) {
  const abort = new AbortController()
  let active = false
  const delays = [500, 1000, 2000]
  async function pause(delay: number) {
    await new Promise<void>((resolve) => {
      const end = () => {
        clearTimeout(timer)
        abort.signal.removeEventListener('abort', end)
        resolve()
      }
      const timer = setTimeout(end, delay)
      abort.signal.addEventListener('abort', end, { once: true })
      if (abort.signal.aborted) end()
    })
  }
  async function start() {
    if (active || abort.signal.aborted) return
    active = true
    try {
      for (let attempt = 0; attempt <= delays.length && !abort.signal.aborted; attempt++) {
        options.onConnectionState(attempt === 0 ? 'connecting' : 'reconnecting')
        try {
          const run = await options.getRun(abort.signal)
          if (abort.signal.aborted) return
          await options.onRun(run)
          if (abort.signal.aborted) return
          options.onConnectionState('connected')
          const result = await openRunStream({
            ...options,
            afterEventId: options.getLastEventId(),
            signal: abort.signal,
          })
          if (abort.signal.aborted) return
          if (result === 'terminal' || isTerminal(run)) {
            await options.onRun(await options.getRun(abort.signal))
            return
          }
          throw new CoreApiError('network', '运行事件连接中断，请重新连接。')
        } catch (error) {
          if (abort.signal.aborted) return
          if (
            !(error instanceof CoreApiError) ||
            error.kind !== 'network' ||
            attempt === delays.length
          )
            throw error
          await pause(delays[attempt]!)
        }
      }
    } catch (error) {
      if (!abort.signal.aborted) {
        options.onConnectionState('error')
        throw error
      }
    } finally {
      active = false
      if (!abort.signal.aborted) options.onConnectionState('closed')
    }
  }
  return {
    start,
    stop() {
      abort.abort()
      options.onConnectionState('closed')
    },
  }
}
