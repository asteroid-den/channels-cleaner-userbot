<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, useTemplateRef } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'

import type { Decision } from '@/api/types'
import AppIcon, { type IconName } from '@/components/AppIcon.vue'
import FilmStrip from '@/components/FilmStrip.vue'
import SwipeDeck from '@/components/SwipeDeck.vue'
import { useHotkeys } from '@/composables/useHotkeys'
import { useApplyStore } from '@/stores/apply'
import { useDeckStore } from '@/stores/deck'

const { t } = useI18n()
const deck = useDeckStore()
const apply = useApplyStore()
const router = useRouter()
const swiper = useTemplateRef<InstanceType<typeof SwipeDeck>>('swiper')

onMounted(async () => {
  deck.watchSync()
  await deck.load()
  // A job may still be running from before a page reload: show it.
  if (apply.running) void router.push('/apply')
})
onBeforeUnmount(() => deck.unwatchSync())

function act(decision: Decision) {
  if (!deck.current) return
  swiper.value?.fling(decision)
}

async function undo() {
  if (swiper.value?.busy) return
  await deck.undo()
}

function review() {
  if (deck.counts.pending > 0) void router.push('/review')
}

useHotkeys({
  ArrowLeft: () => act('unsubscribe'),
  ArrowRight: () => act('keep'),
  ArrowDown: () => act('skip'),
  m: () => act('mute'),
  a: () => act('archive'),
  'mod+z': () => void undo(),
  Backspace: () => void undo(),
  Enter: review,
})

const showSync = computed(() => deck.syncing && deck.items.length === 0)
const empty = computed(() => deck.loaded && !deck.syncing && deck.items.length === 0)

const small: { decision: Decision | 'undo'; icon: IconName; label: string; kbd: string }[] = [
  { decision: 'undo', icon: 'undo', label: 'actions.undo', kbd: 'Ctrl Z' },
  { decision: 'skip', icon: 'skip', label: 'actions.skip', kbd: '↓' },
  { decision: 'mute', icon: 'bellOff', label: 'actions.mute', kbd: 'M' },
  { decision: 'archive', icon: 'archive', label: 'actions.archive', kbd: 'A' },
]
</script>

