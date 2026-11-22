<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
import { ChevronRight, Sparkles } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import type { MessageDto } from '@/lib/api/contracts'
import type { RunProjection } from '@/features/runs/projection'
const props = defineProps<{
  messages: MessageDto[]
  projection: RunProjection | null
  loading: boolean
}>()
const emit = defineEmits<{ inspect: [runId: string] }>()
const viewport = ref<HTMLElement>()
const atBottom = ref(true)
function onScroll() {
  const el = viewport.value
  if (el) atBottom.value = el.scrollHeight - el.scrollTop - el.clientHeight < 90
}
watch(
  () => [props.messages, props.projection?.transientText],
  async () => {
    if (!atBottom.value) return
    await nextTick()
    viewport.value?.scrollTo({ top: viewport.value.scrollHeight, behavior: 'instant' })
  },
)
function content(message: MessageDto) {
  return typeof message.content === 'string'
    ? message.content
    : JSON.stringify(message.content, null, 2)
}
</script>
<template>
  <div
    ref="viewport"
    role="log"
    aria-label="对话消息"
    :aria-busy="loading"
    class="min-h-0 flex-1 overflow-y-auto"
    @scroll="onScroll"
  >
    <div class="mx-auto max-w-3xl px-5 py-8 sm:px-9 sm:py-12">
      <p v-if="loading" role="status" class="py-12 text-center text-sm text-muted-foreground">
        正在读取会话…
      </p>
      <div v-else-if="messages.length === 0 && !projection" class="py-12 sm:py-20">
        <span
          class="mb-7 inline-flex size-11 items-center justify-center rounded-xl border bg-card text-primary"
          ><Sparkles class="size-5"
        /></span>
        <p class="mb-3 text-[11px] tracking-[0.2em] text-muted-foreground">PRISM / CORE</p>
        <h1 class="text-3xl font-medium tracking-tight sm:text-4xl">让想法，从这里开始。</h1>
        <p class="mt-4 max-w-md text-sm leading-7 text-muted-foreground">
          一个专注的对话空间。提一个问题，整理一个思路，或把下一步交给 Prism。
        </p>
      </div>
      <template v-for="message in messages" :key="message.id">
        <div
          v-if="message.role === 'user'"
          class="mb-9 ml-auto w-fit max-w-[90%] whitespace-pre-wrap break-words rounded-2xl rounded-br-sm bg-secondary px-5 py-3.5 text-sm leading-7"
        >
          {{ content(message) }}
        </div>
        <article v-else-if="message.role === 'assistant'" class="mb-10 min-w-0">
          <p
            class="mb-3 flex items-center gap-2 text-[11px] font-semibold tracking-widest text-primary"
          >
            <Sparkles class="size-3.5" />PRISM
          </p>
          <div class="whitespace-pre-wrap break-words text-sm leading-8">
            {{ content(message) }}
          </div>
          <details v-if="message.reasoning" class="mt-4 text-xs text-muted-foreground">
            <summary class="cursor-pointer">思考过程</summary>
            <p class="mt-2 whitespace-pre-wrap leading-7">{{ message.reasoning }}</p>
          </details>
          <Button
            variant="ghost"
            size="xs"
            class="mt-3 text-muted-foreground"
            @click="emit('inspect', message.run_id)"
            >查看执行<ChevronRight class="size-3"
          /></Button>
        </article>
      </template>
      <template v-if="projection">
        <div
          v-for="segment in projection.pendingSegments"
          :key="segment.messageId"
          class="mb-8 whitespace-pre-wrap text-sm leading-8"
        >
          {{ segment.text }}
          <p class="text-xs text-muted-foreground">正在同步持久消息…</p>
        </div>
        <article v-if="projection.transientText || projection.transientReasoning" class="mb-6">
          <p
            class="mb-3 flex items-center gap-2 text-[11px] font-semibold tracking-widest text-primary"
          >
            <Sparkles class="size-3.5 animate-pulse" />PRISM
          </p>
          <details v-if="projection.transientReasoning" class="mb-3 text-xs text-muted-foreground">
            <summary>思考过程</summary>
            <p class="whitespace-pre-wrap">{{ projection.transientReasoning }}</p>
          </details>
          <p class="whitespace-pre-wrap break-words leading-8">
            {{ projection.transientText
            }}<span
              aria-hidden="true"
              class="ml-1 inline-block h-4 w-1 animate-pulse bg-primary align-middle"
            />
          </p>
        </article>
        <button
          v-if="projection.tools.length"
          class="flex w-full items-center justify-between gap-3 rounded-xl border bg-card px-4 py-3 text-left text-xs text-muted-foreground hover:bg-secondary"
          @click="emit('inspect', projection.run.id)"
        >
          <span
            >{{ projection.tools.length }} 次工具调用<span
              v-if="projection.run.status === 'waiting_for_tool'"
            >
              · 等待外部工具结果</span
            ></span
          ><ChevronRight class="size-4" />
        </button>
      </template>
    </div>
  </div>
</template>
