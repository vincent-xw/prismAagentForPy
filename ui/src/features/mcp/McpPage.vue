<script setup lang="ts">
import { computed, onMounted, reactive } from 'vue'

import { useAppContext } from '@/app/context'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { createMcpController } from './mcp'

const { client } = useAppContext()
const controller = createMcpController({ client })
const state = controller.state

const canSubmit = computed(() => !state.loading && form.name !== '')

const form = reactive({
  name: '',
  transport: 'stdio' as 'stdio' | 'http',
  command: '',
  args: '',
  env: '',
  url: '',
  headers: '',
})

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

async function submit(): Promise<void> {
  await controller.create({
    name: form.name,
    transport: form.transport,
    command: form.transport === 'stdio' ? form.command : null,
    args: form.transport === 'stdio' ? form.args.split('\n').filter((item) => item.trim()) : [],
    env: form.transport === 'stdio' ? parsePairs(form.env) : {},
    url: form.transport === 'http' ? form.url : null,
    headers: form.transport === 'http' ? parsePairs(form.headers) : {},
    enabled: false,
  })
  form.name = ''
  form.command = ''
  form.args = ''
  form.env = ''
  form.url = ''
  form.headers = ''
}

onMounted(() => void controller.load())
</script>

<template>
  <section class="mx-auto max-w-4xl px-6 py-8">
    <header class="flex items-center justify-between">
      <h1 class="text-lg font-semibold">MCP 服务</h1>
      <p class="text-xs text-muted-foreground">连接外部 MCP 服务并接入其工具</p>
    </header>

    <p v-if="state.error" class="mt-4 rounded-lg bg-destructive/10 p-3 text-xs text-destructive">
      {{ state.error }}
    </p>

    <div class="mt-6 space-y-3">
      <div v-for="server in state.servers" :key="server.id" class="rounded-xl border p-4">
        <div class="flex items-center justify-between">
          <div>
            <p class="text-sm font-medium">{{ server.name }}</p>
            <p class="mt-1 text-xs text-muted-foreground">
              {{ server.transport }} · {{ server.status }} · {{ server.tool_count }} 个工具
            </p>
            <p v-if="server.last_error" class="mt-1 break-all text-xs text-destructive">
              {{ server.last_error }}
            </p>
          </div>
          <div class="flex gap-2">
            <Button size="sm" variant="outline" @click="controller.openTools(server)">工具</Button>
            <Button size="sm" variant="outline" @click="controller.reconnect(server)">重连</Button>
            <Button size="sm" variant="outline" @click="controller.toggle(server)">
              {{ server.enabled ? '停用' : '启用' }}
            </Button>
            <Button size="sm" variant="outline" @click="controller.remove(server)">删除</Button>
          </div>
        </div>
        <div v-if="state.selectedId === server.id" class="mt-3 border-t pt-3">
          <p v-if="!state.tools.length" class="text-xs text-muted-foreground">暂无已注册工具</p>
          <p v-for="tool in state.tools" :key="tool.name" class="text-xs">
            <span class="font-medium">{{ tool.name }}</span>
            <span class="ml-2 text-muted-foreground">{{ tool.description }}</span>
          </p>
        </div>
      </div>
      <p v-if="!state.servers.length" class="text-sm text-muted-foreground">尚未配置 MCP 服务。</p>
    </div>

    <form class="mt-8 space-y-3 rounded-xl border p-4" @submit.prevent="submit">
      <h2 class="text-sm font-medium">添加服务</h2>
      <Input v-model="form.name" placeholder="名称（小写字母、数字、连字符）" />
      <select
        v-model="form.transport"
        class="w-full rounded-lg border bg-background px-3 py-2 text-sm"
      >
        <option value="stdio">stdio</option>
        <option value="http">Streamable HTTP</option>
      </select>
      <template v-if="form.transport === 'stdio'">
        <Input v-model="form.command" placeholder="command，例如 python" />
        <textarea
          v-model="form.args"
          placeholder="args，每行一个"
          class="min-h-16 w-full rounded-lg border bg-background p-3 text-xs"
        />
        <textarea
          v-model="form.env"
          placeholder="env，每行 KEY=VALUE，值可写 ${VAR}"
          class="min-h-16 w-full rounded-lg border bg-background p-3 text-xs"
        />
      </template>
      <template v-else>
        <Input v-model="form.url" placeholder="https://example.com/mcp" />
        <textarea
          v-model="form.headers"
          placeholder="headers，每行 KEY=VALUE，值可写 ${VAR}"
          class="min-h-16 w-full rounded-lg border bg-background p-3 text-xs"
        />
      </template>
      <Button size="sm" type="submit" :disabled="canSubmit">保存</Button>
    </form>
  </section>
</template>
