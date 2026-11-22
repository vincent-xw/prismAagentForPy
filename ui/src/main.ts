import { createApp } from 'vue'
import App from '@/App.vue'
import '@/styles/main.css'
import { appContextKey, createAppContext } from '@/app/context'
import { router } from '@/app/router'

// 配置错误明确展示，不能挂载一个貌似可用但缺少 API 地址的工作台。
try {
  const context = createAppContext()
  createApp(App).provide(appContextKey, context).use(router).mount('#app')
  window.addEventListener('pagehide', context.dispose, { once: true })
} catch (error) {
  const root = document.querySelector('#app')!
  const message = document.createElement('p')
  message.setAttribute('role', 'alert')
  message.style.padding = '32px'
  message.textContent = error instanceof Error ? error.message : '应用初始化失败。'
  root.append(message)
}
