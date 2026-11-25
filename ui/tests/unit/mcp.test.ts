import { expect, test, vi } from 'vitest'

import { createMcpController } from '@/features/mcp/mcp'
import type { CoreClient } from '@/lib/api/client'

const server = {
  id: 's1',
  name: 'demo',
  transport: 'stdio' as const,
  enabled: true,
  status: 'connected',
  last_error: null,
  tool_count: 1,
  env_keys: [],
  header_keys: [],
  env: {},
  headers: {},
}

test('加载服务列表', async () => {
  const client = { listMcpServers: vi.fn().mockResolvedValue([server]) } as unknown as CoreClient
  const controller = createMcpController({ client })

  await controller.load()

  expect(controller.state.servers).toHaveLength(1)
  expect(controller.state.servers[0]?.status).toBe('connected')
})

test('启用/停用后刷新列表', async () => {
  const client = {
    setMcpEnabled: vi.fn().mockResolvedValue(server),
    listMcpServers: vi.fn().mockResolvedValue([{ ...server, enabled: false }]),
  } as unknown as CoreClient
  const controller = createMcpController({ client })

  await controller.toggle(server)

  expect(client.setMcpEnabled).toHaveBeenCalledWith('s1', false)
  expect(controller.state.servers[0]?.enabled).toBe(false)
})

test('编辑时调用 update 并退出编辑态', async () => {
  const client = {
    updateMcpServer: vi.fn().mockResolvedValue(server),
    listMcpServers: vi.fn().mockResolvedValue([server]),
  } as unknown as CoreClient
  const controller = createMcpController({ client })

  controller.beginEdit(server)
  expect(controller.state.editingId).toBe('s1')
  await controller.save({
    name: 'demo',
    transport: 'stdio',
    command: 'python',
    args: [],
    env: { PLAIN: '***' },
    url: null,
    headers: {},
    enabled: true,
  })

  expect(client.updateMcpServer).toHaveBeenCalledWith(
    's1',
    expect.objectContaining({ name: 'demo' }),
  )
  expect(controller.state.editingId).toBeNull()
})

test('启用时立即进入 connecting 状态', async () => {
  let release: (value: unknown) => void = () => {}
  const pending = new Promise((resolve) => {
    release = resolve
  })
  const disabled = { ...server, enabled: false, status: 'disabled', tool_count: 0 }
  const listMcpServers = vi.fn().mockResolvedValue([disabled])
  const client = {
    listMcpServers,
    setMcpEnabled: vi.fn().mockReturnValue(pending),
  } as unknown as CoreClient
  const controller = createMcpController({ client })
  await controller.load()
  listMcpServers.mockResolvedValue([{ ...server, enabled: true, status: 'connected' }])

  const running = controller.toggle(disabled)
  expect(disabled.status).toBe('connecting')

  release(server)
  await running
  expect(controller.state.servers[0]?.status).toBe('connected')
})
