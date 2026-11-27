<script setup lang="ts">
import { Check, Copy } from '@lucide/vue'
import { ref } from 'vue'

const props = defineProps<{ sessionId: string }>()
const copied = ref(false)

async function copy(): Promise<void> {
  try {
    await navigator.clipboard.writeText(props.sessionId)
    copied.value = true
    window.setTimeout(() => (copied.value = false), 1500)
  } catch {
    copied.value = false
  }
}
</script>

<template>
  <span class="flex min-w-0 items-center gap-1 text-[10px] text-muted-foreground">
    <span class="truncate font-mono">{{ sessionId }}</span>
    <button
      type="button"
      class="inline-flex size-4 shrink-0 items-center justify-center rounded hover:bg-secondary hover:text-foreground"
      :aria-label="copied ? '已复制会话 ID' : '复制会话 ID'"
      :title="copied ? '已复制' : '复制会话 ID'"
      @click="copy"
    >
      <Check v-if="copied" class="size-3 text-primary" />
      <Copy v-else class="size-3" />
    </button>
  </span>
</template>
