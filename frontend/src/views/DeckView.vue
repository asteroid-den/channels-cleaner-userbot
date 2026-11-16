<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, useTemplateRef } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'

import type { Decision } from '@/api/types'
import AppIcon from '@/components/AppIcon.vue'
import ChannelAvatar from '@/components/ChannelAvatar.vue'
import PulseChart from '@/components/PulseChart.vue'
import SwipeDeck from '@/components/SwipeDeck.vue'
import { useChannelColor } from '@/composables/useChannelColor'
import { useHotkeys } from '@/composables/useHotkeys'
import { useApplyStore } from '@/stores/apply'
import { useDeckStore } from '@/stores/deck'
import { compactNumber, relativeTime } from '@/utils/format'

const { t, locale } = useI18n()
const deck = useDeckStore()
const apply = useApplyStore()
const router = useRouter()
const swiper = useTemplateRef<InstanceType<typeof SwipeDeck>>('swiper')

useChannelColor(computed(() => deck.current))

onMounted(async () => {
  deck.watchSync()
  await deck.load()
  if (apply.running) void router.push('/apply')
})
onBeforeUnmount(() => deck.unwatchSync())

// --- actions -------------------------------------------------------------------------------
const pressed = ref<string | null>(null)
const stamps: number[] = []

function flash(key: string) {
  pressed.value = key
  setTimeout(() => (pressed.value = pressed.value === key ? null : pressed.value), 140)
}

function act(decision: Decision) {
  if (!deck.current) return
  flash(decision)
  if (swiper.value?.fling(decision)) stamps.push(Date.now())
}

