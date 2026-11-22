import { expect, test, vi } from 'vitest'
import { createConversation, type StreamFactory } from '@/features/sessions/conversation'
import { createCoreClient } from '@/lib/api/client'
import { parseCoreEvent } from '@/lib/api/contracts'
import { messageDto, runDto, sessionDto, stamp } from '../support/fixtures'

function harness() {
  const fetcher = vi.fn<typeof fetch>()
  const streams: Parameters<StreamFactory>[0][] = []
  const stop = vi.fn()
  const createStream: StreamFactory = (options) => {
    streams.push(options)
    return { start: async () => {}, stop }
  }
  const client = createCoreClient({ basePath: '/api/v1', getToken: () => 'test', fetcher })
  return { fetcher, streams, stop, controller: createConversation({ client, createStream }) }
}
test('逆序返回不覆盖最后选中的会话', async () => {
  const h = harness()
  let resolve!: (value: Response) => void
  h.fetcher.mockImplementation(async (url) => {
    if (url === '/api/v1/sessions/s1')
      return new Promise<Response>((r) => {
        resolve = r
      })
    if (String(url).endsWith('/messages')) return Response.json({ items: [] })
    return Response.json(sessionDto({ id: 's2' }))
  })
  const first = h.controller.openSession('s1')
  await h.controller.openSession('s2')
  resolve(Response.json(sessionDto()))
  await first
  expect(h.controller.state.selectedSessionId).toBe('s2')
  expect(h.controller.state.loading).toBe(false)
  h.controller.dispose()
})
test('恢复工具等待从完整消息发现 Run，不使用虚构活动字段', async () => {
  const h = harness()
  h.fetcher.mockImplementation(async (url) => {
    if (String(url).endsWith('/messages')) return Response.json({ items: [messageDto()] })
    if (String(url).includes('/runs/')) return Response.json(runDto({ status: 'waiting_for_tool' }))
    return Response.json(sessionDto())
  })
  await h.controller.openSession('s1')
  expect(h.controller.state.runs.r1?.run.status).toBe('waiting_for_tool')
  expect(h.streams[0]?.getLastEventId()).toBeNull()
  h.controller.state.drafts.s1 = '不要丢弃'
  h.controller.dispose()
  expect(h.stop).toHaveBeenCalledTimes(1)
  expect(h.controller.state.drafts.s1).toBe('不要丢弃')
})
test('停止请求只记录服务事实，完成竞争不伪装为取消', async () => {
  const h = harness()
  h.fetcher.mockImplementation(async (url) => {
    if (String(url).endsWith('/messages')) return Response.json({ items: [messageDto()] })
    if (String(url).endsWith('/cancel'))
      return Response.json(runDto({ cancel_requested_at: stamp }))
    if (String(url).includes('/runs/')) return Response.json(runDto())
    return Response.json(sessionDto())
  })
  await h.controller.openSession('s1')
  await h.controller.cancel('r1')
  expect(h.controller.state.runs.r1?.run.status).toBe('running')
  expect(h.controller.state.runs.r1?.run.cancel_requested_at).toBe(stamp)
  await h.streams[0]?.onRun(runDto({ status: 'succeeded', output: '已完成' }))
  expect(h.controller.state.runs.r1?.run.status).toBe('succeeded')
  h.controller.dispose()
})
test('活动 Run 阻止重复发送，409 保留草稿并重新查询事实', async () => {
  const h = harness()
  let active = false
  h.fetcher.mockImplementation(async (url, options) => {
    if (options?.method === 'POST') {
      active = true
      return Response.json(
        {
          error: { code: 'RUN_CONFLICT', message: '已存在活动运行', request_id: 'q', details: {} },
        },
        { status: 409 },
      )
    }
    if (String(url).endsWith('/messages'))
      return Response.json({ items: active ? [messageDto()] : [] })
    if (String(url).includes('/runs/')) return Response.json(runDto())
    return Response.json(sessionDto())
  })
  await h.controller.openSession('s1')
  h.controller.state.drafts.s1 = '保留'
  await h.controller.send('保留')
  await h.controller.send('保留')
  expect(h.controller.state.drafts.s1).toBe('保留')
  expect(h.fetcher.mock.calls.filter((call) => call[1]?.method === 'POST')).toHaveLength(1)
  expect(h.controller.state.runs.r1?.run.status).toBe('running')
  h.controller.dispose()
})
test('POST 响应丢失只恢复查询，不自动重发', async () => {
  const h = harness()
  h.fetcher.mockImplementation(async (url, options) => {
    if (options?.method === 'POST') throw new TypeError('lost response')
    if (String(url).endsWith('/messages')) return Response.json({ items: [] })
    return Response.json(sessionDto())
  })
  await h.controller.openSession('s1')
  await h.controller.send('你好')
  expect(h.fetcher.mock.calls.filter((call) => call[1]?.method === 'POST')).toHaveLength(1)
  expect(h.controller.state.drafts.s1).toBe('你好')
  expect(h.controller.state.error).toContain('未确认')
  h.controller.dispose()
})
test('发送响应在切换后到达，不清除新草稿、不连接旧会话流', async () => {
  const h = harness()
  let resolve!: (value: Response) => void
  h.fetcher.mockImplementation(async (url, options) => {
    if (options?.method === 'POST')
      return new Promise<Response>((r) => {
        resolve = r
      })
    if (String(url).endsWith('/messages')) return Response.json({ items: [] })
    return Response.json(sessionDto({ id: String(url).endsWith('s2') ? 's2' : 's1' }))
  })
  await h.controller.openSession('s1')
  const send = h.controller.send('第一条')
  h.controller.state.drafts.s1 = '后来输入'
  await h.controller.openSession('s2')
  h.controller.state.drafts.s2 = '另一会话'
  resolve(Response.json(runDto(), { status: 202 }))
  await send
  expect(h.controller.state.selectedSessionId).toBe('s2')
  expect(h.controller.state.drafts.s1).toBe('后来输入')
  expect(h.controller.state.drafts.s2).toBe('另一会话')
  expect(h.streams).toHaveLength(0)
  h.controller.dispose()
})
test('停止订阅后旧事件不再写入，刷新历史按选择有限恢复', async () => {
  const h = harness()
  h.fetcher.mockImplementation(async (url) => {
    if (String(url).endsWith('s1/messages')) return Response.json({ items: [messageDto()] })
    if (String(url).endsWith('s2/messages')) return Response.json({ items: [] })
    if (String(url).includes('/runs/')) return Response.json(runDto())
    return Response.json(sessionDto({ id: String(url).endsWith('s2') ? 's2' : 's1' }))
  })
  await h.controller.openSession('s1')
  const old = h.streams[0]!
  await h.controller.openSession('s2')
  await old.onEvent(
    parseCoreEvent('message.delta', null, { type: 'message.delta', run_id: 'r1', text: '旧事件' }),
  )
  expect(h.controller.state.runs.r1?.transientText).toBe('')
  h.controller.dispose()
})

