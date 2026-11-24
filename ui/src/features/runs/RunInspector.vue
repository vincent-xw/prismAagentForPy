<script setup lang="ts">
import { ref } from 'vue'
import { RotateCw, X } from '@lucide/vue'
import { useAppContext } from '@/app/context'
import { Button } from '@/components/ui/button'
import type { RunProjection } from './projection'
import type { RunDto } from '@/lib/api/contracts'
import ToolCallCard from './ToolCallCard.vue'
const props = defineProps<{ projection: RunProjection | null }>()
const emit = defineEmits<{ close: []; refresh: [] }>()
const { client } = useAppContext()
interface PreviewState {
  exists: boolean
  diff: string | null
  truncated: boolean
}
const previews = ref<Record<string, PreviewState>>({})
const busyCallId = ref<string | null>(null)

async function loadPreview(callId: string): Promise<void> {
  if (props.projection === null || previews.value[callId] !== undefined) return
  try {
    const preview = await client.getApprovalPreview(props.projection.run.id, callId)
    previews.value = {
      ...previews.value,
      [callId]: { exists: preview.exists, diff: preview.diff, truncated: preview.truncated },
    }
  } catch {
    previews.value = {
      ...previews.value,
      [callId]: { exists: false, diff: null, truncated: false },
    }
  }
}

async function decide(callId: string, decision: 'approve' | 'reject'): Promise<void> {
  if (props.projection === null) return
  busyCallId.value = callId
  try {
    await client.decideApproval(props.projection.run.id, callId, decision, null)
    emit('refresh')
  } finally {
    busyCallId.value = null
  }
}
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
      ><div
        v-if="projection.pendingApprovals.length"
        role="status"
        class="mb-5 rounded-xl border border-primary/30 bg-primary/5 px-3 py-2 text-xs text-primary"
      >
        有 {{ projection.pendingApprovals.length }} 个写入等待你确认，处理后才继续执行。
      </div>
      <div class="mb-5 flex items-start justify-between gap-2">
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
      <div v-if="projection.pendingApprovals.length" class="mt-6 border-t pt-6">
        <h3 class="text-xs font-medium">
          待确认写入
          <span class="ml-1 text-muted-foreground">{{ projection.pendingApprovals.length }}</span>
        </h3>
        <div
          v-for="item in projection.pendingApprovals"
          :key="item.callId"
          class="mt-3 rounded-xl border border-primary/30 bg-primary/5 p-4"
        >
          <p class="break-all text-sm font-medium">
            {{ item.kind === 'generic' ? item.toolName : item.path }}
          </p>
          <p v-if="item.kind === 'file'" class="mt-1 text-xs text-muted-foreground">
            {{ item.mode }} · {{ item.bytes }} 字节
          </p>
          <p v-else class="mt-1 text-xs text-muted-foreground">外部工具调用</p>
          <details v-if="item.kind === 'generic'" class="mt-2 text-xs">
            <summary class="cursor-pointer text-muted-foreground">查看调用参数</summary>
            <pre class="mt-2 max-h-56 overflow-auto rounded-lg bg-secondary p-3">{{
              item.inputPreview ?? '无参数'
            }}</pre>
          </details>
          <details v-else class="mt-2 text-xs" @toggle="loadPreview(item.callId)">
            <summary class="cursor-pointer text-muted-foreground">查看改动预览</summary>
            <pre
              v-if="previews[item.callId]?.diff"
              class="mt-2 max-h-56 overflow-auto rounded-lg bg-secondary p-3"
              >{{ previews[item.callId]?.diff }}</pre>
            <p v-else class="mt-2 text-muted-foreground">
              {{ previews[item.callId]?.exists === false ? '将新建文件。' : '加载中或无差异。' }}
            </p>
          </details>
          <div class="mt-3 flex gap-2">
            <Button
              size="sm"
              :disabled="busyCallId === item.callId"
              @click="decide(item.callId, 'approve')"
              >{{ item.kind === 'generic' ? '允许执行' : '允许写入' }}</Button
            >
            <Button
              variant="outline"
              size="sm"
              :disabled="busyCallId === item.callId"
              @click="decide(item.callId, 'reject')"
              >拒绝</Button
            >
          </div>
        </div>
      </div>
      <h3 class="mt-6 border-t pt-6 text-xs font-medium">
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
