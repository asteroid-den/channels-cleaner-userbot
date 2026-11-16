<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'

import { useAuthStore } from '@/stores/auth'
import { useDeckStore } from '@/stores/deck'
import { useUiStore } from '@/stores/ui'

import AccountMenu from './AccountMenu.vue'
import AppIcon from './AppIcon.vue'

const { t } = useI18n()
const ui = useUiStore()
const auth = useAuthStore()
const deck = useDeckStore()
const route = useRoute()
</script>

<template>
  <header class="relative z-30 flex items-center gap-3 px-5 py-4">
    <RouterLink to="/" class="flex items-center gap-2.5 font-semibold tracking-tight">
      <span
        class="flex h-8 w-8 items-center justify-center rounded-xl bg-accent text-white shadow-card"
      >
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <rect x="4" y="3" width="11" height="15" rx="2.5" fill="currentColor" opacity=".45" />
          <rect
            x="9"
            y="6"
            width="11"
            height="15"
            rx="2.5"
            fill="currentColor"
            transform="rotate(8 14.5 13.5)"
          />
        </svg>
      </span>
      <span class="hidden sm:inline">{{ t('app.name') }}</span>
    </RouterLink>
    <span
      v-if="ui.mock"
      class="rounded-full bg-warn-soft px-2 py-0.5 text-xs font-medium text-warn"
      >{{ t('common.mockMode') }}</span
    >

    <div
      v-if="auth.authorized && route.name === 'deck'"
      class="mx-auto flex items-center gap-1 rounded-full border border-border bg-surface p-1 text-sm"
      role="group"
      :aria-label="t('header.sort')"
    >
      <button
        v-for="mode in ['dead', 'unread'] as const"
        :key="mode"
        class="rounded-full px-3 py-1.5 transition-colors"
        :class="deck.prefs.sort === mode ? 'bg-accent text-white' : 'text-muted hover:text-text'"
        :aria-pressed="deck.prefs.sort === mode"
        @click="deck.setSort(mode)"
      >
        {{ t(mode === 'dead' ? 'header.sortDead' : 'header.sortUnread') }}
      </button>
      <button
        class="ml-0.5 flex h-8 w-8 items-center justify-center rounded-full transition-colors"
        :class="deck.prefs.reverse ? 'bg-accent-soft text-accent' : 'text-muted hover:text-text'"
        :title="t('header.reverse')"
        :aria-label="t('header.reverse')"
        :aria-pressed="deck.prefs.reverse"
        @click="deck.toggleReverse()"
      >
        <AppIcon name="arrows" :size="16" />
      </button>
    </div>
    <div v-else class="mx-auto" />

    <div class="flex items-center gap-2">
      <button
        class="flex h-9 items-center gap-1.5 rounded-full border border-border bg-surface px-3 text-xs font-semibold tracking-wide uppercase hover:bg-surface-2"
        :title="t('header.language')"
        @click="ui.toggleLocale()"
      >
        <AppIcon name="globe" :size="14" />
        {{ ui.locale }}
      </button>
      <button
        class="flex h-9 w-9 items-center justify-center rounded-full border border-border bg-surface hover:bg-surface-2"
        :title="t('header.theme')"
        :aria-label="t('header.theme')"
        @click="ui.toggleTheme()"
      >
        <AppIcon :name="ui.theme === 'dark' ? 'sun' : 'moon'" :size="16" />
      </button>
      <AccountMenu v-if="auth.authorized" />
    </div>
  </header>
</template>
