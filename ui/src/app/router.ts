import { createRouter, createWebHistory } from 'vue-router'
import SessionPage from '@/features/sessions/SessionPage.vue'
import SettingsRoute from '@/features/settings/SettingsRoute.vue'
import WorkspacePage from '@/features/workspace/WorkspacePage.vue'
import NotFoundPage from './NotFoundPage.vue'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: SessionPage },
    { path: '/sessions/:sessionId', component: SessionPage },
    { path: '/workspace', component: WorkspacePage },
    { path: '/settings', component: SettingsRoute },
    { path: '/:pathMatch(.*)*', component: NotFoundPage },
  ],
})
