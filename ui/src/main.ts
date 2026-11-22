import { createApp } from 'vue'
import App from '@/App.vue'
import '@/styles/main.css'

// 挂载前端根组件，业务页面后续从此入口扩展。
createApp(App).mount('#app')
