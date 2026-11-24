import { reactive } from 'vue'

import type { CoreClient } from '@/lib/api/client'
import type { McpServerDto, McpServerPayload, McpToolDto } from '@/lib/api/contracts'

export interface McpState {
  servers: McpServerDto[]
  tools: McpToolDto[]
  selectedId: string | null
  loading: boolean
  error: string | null
}

export interface McpController {
  state: McpState
  load: () => Promise<void>
  create: (payload: McpServerPayload) => Promise<void>
  toggle: (server: McpServerDto) => Promise<void>
  reconnect: (server: McpServerDto) => Promise<void>
  remove: (server: McpServerDto) => Promise<void>
  openTools: (server: McpServerDto) => Promise<void>
}

export function createMcpController({ client }: { client: CoreClient }): McpController {
  const state = reactive<McpState>({
    servers: [],
    tools: [],
    selectedId: null,
    loading: false,
    error: null,
  })

  async function guard(action: () => Promise<void>): Promise<void> {
    state.loading = true
    state.error = null
    try {
      await action()
    } catch (error) {
      state.error = error instanceof Error ? error.message : '操作失败'
    } finally {
      state.loading = false
    }
  }

  async function load(): Promise<void> {
    await guard(async () => {
      state.servers = await client.listMcpServers()
    })
  }

  async function create(payload: McpServerPayload): Promise<void> {
    await guard(async () => {
      await client.createMcpServer(payload)
      state.servers = await client.listMcpServers()
    })
  }

  async function toggle(server: McpServerDto): Promise<void> {
    await guard(async () => {
      await client.setMcpEnabled(server.id, !server.enabled)
      state.servers = await client.listMcpServers()
    })
  }

  async function reconnect(server: McpServerDto): Promise<void> {
    await guard(async () => {
      await client.reconnectMcp(server.id)
      state.servers = await client.listMcpServers()
    })
  }

  async function remove(server: McpServerDto): Promise<void> {
    await guard(async () => {
      await client.deleteMcpServer(server.id)
      state.servers = await client.listMcpServers()
      if (state.selectedId === server.id) state.selectedId = null
    })
  }

  async function openTools(server: McpServerDto): Promise<void> {
    await guard(async () => {
      const result = await client.getMcpTools(server.id)
      state.selectedId = server.id
      state.tools = result.tools
    })
  }

  return { state, load, create, toggle, reconnect, remove, openTools }
}
