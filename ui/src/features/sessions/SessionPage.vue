<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useAppContext } from '@/app/context'
import { isTerminal } from '@/lib/api/contracts'
import { Button } from '@/components/ui/button'
import MessageList from './MessageList.vue'
import MessageComposer from './MessageComposer.vue'
import ApprovalCard from '@/features/runs/ApprovalCard.vue'
const { conversation, connection, client } = useAppContext()
const router = useRouter()
const state = computed(() => conversation.value!.state)
const workspaceLabel = ref<string | null>(null)
const composer = ref<{ clearSkill: () => void } | null>(null)

// 只用于展示当前会话绑定的工作区，加载失败不打断主流程。
async function loadWorkspaceLabel(): Promise<void> {
  const sessionId = state.value.selectedSessionId
  if (!sessionId || client === undefined) {
    workspaceLabel.value = null
    return
  }
  const session = state.value.sessions.find((item) => item.id === sessionId)
  if (!session?.workspace_id) {
    workspaceLabel.value = null
    return
  }
  try {
    const list = await client.listWorkspaces()
    const workspace = list.items.find((item) => item.id === session.workspace_id)
    workspaceLabel.value =
      workspace === undefined
        ? null
        : (workspace.label ??
          workspace.root_path.split('/').filter(Boolean).pop() ??
          workspace.root_path)
  } catch {
    workspaceLabel.value = null
  }
}
watch(
  () => state.value.selectedSessionId,
  () => void loadWorkspaceLabel(),
  { immediate: true },
)
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
const pendingApprovals = computed(() => (active.value ?? projection.value)?.pendingApprovals ?? [])
const pendingRunId = computed(() => (active.value ?? projection.value)?.run.id ?? null)

async function refreshAfterDecision(): Promise<void> {
  if (state.value.selectedSessionId === null) return
  await conversation.value!.openSession(state.value.selectedSessionId)
}

const messages = computed(() =>
  state.value.selectedSessionId ? (state.value.messages[state.value.selectedSessionId] ?? []) : [],
)
async function handleSend(payload: { text: string; skillName: string | null }): Promise<void> {
  const sent = await conversation.value!.send(payload.text, payload.skillName)
  if (sent) composer.value?.clearSkill()
}

async function inspect(runId: string) {
  const sessionId = state.value.selectedSessionId
  if (sessionId === null) return
  await router.push({ path: `/sessions/${sessionId}/execution`, query: { run: runId } })
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
    <section class="flex min-h-0 min-w-0 flex-1 flex-col" aria-label="会话工作台">
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
      <section
        v-if="pendingApprovals.length && pendingRunId !== null"
        class="border-b bg-primary/5 px-5 py-3"
        aria-label="等待确认的工具调用"
      >
        <p class="mb-2 text-xs font-medium text-primary">
          有 {{ pendingApprovals.length }} 个工具调用等待你确认，确认后才继续执行
        </p>
        <div class="max-h-72 space-y-2 overflow-y-auto">
          <ApprovalCard
            v-for="item in pendingApprovals"
            :key="item.callId"
            :run-id="pendingRunId"
            :item="item"
            @decided="refreshAfterDecision"
          />
        </div>
      </section>
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
        <span v-if="workspaceLabel" class="truncate text-muted-foreground"
          >工作区：{{ workspaceLabel }} ·</span
        ><span class="size-1.5 animate-pulse rounded-full bg-primary" />{{
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
        ref="composer"
        v-model="draft"
        :disabled="connection.state.status !== 'ready' || !state.selectedSessionId || state.loading"
        :busy="active !== null"
        :sending="!!state.sending[state.selectedSessionId ?? '']"
        :stopping="
          active !== null &&
          (!!state.cancelling[active.run.id] || active.run.cancel_requested_at !== null)
        "
        @send="handleSend"
        @stop="active && conversation!.cancel(active.run.id)"
      />
    </section>
  </div>
</template>
