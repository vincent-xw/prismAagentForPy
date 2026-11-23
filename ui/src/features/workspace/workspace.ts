import { reactive } from 'vue'

import type { CoreClient } from '@/lib/api/client'
import type { TreeEntryDto, WorkspaceDto } from '@/lib/api/contracts'

export interface WorkspaceFileState {
  path: string
  content: string
  truncated: boolean
}

export interface WorkspaceSearchHit {
  path: string
  snippet: string
}

export interface WorkspaceState {
  workspaces: WorkspaceDto[]
  active: WorkspaceDto | null
  entries: TreeEntryDto[]
  currentPath: string
  file: WorkspaceFileState | null
  searchResults: WorkspaceSearchHit[]
  query: string
  loading: boolean
  error: string | null
}

export interface WorkspaceController {
  state: WorkspaceState
  refreshActive: () => Promise<void>
  pollOnce: () => Promise<void>
  chooseDirectory: () => Promise<void>
  bindPath: (path: string) => Promise<void>
  activate: (id: string) => Promise<void>
  reindex: () => Promise<void>
  openDirectory: (path: string) => Promise<void>
  openFile: (path: string) => Promise<void>
  search: (query: string) => Promise<void>
}

// 控制器只保留界面需要的观察状态，不复制后端事实。
export function createWorkspaceController({
  client,
}: {
  client: CoreClient
}): WorkspaceController {
  const state = reactive<WorkspaceState>({
    workspaces: [],
    active: null,
    entries: [],
    currentPath: '.',
    file: null,
    searchResults: [],
    query: '',
    loading: false,
    error: null,
  })

  async function run<T>(task: () => Promise<T>): Promise<T | null> {
    state.loading = true
    state.error = null
    try {
      return await task()
    } catch (error) {
      state.error = error instanceof Error ? error.message : '工作区操作失败。'
      return null
    } finally {
      state.loading = false
    }
  }

  async function refreshActive(): Promise<void> {
    await run(async () => {
      const list = await client.listWorkspaces()
      state.workspaces = list.items
      const active = list.items.find((item) => item.id === list.active_id) ?? null
      state.active = active
      if (active !== null) state.active = await client.getWorkspace(active.id)
    })
  }

  async function pollOnce(): Promise<void> {
    if (state.active === null) return
    await run(async () => {
      if (state.active !== null) state.active = await client.getWorkspace(state.active.id)
    })
  }

  async function openDirectory(path: string): Promise<void> {
    if (state.active === null) return
    await run(async () => {
      if (state.active === null) return
      const response = await client.getTree(state.active.id, path)
      state.entries = response.items
      state.currentPath = path
    })
  }

  async function chooseDirectory(): Promise<void> {
    await run(async () => {
      const picked = await client.pickWorkspace()
      await client.createWorkspace(picked.path, null)
      await refreshActive()
      await openDirectory('.')
    })
  }

  async function bindPath(path: string): Promise<void> {
    await run(async () => {
      await client.createWorkspace(path, null)
      await refreshActive()
      await openDirectory('.')
    })
  }

  async function activate(id: string): Promise<void> {
    await run(async () => {
      state.active = await client.activateWorkspace(id)
      state.file = null
      state.entries = []
      state.searchResults = []
      state.query = ''
      state.currentPath = '.'
    })
    await openDirectory('.')
    await refreshActive()
  }

  async function reindex(): Promise<void> {
    if (state.active === null) return
    await run(async () => {
      if (state.active !== null) state.active = await client.reindexWorkspace(state.active.id)
    })
  }

  async function openFile(path: string): Promise<void> {
    if (state.active === null) return
    await run(async () => {
      if (state.active === null) return
      const file = await client.getFile(state.active.id, path)
      state.file = { path: file.path, content: file.content, truncated: file.truncated }
    })
  }

  async function search(query: string): Promise<void> {
    state.query = query
    if (state.active === null || query.trim() === '') {
      state.searchResults = []
      return
    }
    await run(async () => {
      if (state.active === null) return
      const response = await client.searchWorkspace(state.active.id, query.trim())
      state.searchResults = response.items
    })
  }

  return {
    state,
    refreshActive,
    pollOnce,
    chooseDirectory,
    bindPath,
    activate,
    reindex,
    openDirectory,
    openFile,
    search,
  }
}
