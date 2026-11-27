<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import { useAppContext } from '@/app/context'
import { Button } from '@/components/ui/button'
import type { ModelProfileDto } from '@/lib/api/contracts'
import { createModelsController } from './models'

const { client } = useAppContext()
const controller = createModelsController({ client })
const state = controller.state
const form = reactive({
  name: '',
  base_url: 'https://api.openai.com/v1',
  model: '',
  api_key_env: 'OPENAI_API_KEY',
  api_key: '',
  context_window: 128000,
  max_output_tokens: 8192,
})
const contextWindow = ref(128000)
const maxOutputTokens = ref(8192)
const isEditing = computed(() => state.editingId !== null)
const canSubmit = computed(() => !state.loading && form.name.trim() !== '')

function edit(profile: ModelProfileDto): void {
  controller.beginEdit(profile)
  form.name = profile.name
  form.base_url = profile.base_url
  form.model = profile.model
  form.api_key_env = profile.api_key_env
  form.api_key = ''
  contextWindow.value = profile.context_window
  maxOutputTokens.value = profile.max_output_tokens
}

async function submit(): Promise<void> {
  const payload = {
    ...form,
    context_window: contextWindow.value,
    max_output_tokens: maxOutputTokens.value,
  }
  // 留空表示不修改；只有真正填了值才发送 api_key。
  if (form.api_key.trim() === '') {
    delete (payload as { api_key?: string }).api_key
  } else {
    payload.api_key = form.api_key.trim()
  }
  await controller.save(payload)
}

onMounted(() => void controller.load())
</script>

<template>
  <section class="mx-auto w-full max-w-4xl px-6 py-8">
    <header class="flex items-center justify-between">
      <h1 class="text-lg font-semibold">模型档案</h1>
      <p class="text-xs text-muted-foreground">切换后下一次请求生效，历史会话同样使用新档案</p>
    </header>

    <p v-if="state.error" class="mt-3 text-xs text-destructive">{{ state.error }}</p>
    <p v-if="state.notice" class="mt-3 text-xs text-muted-foreground">{{ state.notice }}</p>

    <div class="mt-6 space-y-3">
      <div v-for="profile in state.profiles" :key="profile.id" class="rounded-xl border p-4">
        <div class="flex items-center justify-between gap-3">
          <div>
            <p class="text-sm font-medium">
              {{ profile.name }}
              <span v-if="profile.is_active" class="ml-2 text-xs text-primary">使用中</span>
            </p>
            <p class="mt-1 break-all text-xs text-muted-foreground">
              {{ profile.model }} · {{ profile.base_url }} · 密钥变量 {{ profile.api_key_env }} ·
              {{ profile.has_key ? '已配置密钥' : '未配置密钥' }}
            </p>
          </div>
          <div class="flex shrink-0 gap-2">
            <Button size="sm" variant="outline" @click="controller.probe(profile)">测试</Button>
            <Button
              size="sm"
              variant="outline"
              :disabled="profile.is_active"
              @click="controller.activate(profile)"
              >切换</Button
            >
            <Button size="sm" variant="outline" @click="edit(profile)">编辑</Button>
            <Button size="sm" variant="outline" @click="controller.remove(profile)">删除</Button>
          </div>
        </div>
      </div>
      <p v-if="!state.profiles.length" class="text-sm text-muted-foreground">
        还没有档案；未配置时使用 .env 的环境配置。
      </p>
    </div>

    <form class="mt-8 space-y-3 rounded-xl border p-4" @submit.prevent="submit">
      <div class="flex items-center justify-between">
        <h2 class="text-sm font-medium">{{ isEditing ? '编辑档案' : '新增档案' }}</h2>
        <button
          v-if="isEditing"
          type="button"
          class="text-xs text-muted-foreground"
          @click="controller.cancelEdit()"
        >
          取消编辑
        </button>
      </div>
      <input
        v-model="form.name"
        class="w-full rounded-lg border bg-background px-3 py-2 text-sm"
        placeholder="档案名称"
      />
      <input
        v-model="form.base_url"
        class="w-full rounded-lg border bg-background px-3 py-2 text-sm"
        placeholder="https://api.example.com/v1"
      />
      <input
        v-model="form.model"
        class="w-full rounded-lg border bg-background px-3 py-2 text-sm"
        placeholder="模型名，例如 deepseek-chat"
      />
      <input
        v-model="form.api_key_env"
        class="w-full rounded-lg border bg-background px-3 py-2 text-sm"
        placeholder="密钥环境变量名，例如 OPENAI_API_KEY"
      />
      <div class="grid grid-cols-2 gap-3">
        <input
          v-model.number="contextWindow"
          type="number"
          class="w-full rounded-lg border bg-background px-3 py-2 text-sm"
          placeholder="上下文窗口"
        />
        <input
          v-model.number="maxOutputTokens"
          type="number"
          class="w-full rounded-lg border bg-background px-3 py-2 text-sm"
          placeholder="最大输出 tokens"
        />
      </div>
      <input
        v-model="form.api_key"
        type="password"
        autocomplete="new-password"
        class="w-full rounded-lg border bg-background px-3 py-2 text-sm"
        :placeholder="isEditing ? '留空表示不修改密钥' : 'API Key（可选）'"
      />
      <p class="text-[11px] text-muted-foreground">
        密钥可直接保存在本地数据库（仅本机可读）；留空则回退到上面的环境变量。
      </p>
      <Button size="sm" type="submit" :disabled="canSubmit">
        {{ isEditing ? '保存修改' : '保存' }}
      </Button>
    </form>
  </section>
</template>
