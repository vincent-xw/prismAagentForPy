import type { Page } from '@playwright/test'
import { runDto, messageDto, sessionDto } from '../support/fixtures'
import { frame } from '../support/streams'
import type { RunDto, MessageDto } from '../../src/lib/api/contracts'
import { createServer, type ServerResponse } from 'node:http'

// 明确的 Core 路由夹具，未定义请求直接失败，不允许宽泛 200 掩盖接口错误。
export async function installCoreFixture(
  page: Page,
  mode: 'complete' | 'waiting' | 'failed' = 'complete',
) {
  const sessions = [sessionDto()]
  const messages: MessageDto[] = []
  const runs = new Map<string, RunDto>()
  const streams = new Map<string, ServerResponse>()
  const eventBodies = new Map<string, string>()
  // 浏览器实际读取持续分块的 HTTP 响应，而不是一次 fulfill 的静态字符串。
  const server = createServer((request, response) => {
    response.setHeader('Access-Control-Allow-Origin', 'http://127.0.0.1:3000')
    response.setHeader('Access-Control-Allow-Headers', 'authorization,last-event-id')
    if (request.method === 'OPTIONS') {
      response.writeHead(204)
      response.end()
      return
    }
    const id = request.url!.slice(1)
    const body = eventBodies.get(id)
    if (body === undefined) {
      response.writeHead(404)
      response.end()
      return
    }
    response.writeHead(200, { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-cache' })
    response.flushHeaders()
    streams.set(id, response)
    const frames = body.split('\n\n').filter(Boolean)
    let index = 0
    const timer = setInterval(() => {
      const chunk = frames[index++]
      if (chunk !== undefined) response.write(`${chunk}\n\n`)
      else if (mode === 'waiting' && runs.get(id)?.status !== 'cancelled')
        response.write(': ping\n\n')
      else {
        clearInterval(timer)
        response.end()
      }
    }, 25)
    response.on('close', () => {
      clearInterval(timer)
      streams.delete(id)
    })
  })
  await new Promise<void>((resolve) => server.listen(0, '127.0.0.1', resolve))
  const address = server.address()
  if (address === null || typeof address === 'string') throw new Error('SSE fixture server failed')
  page.once('close', () => {
    server.closeAllConnections()
    server.close()
  })
  let count = 0
  await page.route(/\/api\/v1(?:\/|$)/, async (route) => {
    const request = route.request()
    const path = new URL(request.url()).pathname
    const json = (value: unknown, status = 200) => route.fulfill({ status, json: value })
    if (path === '/api/v1/health')
      return json({ status: 'ok', service: 'Prism', version: '0.1', environment: 'test' })
    if (request.headers().authorization !== 'Bearer test-token')
      return json(
        {
          error: { code: 'UNAUTHORIZED', message: 'Token 无效', request_id: 'test-q', details: {} },
        },
        401,
      )
    if (path === '/api/v1/tools') return json({ items: [] })
    if (path === '/api/v1/sessions') {
      if (request.method() === 'POST') {
        const session = sessionDto({ id: `s${sessions.length + 1}` })
        sessions.unshift(session)
        return json(session, 201)
      }
      return json({ items: sessions })
    }
    const sessionMatch = /^\/api\/v1\/sessions\/([^/]+)(?:\/(messages|runs))?$/.exec(path)
    if (sessionMatch) {
      const sid = sessionMatch[1]!
      if (sessionMatch[2] === 'messages')
        return json({ items: messages.filter((message) => message.session_id === sid) })
      if (sessionMatch[2] === 'runs' && request.method() === 'POST') {
        if (
          [...runs.values()].some(
            (run) => run.session_id === sid && ['running', 'waiting_for_tool'].includes(run.status),
          )
        )
          return json(
            {
              error: {
                code: 'RUN_CONFLICT',
                message: '已有活动运行',
                request_id: 'q',
                details: {},
              },
            },
            409,
          )
        const input = request.postDataJSON().input as string
        const run = runDto({ id: `r${++count}`, session_id: sid, input })
        runs.set(run.id, run)
        messages.push(
          messageDto({ id: messages.length + 1, session_id: sid, run_id: run.id, content: input }),
        )
        return json(run, 202)
      }
      const session = sessions.find((item) => item.id === sid)
      if (session) return json(session)
    }
    const runMatch = /^\/api\/v1\/runs\/([^/]+)(?:\/(events|cancel))?$/.exec(path)
    if (runMatch) {
      const run = runs.get(runMatch[1]!)
      if (!run) throw new Error(`Missing fixture run ${path}`)
      if (runMatch[2] === 'cancel') {
        run.cancel_requested_at = '2026-11-22T00:01:00Z'
        setTimeout(() => {
          run.status = 'cancelled'
          streams.get(run.id)?.write(frame('run.cancelled', { run_id: run.id }, '4'))
          streams.get(run.id)?.end()
        }, 180)
        return json(run)
      }
      if (runMatch[2] === 'events') {
        const emit = (type: string, data: Record<string, unknown>, id: string | null) =>
          frame(type, { ...data, run_id: run.id }, id)
        let events = emit('run.started', {}, '1')
        if (mode === 'waiting') {
          run.status = 'waiting_for_tool'
          events += emit(
            'tool.requested',
            {
              call_id: 'c1',
              tool_name: 'external-tool',
              execution_mode: 'remote',
              input: { query: 'demo' },
              input_digest: 'digest',
            },
            '2',
          )
          events += emit('run.waiting_for_tool', { call_ids: ['c1'] }, '3')
        } else if (mode === 'failed') {
          run.status = 'failed'
          run.error_code = 'MODEL_FAILED'
          run.error_message = '模型请求失败'
          events += emit(
            'run.failed',
            { error_code: run.error_code, error_message: run.error_message },
            '2',
          )
        } else {
          const content = `已收到：${run.input}`
          let message = messages.find((item) => item.run_id === run.id && item.role === 'assistant')
          if (!message) {
            message = messageDto({
              id: messages.length + 1,
              session_id: run.session_id,
              run_id: run.id,
              role: 'assistant',
              content,
            })
            messages.push(message)
          }
          run.status = 'succeeded'
          run.output = content
          run.step_count = 1
          events += emit('message.delta', { text: content }, null)
          events += emit('assistant.completed', { message_id: message.id, tool_call_ids: [] }, '2')
          events += emit('run.succeeded', { message_id: message.id }, '3')
        }
        eventBodies.set(run.id, events)
        return route.continue({ url: `http://127.0.0.1:${address.port}/${run.id}` })
      }
      return json(run)
    }
    throw new Error(`Undefined fixture request: ${request.method()} ${path}`)
  })
}
export async function seedToken(page: Page) {
  await page.addInitScript(() => sessionStorage.setItem('prism-ui.api-token', 'test-token'))
}
