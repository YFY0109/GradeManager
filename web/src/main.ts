import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import 'element-plus/dist/index.css'
import * as ElementPlusIconsVue from '@element-plus/icons-vue'

import App from './App.vue'
import router from './router'
import { onUnauthorized } from './api/client'
import { useAuthStore } from './stores/auth'
import './styles.css'

const app = createApp(App)
const pinia = createPinia()

app.use(pinia)
app.use(router)
app.use(ElementPlus, { locale: zhCn })

for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
  app.component(key, component)
}

const auth = useAuthStore(pinia)
onUnauthorized(() => {
  auth.user = null
  const current = router.currentRoute.value
  if (current.name && current.name !== 'login') {
    router.push({ path: '/login', query: { redirect: current.fullPath } })
  }
})

app.mount('#app')
