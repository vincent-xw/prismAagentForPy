<script setup lang="ts">
import { ChevronDown, FolderClosed } from '@lucide/vue'

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import type { SessionDto, WorkspaceDto } from '@/lib/api/contracts'

const props = defineProps<{
  session: SessionDto
  workspaces: WorkspaceDto[]
}>()
const emit = defineEmits<{ bind: [workspaceId: string | null] }>()
function label(workspaceId: string | null): string {
  if (workspaceId === null) return '未绑定工作区'
  const workspace = props.workspaces.find((item) => item.id === workspaceId)
  if (workspace === undefined) return '工作区已删除'
  return (
    workspace.label ?? workspace.root_path.split('/').filter(Boolean).pop() ?? workspace.root_path
  )
}

function onSelect(value: unknown): void {
  const raw = typeof value === 'string' ? value : ''
  emit('bind', raw === '' || raw === '__none__' ? null : raw)
}
</script>

<template>
  <div class="flex min-w-0 items-center gap-2">
    <Select :model-value="session.workspace_id ?? '__none__'" @update:model-value="onSelect">
      <SelectTrigger
        class="h-7 max-w-[220px] gap-1.5 rounded-full border-primary/25 bg-primary/5 px-2.5 text-[11px] font-medium text-primary hover:bg-primary/10"
        :aria-label="`会话工作区：${label(session.workspace_id)}`"
      >
        <FolderClosed class="size-3.5 shrink-0" />
        <SelectValue class="truncate">{{ label(session.workspace_id) }}</SelectValue>
        <ChevronDown class="size-3 shrink-0 opacity-70" />
      </SelectTrigger>
      <SelectContent align="start">
        <SelectItem value="__none__">未绑定工作区</SelectItem>
        <SelectItem v-for="item in workspaces" :key="item.id" :value="item.id">
          {{ item.label ?? item.root_path }}
        </SelectItem>
      </SelectContent>
    </Select>
  </div>
</template>
