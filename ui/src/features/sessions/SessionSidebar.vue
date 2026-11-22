<script setup lang="ts">
import { MessageSquare, Plus } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import type { SessionDto } from '@/lib/api/contracts'
defineProps<{ sessions: SessionDto[]; selectedId: string | null; enabled: boolean }>()
const emit = defineEmits<{ create: []; select: [id: string] }>()
</script>
<template>
  <div class="flex h-full min-h-0 flex-col px-4 py-5">
    <Button
      variant="outline"
      class="w-full justify-start bg-card"
      :disabled="!enabled"
      @click="emit('create')"
      ><Plus class="size-4" />新建会话</Button
    >
    <p class="mb-3 mt-8 px-2 text-[11px] tracking-[0.12em] text-muted-foreground">最近的会话</p>
    <nav aria-label="会话列表" class="min-h-0 flex-1 space-y-1 overflow-y-auto">
      <button
        v-for="session in sessions"
        :key="session.id"
        :aria-current="selectedId === session.id ? 'page' : undefined"
        class="flex w-full items-center gap-2.5 rounded-lg px-3 py-2.5 text-left text-[13px] transition-colors hover:bg-secondary"
        :class="selectedId === session.id ? 'bg-accent text-primary' : 'text-muted-foreground'"
        @click="emit('select', session.id)"
      >
        <MessageSquare class="size-3.5 shrink-0" /><span class="truncate">{{
          session.title === null ? '未命名会话' : session.title
        }}</span>
      </button>
      <p v-if="!sessions.length" class="px-2 py-3 text-xs leading-6 text-muted-foreground">
        {{ enabled ? '还没有会话。新建一个，开始对话。' : '连接服务后查看会话。' }}
      </p>
    </nav>
    <div class="mt-4 border-t px-2 pt-4 text-xs leading-6 text-muted-foreground">
      <span class="font-medium text-foreground">Prism Core</span><br />专注当下，让想法向前。
    </div>
  </div>
</template>