test('晚到的停止响应不能覆盖已经确认的终态', async () => {
  const h = harness()
  let resolve!: (value: Response) => void
  h.fetcher.mockImplementation(async (url) => {
    if (String(url).endsWith('/messages')) return Response.json({ items: [messageDto()] })
    if (String(url).endsWith('/cancel'))
      return new Promise<Response>((r) => {
        resolve = r
      })
    if (String(url).includes('/runs/')) return Response.json(runDto())
    return Response.json(sessionDto())
  })
  await h.controller.openSession('s1')
  const stopping = h.controller.cancel('r1')
  await h.streams[0]!.onRun(runDto({ status: 'succeeded', output: '完成' }))
  resolve(Response.json(runDto({ cancel_requested_at: stamp })))
  await stopping
  expect(h.controller.state.runs.r1?.run.status).toBe('succeeded')
  h.controller.dispose()
})

test('重新打开会话刷新缓存的活动 Run，不能被旧 running 阻止发送', async () => {
  const h = harness()
  let latest = 'r1'
  h.fetcher.mockImplementation(async (url, options) => {
    if (options?.method === 'POST') return Response.json(runDto({ id: 'r3' }), { status: 202 })
    if (String(url).endsWith('/messages'))
      return Response.json({ items: [messageDto({ run_id: latest })] })
    if (String(url).includes('/runs/'))
      return Response.json(
        runDto({
          id: String(url).split('/').at(-1)!,
          status: latest === 'r1' ? 'running' : 'succeeded',
        }),
      )
    return Response.json(sessionDto())
  })
  await h.controller.openSession('s1')
  latest = 'r2'
  await h.controller.openSession('s1')
  await h.controller.send('下一轮')
  expect(h.fetcher.mock.calls.filter((call) => call[1]?.method === 'POST')).toHaveLength(1)
  h.controller.dispose()
})

