<script setup lang="ts">
import { Wrench } from '@lucide/vue'
import type { ToolProjection, ToolStatus } from './projection'
defineProps<{ tool: ToolProjection }>()
const labels: Record<ToolStatus, string> = {
  requested: '已请求，等待结果',
  succeeded: '已完成',
  failed: '失败',
  expired: '已过期',
  cancelled: '已取消',
  incomplete: '详情未完整取得',
}
</script>
<template>
  <div class="mt-3 rounded-xl border p-4">
    <div class="flex items-start gap-2">
      <Wrench class="mt-1 size-3.5 shrink-0 text-muted-foreground" />
      <div class="min-w-0">
        <p class="break-all text-sm font-medium">{{ tool.name }}</p>
        <p
          class="mt-1 text-xs"
          :class="
            ['failed', 'expired'].includes(tool.status)
              ? 'text-destructive'
              : 'text-muted-foreground'
          "
        >
          {{ labels[tool.status] }}
        </p>
      </div>
    </div>
    <p class="mt-3 text-[11px] text-muted-foreground">
      {{ tool.mode === 'remote' ? '外部宿主执行' : '本地执行' }}
    </p>
    <details class="mt-3 text-xs">
      <summary class="cursor-pointer text-muted-foreground">调用参数</summary>
      <pre class="mt-2 max-h-56 overflow-auto rounded-lg bg-secondary p-3">{{
        JSON.stringify(tool.input, null, 2)
      }}</pre>
    </details>
    <details v-if="tool.messageId !== null && tool.status !== 'incomplete'" class="mt-3 text-xs">
      <summary class="cursor-pointer text-muted-foreground">返回结果</summary>
      <pre class="mt-2 max-h-64 overflow-auto rounded-lg bg-secondary p-3">{{
        JSON.stringify(tool.output, null, 2)
      }}</pre>
    </details>
    <p v-if="tool.errorMessage" class="mt-3 break-words text-xs text-destructive">
      {{ tool.errorCode }} · {{ tool.errorMessage }}
    </p>
  </div>
</template>
