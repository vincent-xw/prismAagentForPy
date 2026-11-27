<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'

import { Button } from '@/components/ui/button'
import type { CoreClient } from '@/lib/api/client'
import type { ContextUsageDto } from '@/lib/api/contracts'
import { usageLabel, usageTone } from './contextUsage'

const props = defineProps<{ client: CoreClient; sessionId: string }>()
const usage = ref<ContextUsageDto | null>(null)
const compacting = ref(false)
const timer = ref<number | null>(null)
const tone = computed(() => usageTone(usage.value))
const percent = computed(() => Math.min(100, Math.max(0, usage.value?.percent ?? 0)))

async function refresh(): Promise<void> {
  try {
    usage.value = await props.client.getContextUsage(props.sessionId)
  } catch {
    usage.value = null
  }
}

async function compact(): Promise<void> {
  if (usage.value === null) return
  if (!window.confirm('压缩上下文会生成摘要并释放窗口，确认继续？')) return
  compacting.value = true
  try {
    await props.client.compactSession(props.sessionId)
    await refresh()
  } finally {
    compacting.value = false
  }
}

watch(
  () => props.sessionId,
  () => void refresh(),
)
onMounted(() => {
  void refresh()
  timer.value = window.setInterval(() => void refresh(), 15_000)
})
onUnmounted(() => {
  if (timer.value !== null) window.clearInterval(timer.value)
})
</script>

<template>
  <div class="flex items-center gap-2 text-[11px] text-muted-foreground" aria-live="polite">
    <span class="whitespace-nowrap">{{ usageLabel(usage) }}</span>
    <span class="relative h-1.5 w-24 overflow-hidden rounded-full bg-muted">
      <span
        class="absolute inset-y-0 left-0 rounded-full"
        :class="
          tone === 'danger' ? 'bg-destructive' : tone === 'warn' ? 'bg-amber-500' : 'bg-primary'
        "
        :style="{ width: `${percent}%` }"
      />
    </span>
    <Button
      v-if="usage?.needs_compaction && usage.compactable"
      variant="outline"
      size="xs"
      :disabled="compacting"
      @click="compact"
      >压缩上下文</Button
    >
  </div>
</template>
