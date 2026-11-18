<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'

import { useAuthStore } from '@/stores/auth'
import { useDeckStore } from '@/stores/deck'
import { useUiStore } from '@/stores/ui'

import AccountMenu from './AccountMenu.vue'
import AppIcon from './AppIcon.vue'
import DeckProgress from './DeckProgress.vue'
import SummaryPill from './SummaryPill.vue'

const { t } = useI18n()
const ui = useUiStore()
const auth = useAuthStore()
const deck = useDeckStore()
const route = useRoute()

const onDeck = computed(() => auth.authorized && route.name === 'deck' && deck.loaded)
</script>

<template>
  <header
    class="relative z-30 flex h-14 shrink-0 items-center gap-4 border-b border-border bg-surface px-5"
  >
    <RouterLink
      to="/"
      :aria-label="t('app.name')"
      class="flex shrink-0 items-center gap-2.5 font-display text-[15px] font-bold"
    >
      <span
        class="h-[22px] w-[22px] rounded-md bg-gradient-to-br from-ch to-ch2 transition-colors duration-500"
      />
      <span :class="onDeck ? 'hidden xl:inline' : ''">{{ t('app.name') }}</span>
    </RouterLink>
    <span v-if="ui.mock" class="tag bg-warn-soft text-warn">MOCK</span>

    <div
      v-if="auth.authorized && route.name === 'deck'"
      class="flex shrink-0 overflow-hidden rounded-lg border border-border-2 text-[12.5px]"
      role="group"
      :aria-label="t('header.kind')"
    >
      <button
        v-for="k in ['channel', 'supergroup'] as const"
        :key="k"
        class="relative border-r border-border-2 px-3 py-1.5 transition-colors last:border-r-0"
        :class="deck.kind === k ? 'bg-text text-bg' : 'text-muted hover:text-text'"
        :aria-pressed="deck.kind === k"
        @click="deck.setKind(k)"
      >
        {{ t(k === 'channel' ? 'header.kindChannel' : 'header.kindGroup') }}
        <span
          v-if="deck.kind !== k && deck.counts.pending_other > 0"
          class="absolute top-1 right-1 h-1.5 w-1.5 rounded-full bg-accent"
          :title="t('header.pendingElsewhere')"
        />
      </button>
    </div>

    <div
      v-if="auth.authorized && route.name === 'deck'"
      class="flex shrink-0 overflow-hidden rounded-lg border border-border-2 text-[12.5px]"
      role="group"
      :aria-label="t('header.sort')"
    >
      <button
        v-for="mode in ['dead', 'unread'] as const"
        :key="mode"
        class="border-r border-border-2 px-3 py-1.5 transition-colors"
        :title="t(mode === 'dead' ? 'header.sortDead' : 'header.sortUnread')"
        :class="deck.prefs.sort === mode ? 'bg-text text-bg' : 'text-muted hover:text-text'"
        :aria-pressed="deck.prefs.sort === mode"
        @click="deck.setSort(mode)"
      >
        {{ t(mode === 'dead' ? 'header.sortDeadShort' : 'header.sortUnreadShort') }}
      </button>
      <button
        class="px-2.5 transition-colors"
        :class="deck.prefs.reverse ? 'bg-text text-bg' : 'text-muted hover:text-text'"
        :title="t('header.reverse')"
        :aria-label="t('header.reverse')"
        :aria-pressed="deck.prefs.reverse"
        @click="deck.toggleReverse()"
      >
        <AppIcon name="arrows" :size="14" />
      </button>
    </div>

    <div class="flex min-w-0 flex-1 justify-center px-2">
      <div v-if="onDeck" class="w-full max-w-[540px]"><DeckProgress /></div>
    </div>
    <SummaryPill v-if="onDeck" />

    <button
      class="rounded-lg border border-border-2 px-2.5 py-1.5 font-mono text-[11.5px] text-muted uppercase hover:text-text"
      :title="t('header.language')"
      :aria-label="`${t('header.language')}: ${ui.locale.toUpperCase()}`"
      @click="ui.toggleLocale()"
    >
      {{ ui.locale }}
    </button>
    <button
      class="flex h-[30px] w-[30px] items-center justify-center rounded-lg border border-border-2 text-muted hover:text-text"
      :title="t('header.theme')"
      :aria-label="t('header.theme')"
      @click="ui.toggleTheme()"
    >
      <AppIcon :name="ui.theme === 'dark' ? 'sun' : 'moon'" :size="15" />
    </button>
    <AccountMenu v-if="auth.authorized" />
  </header>
</template>
