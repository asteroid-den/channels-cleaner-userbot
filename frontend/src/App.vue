<script setup lang="ts">
import { onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import AppHeader from '@/components/AppHeader.vue'
import ToastStack from '@/components/ToastStack.vue'
import { useAuthStore } from '@/stores/auth'
import { useUiStore } from '@/stores/ui'

const auth = useAuthStore()
const ui = useUiStore()
const router = useRouter()
const route = useRoute()

onMounted(() => {
  void ui.loadHealth()
  auth.connect()
})

// Keep the route in line with the auth state (login elsewhere, logout, revoked session…).
watch(
  () => [auth.ready, auth.authorized] as const,
  ([ready, authorized]) => {
    if (!ready) return
    if (!authorized && route.name !== 'login') void router.replace({ name: 'login' })
    if (authorized && (route.name === 'login' || !route.name)) void router.replace({ name: 'deck' })
  },
  { immediate: true },
)
</script>

<template>
  <div class="flex min-h-full flex-col">
    <AppHeader />
    <main class="flex flex-1 flex-col">
      <RouterView v-slot="{ Component }">
        <Transition
          mode="out-in"
          enter-from-class="opacity-0 translate-y-2"
          leave-to-class="opacity-0"
          enter-active-class="transition duration-200 ease-out"
          leave-active-class="transition duration-150"
        >
          <component :is="Component" />
        </Transition>
      </RouterView>
    </main>
    <ToastStack />
  </div>
</template>
