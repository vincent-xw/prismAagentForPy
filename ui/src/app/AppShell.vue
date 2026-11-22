<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft, Menu, Settings, PanelsLeftBottom, Hexagon } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from '@/components/ui/sheet'
import { useAppContext } from './context'
import SessionSidebar from '@/features/sessions/SessionSidebar.vue'
const context = useAppContext()
const { conversation, connection } = context
const route = useRoute()
const router = useRouter()
const navigationOpen = ref(false)
const collapsed = ref(false)
const state = computed(() => conversation.value!.state)
const settings = computed(() => route.path === '/settings')
const lastSessionPath = computed(() =>
  state.value.selectedSessionId ? `/sessions/${state.value.selectedSessionId}` : '/',
)
const title = computed(() =>
  settings.value
    ? '连接与外观'
    : (state.value.sessions.find((item) => item.id === state.value.selectedSessionId)?.title ??
      '新的会话'),
)
async function create() {
  navigationOpen.value = false
  const session = await conversation.value!.createSession(null)
  if (session) await router.push(`/sessions/${session.id}`)
}
async function select(id: string) {
  navigationOpen.value = false
  await router.push(`/sessions/${id}`)
}
watch(
  [() => route.params.sessionId, () => connection.state.status, conversation],
  async () => {
    navigationOpen.value = false
    if (connection.state.status !== 'ready') return
    const controller = conversation.value!
    await controller.loadSessions()
    if (typeof route.params.sessionId === 'string')
      await controller.openSession(route.params.sessionId)
  },
  { immediate: true },
)
onMounted(() => {
  void context.initialize()
})
</script>
<template>
  <div class="flex h-dvh min-h-[480px] overflow-hidden bg-background">
    <aside v-if="!collapsed" class="hidden w-[230px] shrink-0 flex-col border-r md:flex">
      <RouterLink
        to="/"
        aria-label="Prism 首页"
        class="flex h-[72px] shrink-0 items-center gap-2.5 px-6"
        ><span
          class="flex size-7 items-center justify-center rounded-lg bg-primary text-primary-foreground"
          ><Hexagon class="size-4" /></span
        ><span class="text-xl font-semibold tracking-tight">Prism</span
        ><span
          class="ml-auto rounded border px-1.5 py-0.5 text-[9px] tracking-widest text-muted-foreground"
          >CORE</span
        ></RouterLink
      >
      <SessionSidebar
        class="min-h-0 flex-1"
        :sessions="state.sessions"
        :selected-id="state.selectedSessionId"
        :enabled="connection.state.status === 'ready'"
        @create="create"
        @select="select"
      />
      <RouterLink
        to="/settings"
        class="mx-4 mb-4 flex items-center gap-2 rounded-lg px-3 py-2 text-xs text-muted-foreground hover:bg-secondary"
        ><Settings class="size-4" />设置</RouterLink
      >
    </aside>
    <div class="flex min-w-0 flex-1 flex-col">
      <header class="flex h-[72px] shrink-0 items-center gap-3 border-b px-4 sm:px-6">
        <Button
          variant="ghost"
          size="icon-sm"
          class="md:hidden"
          aria-label="打开会话导航"
          @click="navigationOpen = true"
          ><Menu class="size-4" /></Button
        ><Button
          variant="ghost"
          size="icon-sm"
          class="hidden md:flex"
          aria-label="切换会话侧栏"
          @click="collapsed = !collapsed"
          ><PanelsLeftBottom class="size-4" /></Button
        ><RouterLink
          v-if="settings"
          :to="lastSessionPath"
          aria-label="返回会话"
          class="text-muted-foreground hover:text-foreground"
          ><ArrowLeft class="size-4"
        /></RouterLink>
        <h2 class="min-w-0 truncate text-[13px] font-medium">{{ title }}</h2>
        <div class="ml-auto flex shrink-0 items-center gap-2">
          <span
            class="size-1.5 rounded-full"
            :class="connection.state.status === 'ready' ? 'bg-primary' : 'bg-muted-foreground'"
          /><span class="hidden text-[11px] text-muted-foreground sm:inline">{{
            connection.state.status === 'ready' ? '访问已验证' : '未连接'
          }}</span
          ><RouterLink
            v-if="collapsed || navigationOpen"
            to="/settings"
            aria-label="设置"
            class="p-2 text-muted-foreground"
            ><Settings class="size-4" /></RouterLink
          ><Button
            v-if="connection.state.status === 'ready'"
            variant="ghost"
            size="xs"
            class="md:hidden"
            @click="create"
            >新建会话</Button
          >
        </div>
      </header>
      <RouterView />
    </div>
    <Sheet :open="navigationOpen" @update:open="navigationOpen = $event"
      ><SheetContent side="left" class="w-[min(85vw,300px)] gap-0 p-0"
        ><SheetHeader class="border-b p-5"
          ><SheetTitle>Prism · 会话</SheetTitle
          ><SheetDescription class="sr-only">选择会话或创建新会话</SheetDescription></SheetHeader
        ><SessionSidebar
          class="min-h-0 flex-1"
          :sessions="state.sessions"
          :selected-id="state.selectedSessionId"
          :enabled="connection.state.status === 'ready'"
          @create="create"
          @select="select"
        /><RouterLink
          to="/settings"
          class="m-4 flex items-center gap-2 rounded-lg p-3 text-sm text-muted-foreground"
          @click="navigationOpen = false"
          ><Settings class="size-4" />设置</RouterLink
        ></SheetContent
      ></Sheet
    >
  </div>
</template>
