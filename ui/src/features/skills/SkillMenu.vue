<script setup lang="ts">
import type { SkillSummaryDto } from '@/lib/api/contracts'

defineProps<{ items: SkillSummaryDto[]; activeIndex: number }>()
const emit = defineEmits<{ select: [index: number] }>()
</script>

<template>
  <div class="max-h-52 overflow-y-auto rounded-xl border bg-card p-1 shadow-lg" role="listbox">
    <button
      v-for="(item, index) in items"
      :key="item.name"
      type="button"
      role="option"
      :aria-selected="index === activeIndex"
      class="flex w-full flex-col rounded-lg px-2 py-1.5 text-left text-xs"
      :class="index === activeIndex ? 'bg-secondary text-foreground' : 'text-muted-foreground'"
      @mousedown.prevent="emit('select', index)"
    >
      <span class="font-medium">{{ item.name }}</span>
      <span class="truncate text-[11px]">{{ item.description }}</span>
    </button>
  </div>
</template>