test('创建已接受的 Run 后消息补读失败仍然建立订阅', async () => {
  const h = harness()
  let accepted = false
  h.fetcher.mockImplementation(async (url, options) => {
    if (options?.method === 'POST') {
      accepted = true
      return Response.json(runDto(), { status: 202 })
    }
    if (String(url).endsWith('/messages'))
      return accepted
        ? Response.json(
            {
              error: { code: 'INTERNAL_ERROR', message: '读取失败', request_id: 'q', details: {} },
            },
            { status: 500 },
          )
        : Response.json({ items: [] })
    return Response.json(sessionDto())
  })
  await h.controller.openSession('s1')
  await h.controller.send('继续跟踪')
  expect(h.streams).toHaveLength(1)
  expect(h.controller.state.selectedRunId).toBe('r1')
  expect(h.controller.state.error).toContain('读取失败')
  h.controller.dispose()
})

test('401 停止全部历史详情流和主流，不只停止当前订阅', async () => {
  const h = harness()
  let release!: () => void
  h.fetcher.mockImplementation(async (url) => {
    if (String(url).endsWith('/messages')) return Response.json({ items: [messageDto()] })
    if (String(url).includes('/runs/')) return Response.json(runDto({ status: 'succeeded' }))
    return Response.json(sessionDto())
  })
  await h.controller.openSession('s1')
  const historyStop = vi.fn(() => release())
  // 真实外部请求通过客户端；只在订阅资源边界控制生命周期。
  const original = h.controller
  const fetcher = h.fetcher
  const client = createCoreClient({ basePath: '/api/v1', getToken: () => 'test', fetcher })
  const stops: ReturnType<typeof vi.fn>[] = []
  const controller = createConversation({
    client,
    createStream: () => {
      const stop = stops.length === 0 ? vi.fn() : historyStop
      stops.push(stop)
      return {
        start: () =>
          stops.length === 1
            ? Promise.resolve()
            : new Promise<void>((r) => {
                release = r
              }),
        stop,
      }
    },
  })
  await controller.openSession('s1')
  const pending = controller.selectRun('r1')
  await vi.waitFor(() => expect(stops).toHaveLength(2))
  fetcher.mockResolvedValueOnce(
    Response.json(
      { error: { code: 'UNAUTHORIZED', message: 'expired', request_id: 'q', details: {} } },
      { status: 401 },
    ),
  )
  await controller.loadSessions()
  expect(historyStop).toHaveBeenCalledTimes(1)
  await pending
  controller.dispose()
  original.dispose()
})

test('断线补读完成消息后清除所属临时片段，不能同时显示两份', async () => {
  const h = harness()
  let completed = false
  h.fetcher.mockImplementation(async (url) => {
    if (String(url).endsWith('/messages'))
      return Response.json({
        items: completed
          ? [messageDto(), messageDto({ id: 2, role: 'assistant', content: '完整输出' })]
          : [messageDto()],
      })
    if (String(url).includes('/runs/')) return Response.json(runDto())
    return Response.json(sessionDto())
  })
  await h.controller.openSession('s1')
  await h.streams[0]!.onEvent(
    parseCoreEvent('message.delta', null, { type: 'message.delta', run_id: 'r1', text: '完整' }),
  )
  completed = true
  await h.streams[0]!.onRun(runDto({ status: 'waiting_for_tool' }))
  expect(h.controller.state.messages.s1?.some((item) => item.content === '完整输出')).toBe(true)
  expect(h.controller.state.runs.r1?.transientText).toBe('')
  h.controller.dispose()
})
