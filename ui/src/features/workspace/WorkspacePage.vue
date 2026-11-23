<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'

import { useAppContext } from '@/app/context'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { createWorkspaceController } from './workspace'

const { client } = useAppContext()
const controller = createWorkspaceController({ client })
const state = controller.state
const manualPath = ref('')
const timer = ref<number | null>(null)

const statusLabel = computed(() => {
  const active = state.active
  if (active === null) return '未绑定'
  switch (active.index_status) {
    case 'indexing':
      return '索引中…'
    case 'ready':
      return `就绪 · ${active.file_count} 个文件`
    case 'failed':
      return `索引失败：${active.index_error ?? '未知原因'}`
    default:
      return '未索引'
  }
})

function stopPolling(): void {
  if (timer.value !== null) {
    window.clearInterval(timer.value)
    timer.value = null
  }
}

function syncPolling(): void {
  stopPolling()
  if (state.active?.index_status === 'indexing') {
    timer.value = window.setInterval(() => void controller.pollOnce(), 1500)
  }
}

async function refresh(): Promise<void> {
  await controller.refreshActive()
  syncPolling()
  if (state.active !== null && state.entries.length === 0) await controller.openDirectory('.')
}

async function choose(): Promise<void> {
  await controller.chooseDirectory()
  syncPolling()
}

async function bind(): Promise<void> {
  if (manualPath.value.trim() === '') return
  await controller.bindPath(manualPath.value.trim())
  manualPath.value = ''
  syncPolling()
}

async function reindex(): Promise<void> {
  await controller.reindex()
  syncPolling()
}

onMounted(() => void refresh())
onUnmounted(stopPolling)
</script>

<template>
  <div class="flex min-h-0 flex-1 flex-col overflow-auto p-4 sm:p-6">
    <section class="rounded-xl border p-4">
      <div class="flex flex-wrap items-center gap-3">
        <div class="min-w-0 flex-1">
          <p class="text-xs text-muted-foreground">当前工作区</p>
          <p class="truncate text-sm font-medium">
            {{ state.active?.root_path ?? '尚未选择目录' }}
          </p>
        </div>
        <span class="rounded border px-2 py-0.5 text-[11px] text-muted-foreground">{{
          statusLabel
        }}</span>
        <Button size="sm" :disabled="state.loading" @click="choose">选择目录</Button>
        <Button
          variant="outline"
          size="sm"
          :disabled="state.loading || state.active === null"
          @click="reindex"
          >重建索引</Button
        >
      </div>
      <div class="mt-3 flex flex-wrap gap-2">
        <Input
          v-model="manualPath"
          class="max-w-md"
          placeholder="或直接输入绝对路径，例如 /Users/me/project"
          @keyup.enter="bind"
        />
        <Button variant="outline" size="sm" :disabled="state.loading" @click="bind">绑定</Button>
      </div>
      <p v-if="state.error !== null" class="mt-2 text-xs text-destructive">{{ state.error }}</p>
    </section>

    <div class="mt-4 grid min-h-0 flex-1 gap-4 lg:grid-cols-[minmax(220px,320px)_1fr]">
      <section class="min-h-0 overflow-auto rounded-xl border p-3">
        <div class="mb-2 flex items-center justify-between text-xs text-muted-foreground">
          <span class="truncate">/{{ state.currentPath === '.' ? '' : state.currentPath }}</span>
          <Button
            v-if="state.currentPath !== '.'"
            variant="ghost"
            size="xs"
            @click="controller.openDirectory('.')"
            >根目录</Button
          >
        </div>
        <ul class="space-y-0.5">
          <li v-for="entry in state.entries" :key="entry.name">
            <button
              type="button"
              class="flex w-full items-center gap-2 rounded px-2 py-1 text-left text-[13px] hover:bg-secondary"
              @click="
                entry.type === 'dir'
                  ? controller.openDirectory(
                      state.currentPath === '.' ? entry.name : `${state.currentPath}/${entry.name}`,
                    )
                  : controller.openFile(
                      state.currentPath === '.' ? entry.name : `${state.currentPath}/${entry.name}`,
                    )
              "
            >
              <span class="text-muted-foreground">{{ entry.type === 'dir' ? '▸' : '·' }}</span>
              <span class="truncate">{{ entry.name }}</span>
            </button>
          </li>
        </ul>
        <p v-if="state.entries.length === 0" class="px-2 py-4 text-xs text-muted-foreground">
          目录为空或未绑定工作区。
        </p>
      </section>

      <section class="flex min-h-0 flex-col gap-3">
        <div class="flex gap-2">
          <Input
            :model-value="state.query"
            placeholder="检索工作区内容…"
            @update:model-value="(value) => controller.search(String(value))"
          />
        </div>
        <div
          v-if="state.searchResults.length > 0"
          class="min-h-0 flex-1 overflow-auto rounded-xl border p-3"
        >
          <ul class="space-y-2">
            <li v-for="hit in state.searchResults" :key="hit.path">
              <button
                type="button"
                class="w-full rounded px-2 py-1.5 text-left hover:bg-secondary"
                @click="controller.openFile(hit.path)"
              >
                <p class="text-[13px] font-medium">{{ hit.path }}</p>
                <p class="truncate text-xs text-muted-foreground">{{ hit.snippet }}</p>
              </button>
            </li>
          </ul>
        </div>
        <div
          v-else
          class="min-h-0 flex-1 overflow-auto rounded-xl border p-3 font-mono text-[12px] whitespace-pre-wrap"
        >
          <template v-if="state.file !== null">
            <p class="mb-2 font-sans text-xs text-muted-foreground">
              {{ state.file.path }}<span v-if="state.file.truncated"> · 已截断</span>
            </p>
            {{ state.file.content }}
          </template>
          <p v-else class="font-sans text-xs text-muted-foreground">选择左侧文件查看内容。</p>
        </div>
      </section>
    </div>
  </div>
</template>
