<script setup lang="ts">
import { RotateCw, X } from '@lucide/vue'

import { Button } from '@/components/ui/button'
import type { RunProjection } from './projection'
import ToolCallCard from './ToolCallCard.vue'

defineProps<{ projection: RunProjection | null }>()
const emit = defineEmits<{ close: []; refresh: [] }>()
</script>

<template>
  <section class="h-full overflow-y-auto bg-card p-5" aria-label="工具执行明细">
    <div class="mb-5 flex items-center justify-between">
      <h2 class="text-sm font-semibold">工具调用</h2>
      <div class="flex items-center gap-1">
        <Button
          variant="ghost"
          size="icon-xs"
          aria-label="重新读取执行详情"
          @click="emit('refresh')"
          ><RotateCw class="size-3.5"
        /></Button>
        <Button variant="ghost" size="icon-xs" aria-label="收起执行详情" @click="emit('close')"
          ><X class="size-4"
        /></Button>
      </div>
    </div>
    <template v-if="projection">
      <p class="mb-3 text-xs text-muted-foreground">共 {{ projection.tools.length }} 个工具调用</p>
      <p v-if="!projection.tools.length" class="text-xs leading-6 text-muted-foreground">
        本次运行没有工具调用。
      </p>
      <ToolCallCard v-for="tool in projection.tools" :key="tool.callId" :tool="tool" />
    </template>
    <p v-else class="text-sm text-muted-foreground">选择一条消息的执行记录查看详情。</p>
  </section>
</template>
