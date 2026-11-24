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
