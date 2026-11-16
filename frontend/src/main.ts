import { createPinia } from 'pinia'
import { createApp } from 'vue'

import App from './App.vue'
import { i18n } from './i18n'
import { router } from './router'
import { useAuthStore } from './stores/auth'
import { useUiStore } from './stores/ui'
import './style.css'

async function boot() {
  const pinia = createPinia()
  const app = createApp(App).use(pinia).use(i18n)
  useUiStore(pinia) // applies theme + locale before first paint
  // Resolve the auth state first so the very first route is already the right one.
  await useAuthStore(pinia).waitReady()
  app.use(router)
  await router.isReady()
  app.mount('#app')
}

void boot()