async function undo() {
  if (swiper.value?.busy) return
  flash('undo')
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

// --- derived ---------------------------------------------------------------------------------
const showSync = computed(() => deck.syncing && deck.items.length === 0)
const empty = computed(() => deck.loaded && !deck.syncing && deck.items.length === 0)
const progress = computed(() =>
  deck.counts.total ? ((deck.position - 1) / deck.counts.total) * 100 : 0,
)
const history = computed(() => deck.history.slice(-14).reverse())
const queue = computed(() => deck.items.slice(1, 8))
const keptInSession = computed(() => deck.history.filter((h) => h.decision === 'keep').length)

/** Remaining time at the user's own pace (median gap between the last decisions). */
const eta = computed(() => {
  void deck.history.length // recompute after each decision
  if (stamps.length < 4) return null
  const gaps = stamps
    .slice(-11)
    .map((ts, i, arr) => (i ? ts - arr[i - 1]! : 0))
    .slice(1)
    .sort((a, b) => a - b)
  const median = Math.min(gaps[Math.floor(gaps.length / 2)]!, 30_000)
  return Math.round((median * deck.counts.undecided) / 60_000)
})

const TAG_CLASS: Record<Decision, string> = {
  keep: 'bg-success-soft text-success',
  unsubscribe: 'bg-danger-soft text-danger',
  skip: 'bg-warn-soft text-warn',
  mute: 'bg-warn-soft text-warn',
  archive: 'bg-accent-soft text-accent',
}

const KEYS: { id: Decision; kbd: string; label: string; cls?: string; kbdAfter?: boolean }[] = [
  { id: 'unsubscribe', kbd: '←', label: 'actions.unsubscribe', cls: 'text-danger' },
  { id: 'skip', kbd: '↓', label: 'actions.skip' },
  { id: 'mute', kbd: 'M', label: 'actions.mute' },
  { id: 'archive', kbd: 'A', label: 'actions.archive' },
  { id: 'keep', kbd: '→', label: 'actions.keep', cls: 'text-success', kbdAfter: true },
]
</script>

<template>
  <!-- gathering the list -->
  <section
    v-if="showSync"
    class="flex flex-1 flex-col items-center justify-center gap-4 text-center"
  >
    <div class="font-mono text-6xl font-bold tabular-nums">{{ deck.sync?.fetched ?? 0 }}</div>
    <div>
      <h1 class="text-lg font-semibold">{{ t('sync.title') }}</h1>
      <p class="mt-1 text-muted">{{ t('sync.found', deck.sync?.fetched ?? 0) }}</p>
    </div>
    <div class="skeleton h-1 w-64" />
    <p v-if="deck.sync?.flood_wait" class="text-sm text-warn">
      {{ t('sync.floodWait', { s: deck.sync.flood_wait }) }}
    </p>
  </section>

  <!-- everything decided -->
  <section
    v-else-if="empty"
    class="flex flex-1 flex-col items-center justify-center gap-5 text-center"
  >
    <div
      class="flex h-16 w-16 items-center justify-center rounded-2xl bg-success-soft text-success"
    >
      <AppIcon name="check" :size="30" :stroke="2.5" />
    </div>
    <div>
      <h1 class="text-2xl font-bold">{{ t('deck.emptyTitle') }}</h1>
      <p class="mt-1 text-muted">
        {{ deck.counts.total ? t('deck.emptyText') : t('deck.emptyNoChannels') }}
      </p>
      <p v-if="deck.sync?.error" class="mt-3 text-sm text-danger">
        {{ t('sync.error', { msg: deck.sync.error }) }}
      </p>
    </div>
    <div class="flex gap-2">
      <button v-if="deck.history.length" class="key" @click="undo">
        <kbd>⌫</kbd>{{ t('actions.undo') }}
      </button>
      <RouterLink v-if="deck.counts.pending" to="/review" class="key">
        {{ t('deck.applyCta', { n: deck.counts.pending }) }}<kbd>↵</kbd>
      </RouterLink>
      <RouterLink v-else to="/results" class="key">{{ t('account.results') }}</RouterLink>
    </div>
  </section>

  <!-- the deck -->
  <section
    v-else-if="deck.loaded"
    class="grid min-h-0 flex-1 grid-cols-1 xl:grid-cols-[280px_minmax(0,1fr)_320px]"
  >
    <!-- history -->
    <aside
      class="hidden min-h-0 overflow-hidden border-r border-border bg-surface p-[18px] xl:block"
    >
      <div class="label mb-3 flex items-center justify-between">
        <span>{{ t('deck.historyTitle') }}</span>
        <button
          class="font-mono tracking-normal normal-case hover:text-text disabled:opacity-40"
          :disabled="!deck.history.length"
          @click="undo"
        >
          ⌫ {{ t('actions.undo').toLowerCase() }}
        </button>
      </div>
      <TransitionGroup
        tag="ul"
        enter-from-class="opacity-0 -translate-y-2"
        enter-active-class="transition duration-300"
        move-class="transition duration-300"
      >
        <li
          v-for="h in history"
          :key="`${h.channel.id}-${h.decision}`"
          class="flex items-center gap-2.5 border-b border-dashed border-border py-2"
        >
          <ChannelAvatar
            :id="h.channel.id"
            :title="h.channel.title"
            :src="h.channel.avatar_url"
            :size="28"
            rounded="8px"
          />
          <span class="min-w-0 flex-1 truncate">{{ h.channel.title }}</span>
          <span class="tag" :class="TAG_CLASS[h.decision]">{{ t(`deck.tags.${h.decision}`) }}</span>
        </li>
      </TransitionGroup>
      <p v-if="!deck.history.length" class="text-[13px] text-faint">
        {{ t('deck.historyEmpty') }}
      </p>
    </aside>

    <!-- centre -->
    <div class="glow relative flex min-h-0 flex-col items-center overflow-hidden px-6 pt-5 pb-6">
      <div class="relative flex w-full max-w-[480px] items-center gap-3 text-[12.5px] text-muted">
        <span class="font-mono tabular-nums">{{ deck.position }}/{{ deck.counts.total }}</span>
        <div class="h-1 flex-1 overflow-hidden rounded bg-border">
          <div
            class="h-full rounded bg-text transition-[width] duration-300"
            :style="{ width: `${progress}%` }"
          />
        </div>
        <span v-if="deck.syncing" class="flex items-center gap-1">
          <AppIcon name="refresh" :size="12" class="animate-spin" />{{ t('deck.syncing') }}
        </span>
        <span v-else-if="eta !== null">{{ t('deck.eta', { m: t('time.minutes', eta) }) }}</span>
      </div>

      <div
        class="relative mt-4 h-[min(610px,calc(100vh-200px))] min-h-[480px] w-full max-w-[480px]"
      >
        <SwipeDeck
          ref="swiper"
          :items="deck.items"
          :returning="deck.returning"
          @decide="deck.decide"
        />
      </div>

      <div class="relative mt-5 flex flex-wrap justify-center gap-2">
        <button
          v-for="k in KEYS"
          :key="k.id"
          class="key"
          :class="[k.cls, pressed === k.id ? 'pressed' : '']"
          @click="act(k.id)"
        >
          <kbd v-if="!k.kbdAfter">{{ k.kbd }}</kbd>{{ t(k.label)
          }}<kbd v-if="k.kbdAfter">{{ k.kbd }}</kbd>
        </button>
      </div>
    </div>

    <!-- queue + summary -->
    <aside
      class="hidden min-h-0 flex-col gap-[18px] overflow-hidden border-l border-border bg-surface p-[18px] xl:flex"
    >
      <div>
        <div class="label mb-3">{{ t('deck.queueTitle') }}</div>
        <TransitionGroup
          tag="ul"
          move-class="transition duration-300"
          enter-from-class="opacity-0"
          enter-active-class="transition duration-300"
        >
          <li
            v-for="c in queue"
            :key="c.id"
            class="flex items-center gap-2.5 border-b border-dashed border-border py-2"
          >
            <ChannelAvatar
              :id="c.id"
              :title="c.title"
              :src="c.avatar_url"
              :size="28"
              rounded="8px"
            />
            <div class="min-w-0 flex-1">
              <div class="truncate">{{ c.title }}</div>
              <div class="truncate text-[11.5px] text-faint">
                {{ c.last_post_at ? relativeTime(c.last_post_at, locale) : t('deck.neverPosted') }}
                · {{ compactNumber(c.unread_count, locale) }} {{ t('deck.unread') }}
              </div>
            </div>
            <div class="w-16 shrink-0 text-muted">
              <PulseChart v-if="c.pulse" :weeks="c.pulse.weeks" :height="18" mini />
              <div v-else class="skeleton h-[18px] w-full opacity-60" />
            </div>
          </li>
        </TransitionGroup>
      </div>

      <dl class="grid grid-cols-2 gap-3 rounded-xl border border-border p-3.5">
        <div>
          <dd class="font-mono text-[22px] font-bold text-danger">{{ deck.counts.pending }}</dd>
          <dt class="text-[11.5px] text-faint">{{ t('deck.toApply') }}</dt>
        </div>
        <div>
          <dd class="font-mono text-[22px] font-bold text-success">{{ keptInSession }}</dd>
          <dt class="text-[11.5px] text-faint">{{ t('deck.keptSession') }}</dt>
        </div>
        <div>
          <dd class="font-mono text-[22px] font-bold">
            {{ deck.counts.total - deck.counts.undecided }}
          </dd>
          <dt class="text-[11.5px] text-faint">{{ t('deck.decided') }}</dt>
        </div>
        <div>
          <dd class="font-mono text-[22px] font-bold">{{ deck.counts.undecided }}</dd>
          <dt class="text-[11.5px] text-faint">{{ t('deck.left') }}</dt>
        </div>
      </dl>

      <button
        class="rounded-[10px] bg-text px-3 py-3 font-semibold text-bg transition-opacity disabled:opacity-35"
        :disabled="!deck.counts.pending"
        @click="review"
      >
        {{ t('deck.applyCta', { n: deck.counts.pending }) }} ↵
      </button>
    </aside>

    <!-- narrow screens: floating review button instead of the side panel -->
    <button
      v-if="deck.counts.pending"
      class="fixed right-5 bottom-5 z-20 rounded-[10px] bg-text px-4 py-3 font-semibold text-bg shadow-card xl:hidden"
      @click="review"
    >
      {{ t('deck.applyCta', { n: deck.counts.pending }) }} ↵
    </button>
  </section>

  <div v-else class="flex flex-1 items-center justify-center">
    <div class="h-8 w-8 animate-spin rounded-full border-2 border-border border-t-text" />
  </div>
</template>

<style scoped>
.glow::before {
  content: '';
  position: absolute;
  inset: 0;
  pointer-events: none;
  background: radial-gradient(
    60% 45% at 50% 32%,
    rgb(var(--ch) / var(--glow-strength)),
    transparent 70%
  );
  transition: background 0.6s;
}
</style>
