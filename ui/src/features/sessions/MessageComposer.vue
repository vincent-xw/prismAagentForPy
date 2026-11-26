<script setup lang="ts">
import { ArrowUp, Square, X } from '@lucide/vue'
import { computed, onMounted, ref } from 'vue'

import { useAppContext } from '@/app/context'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import SkillMenu from '@/features/skills/SkillMenu.vue'
import type { SkillSummaryDto } from '@/lib/api/contracts'

const props = defineProps<{
  modelValue: string
  disabled: boolean
  busy: boolean
  sending: boolean
  stopping: boolean
}>()
const emit = defineEmits<{
  'update:modelValue': [value: string]
  send: [payload: { text: string; skillName: string | null }]
  stop: []
}>()

const { client } = useAppContext()
const skills = ref<SkillSummaryDto[]>([])
const selected = ref<SkillSummaryDto | null>(null)
const menuOpen = ref(false)
const query = ref('')
const tokenStart = ref(0)
const highlight = ref(0)
const composing = ref(false)

const filtered = computed(() => {
  const needle = query.value.trim().toLowerCase()
  const visible = skills.value.filter((item) => !item.shadowed)
  if (needle === '') return visible.slice(0, 20)
  // 优先按技能名匹配；名字没有命中时才退回描述匹配，避免常见字母把整个列表带出来。
  const byName = visible.filter((item) => item.name.toLowerCase().includes(needle))
  const pool =
    byName.length > 0
      ? byName
      : visible.filter((item) => item.description.toLowerCase().includes(needle))
  return pool
    .sort((left, right) => {
      const prefix =
        Number(right.name.toLowerCase().startsWith(needle)) -
        Number(left.name.toLowerCase().startsWith(needle))
      return prefix !== 0 ? prefix : left.name.localeCompare(right.name)
    })
    .slice(0, 20)
})

onMounted(async () => {
  if (client === undefined) return
  try {
    skills.value = (await client.listSkills()).items
  } catch {
    skills.value = []
  }
})

function selectSkill(item: SkillSummaryDto): void {
  const value = props.modelValue
  const end = tokenStart.value + 1 + query.value.length
  const next = `${value.slice(0, tokenStart.value)}${value.slice(end)}`
  selected.value = item
  menuOpen.value = false
  query.value = ''
  emit('update:modelValue', next)
}

function clearSkill(): void {
  selected.value = null
}

function onInput(event: Event): void {
  const target = event.target as HTMLTextAreaElement
  const value = target.value
  emit('update:modelValue', value)
  const cursor = target.selectionStart ?? 0
  const match = /(^|\s)\/([\w-]*)$/.exec(value.slice(0, cursor))
  if (match !== null) {
    tokenStart.value = cursor - (match[2]?.length ?? 0) - 1
    query.value = match[2] ?? ''
    menuOpen.value = true
    highlight.value = 0
  } else {
    menuOpen.value = false
  }
}

function submit(): void {
  if (props.disabled || props.busy || props.sending || !props.modelValue.trim()) return
  emit('send', { text: props.modelValue, skillName: selected.value?.name ?? null })
}

function keydown(event: KeyboardEvent): void {
  if (event.isComposing || composing.value || event.keyCode === 229) return
  if (menuOpen.value && filtered.value.length === 0) {
    if (event.key === 'Enter' || event.key === 'Tab' || event.key === 'Escape') {
      event.preventDefault()
      menuOpen.value = false
    }
    return
  }
  if (menuOpen.value && filtered.value.length > 0) {
    if (event.key === 'ArrowDown') {
      event.preventDefault()
      highlight.value = (highlight.value + 1) % filtered.value.length
      return
    }
    if (event.key === 'ArrowUp') {
      event.preventDefault()
      highlight.value = (highlight.value - 1 + filtered.value.length) % filtered.value.length
      return
    }
    if (event.key === 'Enter' || event.key === 'Tab') {
      event.preventDefault()
      const item = filtered.value[highlight.value]
      if (item !== undefined) selectSkill(item)
      return
    }
    if (event.key === 'Escape') {
      event.preventDefault()
      menuOpen.value = false
      return
    }
  }
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    submit()
  }
}

defineExpose({ clearSkill })
</script>

<template>
  <div class="mx-auto w-full max-w-3xl px-4 pb-5 pt-3 sm:px-7">
    <div
      class="relative rounded-2xl border bg-card p-2 shadow-[0_3px_18px_#00000004] focus-within:border-primary/50"
    >
      <div v-if="menuOpen" class="absolute inset-x-2 bottom-full z-10 mb-1">
        <SkillMenu
          v-if="filtered.length > 0"
          :items="filtered"
          :active-index="highlight"
          @select="(index) => selectSkill(filtered[index]!)"
        />
        <p v-else class="rounded-xl border bg-card px-3 py-2 text-xs text-muted-foreground">
          没有匹配的技能
        </p>
      </div>
      <div v-if="selected !== null" class="mb-1 flex">
        <span
          class="inline-flex items-center gap-1 rounded-full bg-primary/10 px-2 py-1 text-[11px] text-primary"
          >◈ {{ selected.name }}
          <button type="button" aria-label="移除技能" @click="clearSkill">
            <X class="size-3" /></button
        ></span>
      </div>
      <Textarea
        :model-value="modelValue"
        aria-label="消息"
        placeholder="向 Prism 描述你想完成的事… 输入 / 选择技能"
        class="min-h-20 max-h-44 resize-none border-0 bg-transparent px-3 py-3 text-sm shadow-none focus-visible:ring-0"
        :disabled="disabled"
        @input="onInput"
        @compositionstart="composing = true"
        @compositionend="composing = false"
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
          @click="submit"
          ><ArrowUp class="size-4"
        /></Button>
      </div>
    </div>
    <p class="mt-2 text-center text-[10px] tracking-wide text-muted-foreground">
      Prism 的回复可能存在误差，请核实关键信息。
    </p>
  </div>
</template>
