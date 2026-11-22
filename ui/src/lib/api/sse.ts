import { CoreApiError, assertResponse } from './client'
import { parseCoreEvent, type CoreEvent } from './contracts'

export interface SseFrame {
  event: string
  id: string | null
  data: string
}

// SSE 行解析与字节解码分离，保留跨块 UTF-8 与 CRLF。
export async function* decodeSse(
  body: ReadableStream<Uint8Array>,
  signal: AbortSignal,
): AsyncIterable<SseFrame> {
  const reader = body.getReader()
  const decoder = new TextDecoder('utf-8', { fatal: true })
  let buffer = ''
  let event = 'message'
  let id: string | null = null
  let data: string[] = []
  const cancel = () => {
    void reader.cancel().catch(() => {})
  }
  signal.addEventListener('abort', cancel, { once: true })
  try {
    if (signal.aborted) return
    while (!signal.aborted) {
      const chunk = await reader.read()
      buffer += chunk.done ? decoder.decode() : decoder.decode(chunk.value, { stream: true })
      while (true) {
        const match = /\r\n|\r|\n/.exec(buffer)
        if (!match || (!chunk.done && match[0] === '\r' && match.index === buffer.length - 1)) break
        const line = buffer.slice(0, match.index)
        buffer = buffer.slice(match.index + match[0].length)
        if (line === '') {
          if (data.length) yield { event, id, data: data.join('\n') }
          event = 'message'
          id = null
          data = []
        } else if (!line.startsWith(':')) {
          const colon = line.indexOf(':')
          const field = colon === -1 ? line : line.slice(0, colon)
          const value = colon === -1 ? '' : line.slice(colon + 1).replace(/^ /, '')
          if (field === 'event') event = value
          if (field === 'id') id = value
          if (field === 'data') data.push(value)
        }
      }
      if (chunk.done) break
    }
  } finally {
    signal.removeEventListener('abort', cancel)
    await reader.cancel().catch(() => {})
    reader.releaseLock()
  }
}
export interface OpenStreamOptions {
  basePath: string
  runId: string
  getToken: () => string | null
  afterEventId: string | null
  onEvent: (event: CoreEvent) => Promise<void>
  signal: AbortSignal
  fetcher: typeof fetch
}
export async function openRunStream(
  options: OpenStreamOptions,
): Promise<'terminal' | 'interrupted'> {
  const headers = new Headers({ Accept: 'text/event-stream' })
  const token = options.getToken()
  if (token !== null) headers.set('Authorization', `Bearer ${token}`)
  if (options.afterEventId !== null) {
    if (!/^\d+$/.test(options.afterEventId)) throw new CoreApiError('protocol', '事件游标不合法。')
    headers.set('Last-Event-ID', options.afterEventId)
  }
  let response: Response
  try {
    response = await options.fetcher(
      `${options.basePath}/runs/${encodeURIComponent(options.runId)}/events`,
      { headers, signal: options.signal },
    )
  } catch (error) {
    if (options.signal.aborted) throw error
    throw new CoreApiError('network', '运行事件连接中断。')
  }
  await assertResponse(response)
  if (
    !response.headers.get('content-type')?.startsWith('text/event-stream') ||
    response.body === null ||
    response.status === 204
  ) {
    throw new CoreApiError('protocol', '运行事件响应不是有效 SSE 流。', response.status)
  }
  try {
    for await (const frame of decodeSse(response.body, options.signal)) {
      if (options.signal.aborted) return 'interrupted'
      let event: CoreEvent
      try {
        event = parseCoreEvent(frame.event, frame.id, JSON.parse(frame.data))
      } catch {
        throw new CoreApiError('protocol', '运行事件不符合 Core 协议。')
      }
      if (event.run_id !== options.runId) throw new CoreApiError('protocol', '运行事件归属不一致。')
      // 等待投影和持久消息同步成功，调用方才能推进游标。
      await options.onEvent(event)
      if (['run.succeeded', 'run.failed', 'run.cancelled'].includes(event.type)) return 'terminal'
    }
  } catch (error) {
    if (options.signal.aborted || error instanceof CoreApiError) throw error
    throw new CoreApiError('network', '运行事件连接中断。')
  }
  return 'interrupted'
}
