<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'

import { Loader2 } from '@lucide/vue'

import { useAppContext } from '@/app/context'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import type { McpServerDto } from '@/lib/api/contracts'
import { createMcpController } from './mcp'

const { client } = useAppContext()
const controller = createMcpController({ client })
const state = controller.state
const formError = ref<string | null>(null)

const form = reactive({
  name: '',
  transport: 'stdio' as 'stdio' | 'http',
  command: '',
  args: '',
  env: '',
  url: '',
  headers: '',
})

const canSubmit = computed(() => !state.loading && form.name !== '')
const isEditing = computed(() => state.editingId !== null)
const STATUS_LABEL: Record<string, string> = {
  disabled: '已停用',
  connecting: '连接中…',
  connected: '已连接',
  error: '连接失败',
}

function statusLabel(server: McpServerDto): string {
  return STATUS_LABEL[server.status] ?? server.status
}

function parsePairs(text: string): Record<string, string> {
  const result: Record<string, string> = {}
  for (const line of text.split('\n')) {
    const trimmed = line.trim()
    if (trimmed === '') continue
    const index = trimmed.indexOf('=')
    if (index > 0) result[trimmed.slice(0, index).trim()] = trimmed.slice(index + 1).trim()
  }
  return result
}

function pairsToText(pairs: Record<string, string>): string {
  return Object.entries(pairs)
    .map(([key, value]) => `${key}=${value}`)
    .join('\n')
}

function resetForm(): void {
  form.name = ''
  form.transport = 'stdio'
  form.command = ''
  form.args = ''
  form.env = ''
  form.url = ''
  form.headers = ''
}

function edit(server: McpServerDto): void {
  controller.beginEdit(server)
  form.name = server.name
  form.transport = server.transport
  form.command = server.command ?? ''
  form.args = server.args.join('\n')
  form.env = pairsToText(server.env)
  form.url = server.url ?? ''
  form.headers = pairsToText(server.headers)
}

function cancelEdit(): void {
  controller.cancelEdit()
  resetForm()
  formError.value = null
}

async function submit(): Promise<void> {
  formError.value = null
  if (form.name.trim() === '') {
    formError.value = '服务名不能为空'
    return
  }
  await controller.save({
    name: form.name.trim(),
    transport: form.transport,
    command: form.transport === 'stdio' ? form.command : null,
    args: form.transport === 'stdio' ? form.args.split('\n').filter((item) => item.trim()) : [],
    env: form.transport === 'stdio' ? parsePairs(form.env) : {},
    url: form.transport === 'http' ? form.url : null,
    headers: form.transport === 'http' ? parsePairs(form.headers) : {},
    enabled: false,
  })
  if (state.error === null) {
    resetForm()
  } else {
    // 提交失败时把错误固定显示在按钮下方，并清掉全局错误避免页面顶部跳动。
    formError.value = state.error
    state.error = null
  }
}

async function remove(server: McpServerDto): Promise<void> {
  if (!window.confirm(`删除 MCP 服务「${server.name}」？`)) return
  await controller.remove(server)
}

let timer: number | null = null
onMounted(() => {
  void controller.load()
  timer = window.setInterval(() => void controller.load(), 3000)
})
onUnmounted(() => {
  if (timer !== null) window.clearInterval(timer)
})
</script>

