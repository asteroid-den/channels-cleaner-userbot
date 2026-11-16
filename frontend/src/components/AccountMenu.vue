<script setup lang="ts">
import { onClickOutside } from '@vueuse/core'
import { ref, useTemplateRef } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'

import { useAuthStore } from '@/stores/auth'
import { useDeckStore } from '@/stores/deck'
import { useUiStore } from '@/stores/ui'

import AppIcon, { type IconName } from './AppIcon.vue'

const { t } = useI18n()
const auth = useAuthStore()
const deck = useDeckStore()
const ui = useUiStore()
const router = useRouter()

const open = ref(false)
const root = useTemplateRef<HTMLElement>('root')
onClickOutside(root, () => (open.value = false))

async function run(action: () => Promise<unknown> | unknown) {
  open.value = false
  try {
    await action()
  } catch (err) {
    ui.toast(t('login.errors.generic', { msg: err instanceof Error ? err.message : String(err) }))
  }
}

const items: { icon: IconName; label: string; danger?: boolean; action: () => unknown }[] = [
  { icon: 'refresh', label: 'account.resync', action: () => deck.resync() },
  { icon: 'chart', label: 'account.results', action: () => router.push('/results') },
  { icon: 'undo', label: 'account.resetKeeps', action: () => deck.reset('keep') },
  {
    icon: 'trash',
    label: 'account.resetAll',
    action: () => confirm(t('account.resetConfirm')) && deck.reset(null),
  },
  {
    icon: 'logout',
    label: 'account.logout',
    action: () => confirm(t('account.logoutConfirm')) && logout(false),
  },
  {
    icon: 'logout',
    label: 'account.logoutWipe',
    danger: true,
    action: () => confirm(t('account.logoutWipeConfirm')) && logout(true),
  },
]

async function logout(wipe: boolean) {
  await auth.logout(wipe)
  deck.clear()
}
</script>

<template>
  <div ref="root" class="relative">
    <button
      class="flex h-[30px] items-center gap-2 rounded-lg border border-border-2 px-2.5 text-[12.5px] text-muted hover:text-text"
      :aria-label="t('account.menu')"
      :aria-expanded="open"
      @click="open = !open"
    >
      <AppIcon name="user" :size="14" />
      <span class="max-w-32 truncate">{{ auth.state.user?.first_name }}</span>
    </button>
    <Transition
      enter-from-class="opacity-0 -translate-y-1"
      leave-to-class="opacity-0 -translate-y-1"
      enter-active-class="transition duration-150"
      leave-active-class="transition duration-100"
    >
      <div
        v-if="open"
        class="absolute right-0 z-40 mt-2 w-72 overflow-hidden rounded-xl border border-border-2 bg-surface p-1 shadow-card"
        role="menu"
      >
        <div class="px-3 py-2 text-xs text-muted">
          {{ auth.state.user?.first_name }} {{ auth.state.user?.last_name ?? '' }}
          <span v-if="auth.state.user?.username">· @{{ auth.state.user.username }}</span>
        </div>
        <button
          v-for="item in items"
          :key="item.label"
          role="menuitem"
          class="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left text-sm hover:bg-surface-2"
          :class="item.danger ? 'text-danger' : ''"
          @click="run(item.action)"
        >
          <AppIcon :name="item.icon" :size="16" class="shrink-0 opacity-80" />
          {{ t(item.label) }}
        </button>
      </div>
    </Transition>
  </div>
</template>
