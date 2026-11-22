<script setup lang="ts">
import { ref } from 'vue'
import { ArrowRight, Check, KeyRound, Plug, Sparkles } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import type { ConnectionController } from './connection'

const props = defineProps<{ connection: ConnectionController; open: boolean }>()
const emit = defineEmits<{ 'update:open': [value: boolean]; start: [] }>()
// 候选凭据只留在当前组件内存，验证成功后立刻清空表单。
const candidate = ref('')
const steps = ['连接服务', '验证访问', '开始使用']
async function next() {
  const state = props.connection.state
  if (state.step === 0 && (await props.connection.checkHealth())) state.step = 1
  else if (state.step === 1 && (await props.connection.verifyAccess(candidate.value))) {
    candidate.value = ''
    state.step = 2
  } else if (state.step === 2 && state.status === 'ready') {
    emit('update:open', false)
    emit('start')
  }
}
</script>

<template>
  <Dialog :open="open" @update:open="emit('update:open', $event)">
    <DialogContent class="gap-0 overflow-hidden p-0 sm:max-w-[520px]">
      <div class="px-7 pb-6 pt-9 sm:px-9">
        <div
          class="mb-7 flex size-11 items-center justify-center rounded-xl bg-accent text-primary"
        >
          <Plug v-if="connection.state.step === 0" /><KeyRound
            v-else-if="connection.state.step === 1"
          /><Sparkles v-else />
        </div>
        <ol class="mb-6 flex gap-4 text-xs text-muted-foreground" aria-label="连接步骤">
          <li
            v-for="(title, i) in steps"
            :key="title"
            :class="{ 'text-primary': i === connection.state.step }"
          >
            <span class="mr-1 font-mono">{{ i + 1 }}.</span>{{ title }}
          </li>
        </ol>
        <DialogHeader class="text-left">
          <DialogTitle class="text-2xl font-semibold tracking-tight">{{
            steps[connection.state.step]
          }}</DialogTitle>
          <DialogDescription class="mt-2 leading-7">
            <template v-if="connection.state.step === 0"
              >连接你的 Prism 服务，让想法有一个开始的地方。</template
            >
            <template v-else-if="connection.state.step === 1"
              >验证 API Token，安全访问会话和运行。</template
            >
            <template v-else>连接已准备好。现在可以开启第一段对话。</template>
          </DialogDescription>
        </DialogHeader>
        <div class="my-6 rounded-xl border bg-background p-4">
          <template v-if="connection.state.step === 0"
            ><p class="mb-1 text-xs text-muted-foreground">当前服务路径</p>
            <code>{{ connection.state.basePath }}</code>
            <p class="mt-3 text-xs text-muted-foreground">
              健康检查仅确认服务可达，不验证访问权限或模型。
            </p></template
          >
          <template v-else-if="connection.state.step === 1"
            ><Label for="wizard-token">API Token</Label
            ><Input
              id="wizard-token"
              v-model="candidate"
              type="password"
              autocomplete="off"
              class="my-3"
              placeholder="输入服务的 API Token"
              @keydown.enter="next"
            />
            <p class="text-xs text-muted-foreground">
              仅保存在当前标签页，关闭标签页后清除。
            </p></template
          >
          <template v-else
            ><p class="flex items-center gap-2"><Check class="size-4 text-primary" />服务可达</p>
            <p class="mt-2 flex items-center gap-2">
              <Check class="size-4 text-primary" />访问已验证
            </p>
            <p class="mt-3 text-xs text-muted-foreground">
              模型与工具能力以实际运行结果为准。
            </p></template
          >
        </div>
        <p
          v-if="connection.state.error || connection.state.healthError"
          role="alert"
          class="text-sm text-destructive"
        >
          {{ connection.state.step === 0 ? connection.state.healthError : connection.state.error }}
        </p>
        <p v-if="connection.state.storageError" role="status" class="text-sm text-muted-foreground">
          {{ connection.state.storageError }}
        </p>
      </div>
      <div class="flex items-center justify-between border-t bg-background px-7 py-5 sm:px-9">
        <Button variant="ghost" data-testid="wizard-later" @click="emit('update:open', false)"
          >暂时关闭</Button
        >
        <Button
          :disabled="connection.state.healthChecking || connection.state.status === 'checking'"
          @click="next"
          >{{
            connection.state.step === 0
              ? '检查连接'
              : connection.state.step === 1
                ? '验证访问'
                : '开始使用'
          }}<ArrowRight class="size-4"
        /></Button>
      </div>
    </DialogContent>
  </Dialog>
</template>
