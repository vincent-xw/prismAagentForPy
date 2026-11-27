<script setup lang="ts">
import { Monitor, Moon, Sun, ShieldCheck, Plug, Wrench } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import type { ConnectionController } from '@/features/connection/connection'
import type { useTheme, ThemePreference } from '@/app/theme/useTheme'

defineProps<{
  connection: ConnectionController
  theme: ReturnType<typeof useTheme>
}>()
const themes: { value: ThemePreference; label: string; icon: typeof Sun }[] = [
  { value: 'light', label: '浅色', icon: Sun },
  { value: 'dark', label: '深色', icon: Moon },
  { value: 'system', label: '跟随系统', icon: Monitor },
]
</script>
<template>
  <div class="mx-auto w-full max-w-3xl overflow-y-auto px-5 py-10 sm:px-10">
    <p class="mb-2 text-xs tracking-[0.18em] text-muted-foreground">PREFERENCES</p>
    <h1 class="text-3xl font-semibold tracking-tight">设置</h1>
    <p class="mt-3 text-muted-foreground">让 Prism 适应你的工作方式。</p>
    <section class="mt-10 border-t py-7" aria-labelledby="appearance-title">
      <h2 id="appearance-title" class="text-base font-medium">外观</h2>
      <p class="mt-1 text-sm text-muted-foreground">选择适合当前环境的主题。</p>
      <div class="mt-5 grid grid-cols-3 gap-3">
        <button
          v-for="choice in themes"
          :key="choice.value"
          :data-theme-choice="choice.value"
          :aria-pressed="theme.preference.value === choice.value"
          class="flex flex-col items-center gap-3 rounded-xl border px-2 py-5 transition-colors hover:bg-accent"
          :class="
            theme.preference.value === choice.value
              ? 'border-primary bg-accent text-primary'
              : 'bg-card'
          "
          @click="theme.setPreference(choice.value)"
        >
          <component :is="choice.icon" class="size-5" /><span class="text-sm">{{
            choice.label
          }}</span>
        </button>
      </div>
      <p v-if="theme.storageError.value" role="status" class="mt-3 text-sm text-destructive">
        {{ theme.storageError.value }}
      </p>
    </section>
    <section class="border-t py-7" aria-labelledby="connection-title">
      <h2 id="connection-title" class="flex items-center gap-2 text-base font-medium">
        <Plug class="size-4" />服务连接
      </h2>
      <div class="my-5 rounded-xl border bg-card p-4">
        <p class="text-xs text-muted-foreground">当前服务路径</p>
        <code class="mt-2 block text-sm">{{ connection.state.basePath }}</code>
      </div>
      <div class="flex flex-wrap items-center gap-3">
        <Button
          variant="outline"
          :disabled="connection.state.healthChecking"
          @click="connection.checkHealth()"
          >检查服务</Button
        ><span v-if="connection.state.health" class="text-sm text-muted-foreground"
          >{{ connection.state.health.service }} · {{ connection.state.health.version }} ·
          {{ connection.state.health.environment }}</span
        >
      </div>
      <p v-if="connection.state.healthError" role="alert" class="mt-3 text-sm text-destructive">
        {{ connection.state.healthError }}
      </p>
      <p class="mt-4 flex items-center gap-2 text-sm text-primary">
        <ShieldCheck class="size-4" />已连接（内置凭据，无需手动填写 Token）
      </p>
      <p v-if="connection.state.error" role="alert" class="mt-3 text-sm text-destructive">
        {{ connection.state.error }}
      </p>
      <p v-if="connection.state.storageError" role="status" class="mt-3 text-sm text-destructive">
        {{ connection.state.storageError }}
      </p>
    </section>
    <section class="border-t py-7" aria-labelledby="tools-title">
      <h2 id="tools-title" class="flex items-center gap-2 text-base font-medium">
        <Wrench class="size-4" />当前服务的工具
      </h2>
      <p v-if="connection.state.status !== 'ready'" class="mt-4 text-sm text-muted-foreground">
        验证访问后查看工具目录。
      </p>
      <p
        v-else-if="connection.state.tools.length === 0"
        class="mt-4 rounded-xl border border-dashed p-6 text-sm text-muted-foreground"
      >
        尚未注册工具。你仍然可以使用服务提供的对话能力。
      </p>
      <details
        v-for="tool in connection.state.tools"
        v-else
        :key="tool.name"
        class="mt-3 rounded-lg border bg-card p-4"
      >
        <summary class="cursor-pointer font-medium">
          {{ tool.name }}
          <span class="ml-2 text-xs text-muted-foreground">{{
            tool.execution_mode === 'remote' ? '外部宿主' : '本地执行'
          }}</span>
        </summary>
        <p class="my-3 text-sm text-muted-foreground">{{ tool.description }}</p>
        <pre class="text-xs">{{ JSON.stringify(tool.input_schema, null, 2) }}</pre>
      </details>
    </section>
  </div>
</template>
