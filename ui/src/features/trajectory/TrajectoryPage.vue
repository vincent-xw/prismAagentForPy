<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

import { useAppContext } from '@/app/context'
import type { TrajectoryDto, TrajectoryStepDto, TrajectoryToolDto } from '@/lib/api/contracts'

const { client } = useAppContext()
const route = useRoute()
const data = ref<TrajectoryDto | null>(null)
const error = ref<string | null>(null)
const selected = ref<{ title: string; body: string } | null>(null)
let timer: ReturnType<typeof setInterval> | null = null

const sessionId = computed(() => String(route.params.sessionId ?? ''))
const hasActive = computed(
  () =>
    data.value?.turns.some(
      (turn) => !['succeeded', 'failed', 'cancelled'].includes(turn.run.status),
    ) ?? false,
)

async function load(): Promise<void> {
  if (client === undefined || sessionId.value === '') return
  try {
    data.value = await client.getTrajectory(sessionId.value)
    error.value = null
    if (!hasActive.value) stopPolling()
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : '轨迹加载失败'
  }
}

function startPolling(): void {
  if (timer !== null) return
  timer = setInterval(() => void load(), 2000)
}

function stopPolling(): void {
  if (timer !== null) {
    clearInterval(timer)
    timer = null
  }
}

function inspectStep(step: TrajectoryStepDto): void {
  selected.value = {
    title: `Step ${step.index + 1}`,
    body: JSON.stringify(
      {
        model: step.model,
        usage: step.usage,
        duration_ms: step.duration_ms,
        finish_reason: step.finish_reason,
      },
      null,
      2,
    ),
  }
}

function inspectTool(tool: TrajectoryToolDto): void {
  selected.value = {
    title: tool.tool_name,
    body: JSON.stringify({ input: tool.input, output: tool.output, status: tool.status }, null, 2),
  }
}

function formatUsage(step: TrajectoryStepDto): string {
  if (step.usage === null) return '未记录 usage'
  return `${step.usage.total_tokens} tokens`
}

onMounted(async () => {
  await load()
  if (hasActive.value) startPolling()
})
onUnmounted(stopPolling)
watch(sessionId, async () => {
  stopPolling()
  selected.value = null
  await load()
  if (hasActive.value) startPolling()
})
</script>

<template>
  <section class="flex h-full min-h-0 flex-1 flex-col overflow-hidden" aria-label="轨迹">
    <header class="flex items-center justify-between border-b px-6 py-4">
      <h1 class="text-sm font-semibold">轨迹</h1>
      <p class="text-xs text-muted-foreground">
        {{ hasActive ? '运行中，每 2 秒刷新' : '已停止刷新' }}
      </p>
    </header>
    <p v-if="error" class="px-6 py-3 text-xs text-destructive">{{ error }}</p>
    <div class="flex min-h-0 flex-1">
      <div class="min-w-0 flex-1 overflow-y-auto px-6 py-4">
        <div v-for="turn in data?.turns ?? []" :key="turn.run.id" class="mb-6">
          <div class="mb-2 flex items-baseline gap-2 text-xs">
            <span class="font-medium">{{ turn.run.input_text || '（无输入）' }}</span>
            <span class="text-muted-foreground">{{ turn.run.status }}</span>
          </div>
          <button
            v-for="step in turn.steps"
            :key="`${turn.run.id}-${step.index}`"
            type="button"
            class="mb-2 w-full rounded-lg border p-3 text-left text-xs hover:bg-secondary"
            @click="inspectStep(step)"
          >
            <div class="flex items-center justify-between">
              <span class="font-medium"
                >Step {{ step.index + 1 }} · {{ step.model }}
                <span v-if="step.legacy" class="ml-1 text-muted-foreground">legacy</span></span
              >
              <span class="text-muted-foreground"
                >{{ formatUsage(step) }} · {{ step.duration_ms ?? '—' }} ms</span
              >
            </div>
            <button
              v-for="tool in step.tools"
              :key="tool.call_id"
              type="button"
              class="mt-2 block w-full rounded-md bg-secondary/60 px-2 py-1 text-left hover:bg-secondary"
              @click.stop="inspectTool(tool)"
            >
              ↳ {{ tool.tool_name }} · {{ tool.status }} · {{ tool.duration_ms ?? '—' }} ms
            </button>
          </button>
          <p
            v-for="item in turn.compactions"
            :key="item.id"
            class="rounded-md border border-dashed px-3 py-2 text-[11px] text-muted-foreground"
          >
            上下文已压缩：{{ item.tokens_before }} → {{ item.tokens_after }} tokens
          </p>
        </div>
        <p v-if="!data?.turns.length" class="text-sm text-muted-foreground">还没有执行记录。</p>
      </div>
      <aside
        v-if="selected"
        class="w-80 shrink-0 overflow-y-auto border-l bg-card p-4 text-xs"
        aria-label="记录详情"
      >
        <div class="mb-2 flex items-center justify-between">
          <h2 class="font-medium">{{ selected.title }}</h2>
          <button type="button" class="text-muted-foreground" @click="selected = null">关闭</button>
        </div>
        <pre class="whitespace-pre-wrap break-all">{{ selected.body }}</pre>
      </aside>
    </div>
  </section>
</template>
