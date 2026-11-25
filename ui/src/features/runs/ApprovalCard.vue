<script setup lang="ts">
import { ref } from 'vue'

import { useAppContext } from '@/app/context'
import { Button } from '@/components/ui/button'
import type { PendingApproval } from './projection'

const props = defineProps<{ runId: string; item: PendingApproval }>()
const emit = defineEmits<{ decided: [] }>()
const { client } = useAppContext()

interface PreviewState {
  exists: boolean
  diff: string | null
  truncated: boolean
}
const preview = ref<PreviewState | null>(null)
const busy = ref(false)

async function loadPreview(): Promise<void> {
  if (preview.value !== null) return
  try {
    const result = await client.getApprovalPreview(props.runId, props.item.callId)
    preview.value = {
      exists: result.exists,
      diff: result.diff,
      truncated: result.truncated,
    }
  } catch {
    preview.value = { exists: false, diff: null, truncated: false }
  }
}

async function decide(decision: 'approve' | 'reject'): Promise<void> {
  busy.value = true
  try {
    await client.decideApproval(props.runId, props.item.callId, decision, null)
    emit('decided')
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="rounded-xl border border-primary/30 bg-card p-4">
    <p class="break-all text-sm font-medium">
      {{ item.kind === 'generic' ? item.toolName : item.path }}
    </p>
    <p v-if="item.kind === 'file'" class="mt-1 text-xs text-muted-foreground">
      {{ item.mode }} · {{ item.bytes }} 字节
    </p>
    <p v-else class="mt-1 text-xs text-muted-foreground">外部工具调用</p>
    <details v-if="item.kind === 'generic'" class="mt-2 text-xs">
      <summary class="cursor-pointer text-muted-foreground">查看调用参数</summary>
      <pre class="mt-2 max-h-40 overflow-auto rounded-lg bg-secondary p-3">{{
        item.inputPreview ?? '无参数'
      }}</pre>
    </details>
    <details v-else class="mt-2 text-xs" @toggle="loadPreview">
      <summary class="cursor-pointer text-muted-foreground">查看改动预览</summary>
      <pre v-if="preview?.diff" class="mt-2 max-h-40 overflow-auto rounded-lg bg-secondary p-3">{{
        preview?.diff
      }}</pre>
      <p v-else class="mt-2 text-muted-foreground">
        {{ preview?.exists === false ? '将新建文件。' : '加载中或无差异。' }}
      </p>
    </details>
    <div class="mt-3 flex gap-2">
      <Button size="sm" :disabled="busy" @click="decide('approve')">
        {{ item.kind === 'generic' ? '允许执行' : '允许写入' }}
      </Button>
      <Button variant="outline" size="sm" :disabled="busy" @click="decide('reject')">拒绝</Button>
    </div>
  </div>
</template>
