<script setup lang="ts">
import { computed, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { useAppContext } from '@/app/context'
import { isTerminal } from '@/lib/api/contracts'
import RunInspector from './RunInspector.vue'

const route = useRoute()
const router = useRouter()
const { conversation } = useAppContext()
const state = computed(() => conversation.value!.state)
const sessionId = computed(() => String(route.params.sessionId ?? ''))
const projection = computed(() =>
  state.value.selectedRunId ? (state.value.runs[state.value.selectedRunId] ?? null) : null,
)

function pickRunId(): string | null {
  const requested = typeof route.query.run === 'string' ? route.query.run : null
  if (requested !== null) return requested
  const sessionRuns = Object.values(state.value.runs).filter(
    (item) => item.run.session_id === sessionId.value,
  )
  const active = sessionRuns.find((item) => !isTerminal(item.run))
  if (active !== undefined) return active.run.id
  return sessionRuns.at(-1)?.run.id ?? null
}

async function load(): Promise<void> {
  if (sessionId.value === '') return
  const runId = pickRunId()
  if (runId === null || runId === state.value.selectedRunId) return
  if (!state.value.runs[runId]) {
    // 会话已打开但该 Run 未在内存中：先加载会话，再重新挑选。
    await conversation.value!.openSession(sessionId.value)
  }
  if (state.value.runs[runId]) await conversation.value!.selectRun(runId)
}

async function refresh(): Promise<void> {
  if (projection.value !== null) await conversation.value!.selectRun(projection.value.run.id)
}

watch([() => route.params.sessionId, () => route.query.run], () => void load(), { immediate: true })
</script>

<template>
  <div class="min-h-0 flex-1 overflow-y-auto">
    <div class="mx-auto w-full max-w-4xl px-5 py-6 sm:px-9 sm:py-10">
      <RunInspector
        v-if="projection !== null"
        :projection="projection"
        @close="router.push(`/sessions/${sessionId}`)"
        @refresh="refresh"
      />
      <div v-else class="rounded-xl border bg-card p-6 text-sm text-muted-foreground">
        还没有可展示的执行记录。先在会话里发送消息，或从消息下方点击「查看执行」。
      </div>
    </div>
  </div>
</template>
