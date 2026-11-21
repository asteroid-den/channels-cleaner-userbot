import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { api, subscribe } from '@/api/client'
import type { AuthState } from '@/api/types'

const INITIAL: AuthState = {
  status: 'starting',
  user: null,
  qr_url: null,
  qr_expires_at: null,
  password_hint: null,
  phone: null,
  error: null,
}

export const useAuthStore = defineStore('auth', () => {
  const state = ref<AuthState>({ ...INITIAL })
  const ready = ref(false)
  let unsubscribe: (() => void) | null = null

  const authorized = computed(() => state.value.status === 'authorized')

  function set(next: AuthState) {
    state.value = next
    ready.value = next.status !== 'starting'
  }

  function connect() {
    if (unsubscribe) return
    unsubscribe = subscribe('/api/auth/events', {
      snapshot: (data: AuthState) => set(data),
      state: (data: AuthState) => set(data),
    })
  }

  async function refresh() {
    set(await api.get<AuthState>('/api/auth/state'))
  }

  async function waitReady() {
    for (;;) {
      try {
        await refresh()
        if (ready.value) return
      } catch {
        /* backend still starting */
      }
      await new Promise((resolve) => setTimeout(resolve, 400))
    }
  }

  const startQr = async () => set(await api.post<AuthState>('/api/auth/qr/start'))
  const sendCode = async (phone: string) =>
    set(await api.post<AuthState>('/api/auth/phone/send-code', { phone }))
  const signIn = async (code: string) =>
    set(await api.post<AuthState>('/api/auth/phone/sign-in', { code }))
  const checkPassword = async (password: string) =>
    set(await api.post<AuthState>('/api/auth/password', { password }))
  const cancel = async () => set(await api.post<AuthState>('/api/auth/cancel'))
  const logout = async (wipeData: boolean) =>
    set(await api.post<AuthState>('/api/auth/logout', { wipe_data: wipeData }))

  return {
    state,
    ready,
    authorized,
    connect,
    refresh,
    waitReady,
    startQr,
    sendCode,
    signIn,
    checkPassword,
    cancel,
    logout,
  }
})
