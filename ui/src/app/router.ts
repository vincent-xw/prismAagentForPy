import { createRouter, createWebHistory } from 'vue-router'
import SessionPage from '@/features/sessions/SessionPage.vue'
import SettingsRoute from '@/features/settings/SettingsRoute.vue'
import WorkspacePage from '@/features/workspace/WorkspacePage.vue'
import McpPage from '@/features/mcp/McpPage.vue'
import ModelProfilesPage from '@/features/models/ModelProfilesPage.vue'
import ExecutionPage from '@/features/runs/ExecutionPage.vue'
import NotFoundPage from './NotFoundPage.vue'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: SessionPage },
    { path: '/sessions/:sessionId', component: SessionPage },
    { path: '/sessions/:sessionId/execution', component: ExecutionPage },
    { path: '/workspace', component: WorkspacePage },
    { path: '/mcp', component: McpPage },
    { path: '/models', component: ModelProfilesPage },
    { path: '/settings', component: SettingsRoute },
    { path: '/:pathMatch(.*)*', component: NotFoundPage },
  ],
})
