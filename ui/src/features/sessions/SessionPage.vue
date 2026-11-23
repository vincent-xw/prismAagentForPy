<script setup lang="ts">
import { computed, ref } from 'vue'
import { useAppContext } from '@/app/context'
import { isTerminal } from '@/lib/api/contracts'
import { Button } from '@/components/ui/button'
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from '@/components/ui/sheet'
import MessageList from './MessageList.vue'
import MessageComposer from './MessageComposer.vue'
import RunInspector from '@/features/runs/RunInspector.vue'
const { conversation, connection } = useAppContext()
const inspectorOpen = ref(false)
const isNarrow = ref(window.matchMedia('(max-width: 767px)').matches)
const media = window.matchMedia('(max-width: 767px)')
import { onMounted, onUnmounted } from 'vue'
const onMedia = () => {
  isNarrow.value = media.matches
}
onMounted(() => media.addEventListener('change', onMedia))
onUnmounted(() => media.removeEventListener('change', onMedia))
const state = computed(() => conversation.value!.state)
const projection = computed(() =>
  state.value.selectedRunId ? (state.value.runs[state.value.selectedRunId] ?? null) : null,
)
const active = computed(
  () =>
    Object.values(state.value.runs).find(
      (item) => item.run.session_id === state.value.selectedSessionId && !isTerminal(item.run),
    ) ?? null,
)
const draft = computed({
  get: () => state.value.drafts[state.value.selectedSessionId ?? 'new'] ?? '',
  set: (value: string) => {
    state.value.drafts[state.value.selectedSessionId ?? 'new'] = value
  },
})
const messages = computed(() =>
  state.value.selectedSessionId ? (state.value.messages[state.value.selectedSessionId] ?? []) : [],
)
async function inspect(runId: string) {
  inspectorOpen.value = true
  await conversation.value!.selectRun(runId)
}
const labels = {
  queued: '排队中',
  running: '正在生成',
  waiting_for_tool: '等待外部工具结果',
  waiting_for_approval: '等待确认写入',
  succeeded: '已完成',
  failed: '执行失败',
  cancelled: '已停止',
}
</script>
<template>
  <div class="relative flex min-h-0 min-w-0 flex-1">
    <section
      class="min-h-0 min-w-0 flex-1 flex-col"
      :class="inspectorOpen && !isNarrow ? 'hidden xl:flex' : 'flex'"
      aria-label="会话工作台"
    >
      <div
        v-if="connection.state.status !== 'ready'"
        class="flex flex-wrap items-center justify-center gap-2 border-b bg-accent/50 px-4 py-2 text-xs"
      >
        <span class="text-muted-foreground">{{
          connection.state.status === 'unauthorized' ? '访问凭据已失效' : '连接服务后开始对话'
        }}</span><RouterLink
          to="/settings"
          class="font-medium text-primary underline-offset-4 hover:underline"
          >连接服务</RouterLink
        >
      </div>
      <div
        v-if="state.error"
        role="alert"
        class="flex flex-wrap items-center justify-between gap-2 border-b bg-destructive/5 px-5 py-3 text-xs text-destructive"
      >
        <span class="min-w-0 break-words">{{ state.error }}</span><Button
          v-if="state.selectedSessionId"
          variant="ghost"
          size="xs"
          @click="conversation!.openSession(state.selectedSessionId)"
          >重新读取会话</Button
        >
      </div>
      <MessageList
        :messages="messages"
        :projection="active ?? projection"
        :loading="state.loading"
        @inspect="inspect"
      />
      <div
        v-if="active || projection"
        role="status"
        class="mx-auto flex w-full max-w-3xl items-center gap-2 px-7 text-xs text-muted-foreground"
      >
        <span class="size-1.5 animate-pulse rounded-full bg-primary" />{{
          active
            ? active.run.cancel_requested_at
              ? '等待停止确认'
              : labels[active.run.status]
            : labels[projection!.run.status]
        }}<span v-if="state.connection === 'reconnecting'"> · 正在重新连接</span
        ><span v-else-if="state.connection === 'error'"> · 事件连接中断</span
        ><Button
          variant="link"
          size="xs"
          class="ml-auto"
          @click="inspect((active ?? projection)!.run.id)"
          >执行详情</Button
        >
      </div>
      <MessageComposer
        v-model="draft"
        :disabled="connection.state.status !== 'ready' || !state.selectedSessionId || state.loading"
        :busy="active !== null"
        :sending="!!state.sending[state.selectedSessionId ?? '']"
        :stopping="
          active !== null &&
          (!!state.cancelling[active.run.id] || active.run.cancel_requested_at !== null)
        "
        @send="conversation!.send(draft)"
        @stop="active && conversation!.cancel(active.run.id)"
      />
    </section>
    <aside v-if="inspectorOpen && !isNarrow" class="w-full shrink-0 xl:w-[310px] xl:border-l">
      <RunInspector
        :projection="projection"
        @close="inspectorOpen = false"
        @refresh="projection && conversation!.selectRun(projection.run.id)"
      />
    </aside>
    <Sheet :open="inspectorOpen && isNarrow" @update:open="inspectorOpen = $event"
      ><SheetContent class="w-[min(90vw,360px)] gap-0 p-0"
        ><SheetHeader class="sr-only"
          ><SheetTitle>执行详情</SheetTitle
          ><SheetDescription>当前运行与工具调用的持久记录</SheetDescription></SheetHeader
        ><RunInspector
          :projection="projection"
          @close="inspectorOpen = false"
          @refresh="projection && conversation!.selectRun(projection.run.id)" /></SheetContent
    ></Sheet>
  </div>
</template>
