<script setup lang="ts">
import { ArrowUp, Square } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
const props = defineProps<{
  modelValue: string
  disabled: boolean
  busy: boolean
  sending: boolean
  stopping: boolean
}>()
const emit = defineEmits<{ 'update:modelValue': [value: string]; send: []; stop: [] }>()
// 中文输入法确认候选时不得触发发送。
function keydown(event: KeyboardEvent) {
  if (event.key === 'Enter' && !event.shiftKey && !event.isComposing && event.keyCode !== 229) {
    event.preventDefault()
    if (!props.disabled && !props.busy && !props.sending && props.modelValue.trim()) emit('send')
  }
}
</script>
<template>
  <div class="mx-auto w-full max-w-3xl px-4 pb-5 pt-3 sm:px-7">
    <div
      class="rounded-2xl border bg-card p-2 shadow-[0_3px_18px_#00000004] focus-within:border-primary/50"
    >
      <Textarea
        :model-value="modelValue"
        aria-label="消息"
        placeholder="向 Prism 描述你想完成的事…"
        class="min-h-20 max-h-44 resize-none border-0 bg-transparent px-3 py-3 text-sm shadow-none focus-visible:ring-0"
        :disabled="disabled"
        @update:model-value="emit('update:modelValue', String($event))"
        @keydown="keydown"
      />
      <div class="flex items-center justify-between px-2 pb-1">
        <span class="text-[11px] text-muted-foreground"
          ><span class="hidden sm:inline">Enter 发送 · Shift + Enter 换行</span
          ><span class="sm:hidden">Shift + Enter 换行</span></span
        ><Button
          v-if="busy"
          variant="secondary"
          size="sm"
          :disabled="stopping"
          aria-label="停止运行"
          @click="emit('stop')"
          ><Square class="size-3 fill-current" />{{ stopping ? '等待停止确认' : '停止' }}</Button
        ><Button
          v-else
          size="icon-sm"
          :disabled="disabled || sending || !modelValue.trim()"
          aria-label="发送消息"
          @click="emit('send')"
          ><ArrowUp class="size-4"
        /></Button>
      </div>
    </div>
    <p class="mt-2 text-center text-[10px] tracking-wide text-muted-foreground">
      Prism 的回复可能存在误差，请核实关键信息。
    </p>
  </div>
</template>