<template>
  <section class="mx-auto w-full max-w-4xl px-6 py-8">
    <header class="flex items-center justify-between">
      <h1 class="text-lg font-semibold">MCP 服务</h1>
      <p class="text-xs text-muted-foreground">连接外部 MCP 服务并接入其工具</p>
    </header>

    <p class="mt-2 min-h-4 text-xs text-destructive">{{ state.error ?? '' }}</p>

    <div class="mt-6 space-y-3">
      <div v-for="server in state.servers" :key="server.id" class="rounded-xl border p-4">
        <div class="flex items-center justify-between">
          <div>
            <p class="text-sm font-medium">
              {{ server.name }}
              <span v-if="state.editingId === server.id" class="ml-2 text-xs text-primary"
                >编辑中</span
              >
            </p>
            <p class="mt-1 flex items-center gap-1 text-xs text-muted-foreground">
              <Loader2
                v-if="server.status === 'connecting'"
                class="size-3 animate-spin text-primary"
              />
              <span>{{ server.transport }} · {{ statusLabel(server) }} ·</span>
              <span v-if="server.status === 'connecting'">加载工具中…</span>
              <span v-else>{{ server.tool_count }} 个工具</span>
            </p>
            <p v-if="server.last_error" class="mt-1 break-all text-xs text-destructive">
              {{ server.last_error }}
            </p>
          </div>
          <div class="flex gap-2">
            <Button
              size="sm"
              variant="outline"
              :disabled="server.status === 'connecting'"
              @click="controller.openTools(server)"
              >工具</Button
            >
            <Button size="sm" variant="outline" @click="edit(server)">编辑</Button>
            <Button
              size="sm"
              variant="outline"
              :disabled="server.status === 'connecting'"
              @click="controller.reconnect(server)"
              >重连</Button
            >
            <Button
              size="sm"
              variant="outline"
              :disabled="server.status === 'connecting'"
              @click="controller.toggle(server)"
            >
              {{ server.enabled ? '停用' : '启用' }}
            </Button>
            <Button
              size="sm"
              variant="outline"
              :disabled="server.status === 'connecting'"
              @click="remove(server)"
              >删除</Button
            >
          </div>
        </div>
        <div v-if="state.selectedId === server.id" class="mt-3 border-t pt-3">
          <p v-if="!state.tools.length" class="text-xs text-muted-foreground">暂无已注册工具</p>
          <details v-for="tool in state.tools" :key="tool.name" class="mt-2 text-xs">
            <summary class="cursor-pointer">
              <span class="font-medium">{{ tool.name }}</span>
              <span class="ml-2 text-muted-foreground">{{ tool.description }}</span>
            </summary>
            <pre class="mt-2 max-h-56 overflow-auto rounded-lg bg-secondary p-3">{{
              JSON.stringify(tool.input_schema, null, 2)
            }}</pre>
          </details>
        </div>
      </div>
      <p v-if="!state.servers.length" class="text-sm text-muted-foreground">尚未配置 MCP 服务。</p>
    </div>

    <form class="mt-8 space-y-3 rounded-xl border p-4" @submit.prevent="submit">
      <div class="flex items-center justify-between">
        <h2 class="text-sm font-medium">{{ isEditing ? '编辑服务' : '添加服务' }}</h2>
        <button
          v-if="isEditing"
          type="button"
          class="text-xs text-muted-foreground"
          @click="cancelEdit"
        >
          取消编辑
        </button>
      </div>
      <div>
        <Input v-model="form.name" placeholder="名称，例如 DeepWiki" />
        <p class="mt-1 text-[11px] text-muted-foreground">
          可含大小写与空格；工具前缀会规范化为小写，如 DeepWiki → deepwiki
        </p>
      </div>
      <select
        v-model="form.transport"
        class="w-full rounded-lg border bg-background px-3 py-2 text-sm"
      >
        <option value="stdio">stdio</option>
        <option value="http">Streamable HTTP</option>
      </select>
      <div class="h-[176px] space-y-3">
        <template v-if="form.transport === 'stdio'">
          <Input v-model="form.command" placeholder="command，例如 python" />
          <textarea
            v-model="form.args"
            placeholder="args，每行一个"
            class="h-14 w-full rounded-lg border bg-background p-3 text-xs"
          />
          <textarea
            v-model="form.env"
            placeholder="env，每行 KEY=VALUE；value 为 *** 表示保持原值"
            class="h-14 w-full rounded-lg border bg-background p-3 text-xs"
          />
        </template>
        <template v-else>
          <Input v-model="form.url" placeholder="https://example.com/mcp" />
          <textarea
            v-model="form.headers"
            placeholder="headers，每行 KEY=VALUE；value 为 *** 表示保持原值"
            class="h-14 w-full rounded-lg border bg-background p-3 text-xs"
          />
        </template>
      </div>
      <Button size="sm" type="submit" :disabled="canSubmit === false">
        {{ isEditing ? '保存修改' : '保存' }}
      </Button>
      <p class="min-h-[18px] text-xs text-destructive">{{ formError ?? '' }}</p>
    </form>
  </section>
</template>
