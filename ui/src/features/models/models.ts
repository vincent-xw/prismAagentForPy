import { reactive } from 'vue'

import type { CoreClient } from '@/lib/api/client'
import type { ModelProfileDto, ModelProfilePayload } from '@/lib/api/contracts'

export interface ModelsState {
  profiles: ModelProfileDto[]
  editingId: string | null
  loading: boolean
  error: string | null
  notice: string | null
}

export interface ModelsController {
  state: ModelsState
  load: () => Promise<void>
  save: (payload: ModelProfilePayload) => Promise<void>
  beginEdit: (profile: ModelProfileDto) => void
  cancelEdit: () => void
  activate: (profile: ModelProfileDto) => Promise<void>
  remove: (profile: ModelProfileDto) => Promise<void>
  probe: (profile: ModelProfileDto) => Promise<void>
}

export function createModelsController({ client }: { client: CoreClient }): ModelsController {
  const state = reactive<ModelsState>({
    profiles: [],
    editingId: null,
    loading: false,
    error: null,
    notice: null,
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
      state.profiles = await client.listModelProfiles()
    })
  }

  async function save(payload: ModelProfilePayload): Promise<void> {
    await guard(async () => {
      if (state.editingId === null) {
        await client.createModelProfile(payload)
      } else {
        await client.updateModelProfile(state.editingId, payload)
        state.editingId = null
      }
      state.profiles = await client.listModelProfiles()
    })
  }

  function beginEdit(profile: ModelProfileDto): void {
    state.editingId = profile.id
  }

  function cancelEdit(): void {
    state.editingId = null
  }

  async function activate(profile: ModelProfileDto): Promise<void> {
    await guard(async () => {
      await client.activateModelProfile(profile.id)
      state.profiles = await client.listModelProfiles()
      state.notice = `已切换到 ${profile.name}，下一次请求生效`
    })
  }

  async function remove(profile: ModelProfileDto): Promise<void> {
    await guard(async () => {
      await client.deleteModelProfile(profile.id)
      state.profiles = await client.listModelProfiles()
    })
  }

  async function probe(profile: ModelProfileDto): Promise<void> {
    await guard(async () => {
      const result = await client.probeModelProfile(profile.id)
      state.notice = result.ok
        ? `${profile.name} 连接正常（${result.latency_ms ?? 0} ms）`
        : `${profile.name} 连接失败：${result.error ?? '未知错误'}`
    })
  }

  return { state, load, save, beginEdit, cancelEdit, activate, remove, probe }
}
