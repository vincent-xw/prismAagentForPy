<script setup lang="ts">
import { RotateCw, X } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import type { RunProjection } from './projection'
import type { RunDto } from '@/lib/api/contracts'
import ToolCallCard from './ToolCallCard.vue'
defineProps<{ projection: RunProjection | null }>()
const emit = defineEmits<{ close: []; refresh: [] }>()
export type RunLabels = Record<RunDto['status'], string>
const labels: RunLabels = {
  queued: '排队中',
  running: '运行中',
  waiting_for_tool: '等待外部工具结果',
  waiting_for_approval: '等待确认写入',
  succeeded: '已完成',
  failed: '执行失败',
  cancelled: '已停止',
}
function date(value: string | null) {
  return value === null ? '尚未发生' : new Date(value).toLocaleString('zh-CN', { hour12: false })
}
</script>
<template>
  <section class="h-full overflow-y-auto bg-card p-5" aria-label="当前执行详情">
    <div class="mb-7 flex items-center justify-between">
      <h2 class="text-sm font-semibold">执行详情</h2>
      <Button variant="ghost" size="icon-xs" aria-label="收起执行详情" @click="emit('close')"
        ><X class="size-4"
      /></Button>
    </div>
    <template v-if="projection"
      ><div class="mb-5 flex items-start justify-between gap-2">
        <div>
          <p class="text-[10px] tracking-widest text-muted-foreground">RUN STATUS</p>
          <p
            class="mt-2 text-sm font-medium"
            :class="projection.run.status === 'failed' ? 'text-destructive' : 'text-primary'"
          >
            {{ labels[projection.run.status] }}
          </p>
          <p
            v-if="
              projection.run.cancel_requested_at &&
              !['succeeded', 'failed', 'cancelled'].includes(projection.run.status)
            "
            class="mt-2 text-xs text-muted-foreground"
          >
            等待停止确认
          </p>
        </div>
        <Button
          variant="ghost"
          size="icon-xs"
          aria-label="重新读取执行详情"
          @click="emit('refresh')"
          ><RotateCw class="size-3.5"
        /></Button>
      </div>
      <dl class="space-y-4 border-t py-5 text-xs">
        <div>
          <dt class="text-muted-foreground">模型</dt>
          <dd class="mt-1 break-all">{{ projection.run.model }}</dd>
        </div>
        <div>
          <dt class="text-muted-foreground">执行步数</dt>
          <dd class="mt-1 font-mono">{{ projection.run.step_count }}</dd>
        </div>
        <div>
          <dt class="text-muted-foreground">开始时间</dt>
          <dd class="mt-1">{{ date(projection.run.started_at) }}</dd>
        </div>
        <div>
          <dt class="text-muted-foreground">结束时间</dt>
          <dd class="mt-1">{{ date(projection.run.finished_at) }}</dd>
        </div>
        <div>
          <dt class="text-muted-foreground">运行 ID</dt>
          <dd class="mt-1 break-all font-mono text-[11px]">{{ projection.run.id }}</dd>
        </div>
      </dl>
      <div
        v-if="projection.run.error_message"
        role="alert"
        class="mb-5 rounded-lg border border-destructive/25 bg-destructive/5 p-3 text-xs leading-6 text-destructive"
      >
        <p class="font-mono">{{ projection.run.error_code }}</p>
        {{ projection.run.error_message }}
      </div>
      <h3 class="border-t pt-5 text-xs font-medium">
        工具调用 <span class="ml-1 text-muted-foreground">{{ projection.tools.length }}</span>
      </h3>
      <p v-if="!projection.tools.length" class="mt-3 text-xs leading-6 text-muted-foreground">
        尚无已读取的工具调用。可重新读取以同步持久事件。
      </p>
      <ToolCallCard v-for="tool in projection.tools" :key="tool.callId" :tool="tool"
    /></template>
    <p v-else class="text-sm text-muted-foreground">选择一条消息的执行记录查看详情。</p>
  </section>
</template>