<template>
  <section class="flex flex-1 flex-col items-center px-4 pb-6">
    <!-- syncing -->
    <div v-if="showSync" class="flex flex-1 flex-col items-center justify-center gap-5 text-center">
      <div class="relative h-20 w-20">
        <div class="absolute inset-0 animate-ping rounded-3xl bg-accent-soft" />
        <div
          class="relative flex h-20 w-20 items-center justify-center rounded-3xl bg-accent text-white"
        >
          <AppIcon name="refresh" :size="30" class="animate-spin [animation-duration:2s]" />
        </div>
      </div>
      <div>
        <h1 class="text-xl font-semibold">{{ t('sync.title') }}</h1>
        <p class="mt-1 text-muted tabular-nums">{{ t('sync.found', deck.sync?.fetched ?? 0) }}</p>
        <p v-if="deck.sync?.flood_wait" class="mt-3 text-sm text-warn">
          {{ t('sync.floodWait', { s: deck.sync.flood_wait }) }}
        </p>
      </div>
    </div>

    <!-- all done -->
    <div
      v-else-if="empty"
      class="flex flex-1 flex-col items-center justify-center gap-5 text-center"
    >
      <div
        class="flex h-20 w-20 items-center justify-center rounded-3xl bg-success-soft text-success"
      >
        <AppIcon name="check" :size="36" :stroke="2.5" />
      </div>
      <div>
        <h1 class="text-2xl font-semibold">{{ t('deck.emptyTitle') }}</h1>
        <p class="mt-1 text-muted">
          {{ deck.counts.total ? t('deck.emptyText') : t('deck.emptyNoChannels') }}
        </p>
        <p v-if="deck.sync?.error" class="mt-3 text-sm text-danger">
          {{ t('sync.error', { msg: deck.sync.error }) }}
        </p>
      </div>
      <div class="flex gap-3">
        <button
          v-if="deck.history.length"
          class="flex items-center gap-2 rounded-full border border-border bg-surface px-5 py-2.5 hover:bg-surface-2"
          @click="undo"
        >
          <AppIcon name="undo" :size="16" />{{ t('actions.undo') }}
        </button>
        <RouterLink
          v-if="deck.counts.pending"
          to="/review"
          class="flex items-center gap-2 rounded-full bg-accent px-5 py-2.5 font-medium text-white"
        >
          {{ t('deck.reviewCount', { n: deck.counts.pending })
          }}<AppIcon name="arrowRight" :size="16" />
        </RouterLink>
        <RouterLink
          v-else
          to="/results"
          class="flex items-center gap-2 rounded-full border border-border bg-surface px-5 py-2.5 hover:bg-surface-2"
        >
          <AppIcon name="chart" :size="16" />{{ t('account.results') }}
        </RouterLink>
      </div>
    </div>

    <!-- deck -->
    <template v-else-if="deck.loaded">
      <div class="flex w-full max-w-3xl items-center justify-center gap-4">
        <FilmStrip :items="deck.items" :history="deck.history" />
      </div>
      <div class="mt-1 flex items-center gap-3 text-sm text-muted tabular-nums">
        <span>{{ t('deck.position', { pos: deck.position, total: deck.counts.total }) }}</span>
        <span v-if="deck.syncing" class="flex items-center gap-1 text-xs">
          <AppIcon name="refresh" :size="12" class="animate-spin" />{{ t('deck.syncing') }}
        </span>
      </div>
      <div class="mt-1 h-[3px] w-full max-w-[440px] overflow-hidden rounded-full bg-surface-2">
        <div
          class="h-full rounded-full bg-accent transition-[width] duration-300"
          :style="{
            width: `${deck.counts.total ? ((deck.position - 1) / deck.counts.total) * 100 : 0}%`,
          }"
        />
      </div>

      <div
        class="relative mt-5 h-[min(580px,calc(100vh-290px))] min-h-[420px] w-full max-w-[440px]"
      >
        <SwipeDeck
          ref="swiper"
          :items="deck.items"
          :returning="deck.returning"
          @decide="deck.decide"
        />
      </div>

      <!-- actions -->
      <div class="mt-8 flex items-end gap-3 sm:gap-5">
        <button
          class="group flex flex-col items-center gap-1.5"
          :aria-label="t('actions.unsubscribe')"
          @click="act('unsubscribe')"
        >
          <span
            class="flex h-16 w-16 items-center justify-center rounded-full bg-danger text-white shadow-card transition-transform group-hover:scale-105 group-active:scale-95"
          >
            <AppIcon name="x" :size="30" :stroke="2.6" />
          </span>
          <span class="text-xs text-muted"
            >{{ t('actions.unsubscribe') }} <kbd class="opacity-60">←</kbd></span
          >
        </button>

        <button
          v-for="b in small"
          :key="b.decision"
          class="group flex flex-col items-center gap-1.5 disabled:opacity-35"
          :disabled="b.decision === 'undo' && !deck.history.length"
          :aria-label="t(b.label)"
          @click="b.decision === 'undo' ? undo() : act(b.decision)"
        >
          <span
            class="flex h-12 w-12 items-center justify-center rounded-full border border-border bg-surface transition-transform group-hover:scale-105 group-hover:bg-surface-2 group-active:scale-95"
          >
            <AppIcon :name="b.icon" :size="20" />
          </span>
          <span class="text-[11px] text-muted">{{ t(b.label) }}</span>
        </button>

        <button
          class="group flex flex-col items-center gap-1.5"
          :aria-label="t('actions.keep')"
          @click="act('keep')"
        >
          <span
            class="flex h-16 w-16 items-center justify-center rounded-full bg-success text-white shadow-card transition-transform group-hover:scale-105 group-active:scale-95"
          >
            <AppIcon name="check" :size="30" :stroke="2.6" />
          </span>
          <span class="text-xs text-muted"
            >{{ t('actions.keep') }} <kbd class="opacity-60">→</kbd></span
          >
        </button>
      </div>

      <Transition
        enter-from-class="opacity-0 translate-y-4"
        enter-active-class="transition duration-300"
        leave-to-class="opacity-0 translate-y-4"
        leave-active-class="transition duration-200"
      >
        <button
          v-if="deck.counts.pending"
          class="fixed right-6 bottom-6 z-20 flex items-center gap-2 rounded-full bg-accent py-3 pr-4 pl-5 text-sm font-medium text-white shadow-card transition hover:brightness-110"
          @click="review"
        >
          {{ t('deck.reviewCount', { n: deck.counts.pending }) }}
          <AppIcon name="arrowRight" :size="16" />
          <kbd class="rounded-md bg-white/20 px-1.5 py-0.5 text-[10px] font-normal">Enter</kbd>
        </button>
      </Transition>
    </template>

    <div v-else class="flex flex-1 items-center justify-center">
      <div class="h-10 w-10 animate-spin rounded-full border-2 border-border border-t-accent" />
    </div>
  </section>
</template>
