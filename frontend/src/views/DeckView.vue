<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, useTemplateRef } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'

import type { Decision } from '@/api/types'
import AppIcon from '@/components/AppIcon.vue'
import SwipeDeck from '@/components/SwipeDeck.vue'
import { useChannelColor } from '@/composables/useChannelColor'
import { useHotkeys } from '@/composables/useHotkeys'
import { useApplyStore } from '@/stores/apply'
import { useDeckStore } from '@/stores/deck'

const { t } = useI18n()
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

function flash(key: string) {
  pressed.value = key
  setTimeout(() => (pressed.value = pressed.value === key ? null : pressed.value), 140)
}

function act(decision: Decision) {
  if (!deck.current) return
  flash(decision)
  swiper.value?.fling(decision)
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

// --- "+1" chip: flies from the leaving card into the progress bar in the header -------------
const CHIP_CLASS: Record<Exclude<Decision, 'skip'>, string> = {
  keep: 'bg-success',
  unsubscribe: 'bg-danger-strong',
  mute: 'bg-warn',
  archive: 'bg-accent',
}
const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)')

function onFlinging(decision: Decision, from: DOMRect) {
  if (decision === 'skip') return // "later" doesn't move the deck forward
  const target = document.querySelector('[data-progress-edge]')?.getBoundingClientRect()
  deck.chipsInFlight += 1
  const land = () => {
    deck.chipsInFlight = Math.max(0, deck.chipsInFlight - 1)
    deck.landed += 1
  }
  if (!target || reduceMotion.matches) return void setTimeout(land, 200)

  const chip = document.createElement('div')
  chip.className = `chip ${CHIP_CLASS[decision]}`
  chip.textContent = '+1'
  chip.setAttribute('aria-hidden', 'true')
  document.body.appendChild(chip)
  const x0 = from.left + from.width / 2 - 18
  const y0 = from.top + 36
  const x1 = target.left + target.width / 2 - 18
  const y1 = target.top + target.height / 2 - 12
  const mx = (x0 + x1) / 2 + (decision === 'keep' ? 70 : -70)
  const my = Math.min(y0, y1) + 20
  chip.animate(
    [
      { transform: `translate(${x0}px, ${y0}px) scale(.6)`, opacity: 0 },
      { transform: `translate(${x0}px, ${y0 - 30}px) scale(1.1)`, opacity: 1, offset: 0.2 },
      { transform: `translate(${mx}px, ${my}px) scale(1)`, opacity: 1, offset: 0.6 },
      { transform: `translate(${x1}px, ${y1}px) scale(.5)`, opacity: 0.3 },
    ],
    { duration: 650, easing: 'cubic-bezier(.5,0,.4,1)' },
  ).onfinish = () => {
    chip.remove()
    land()
  }
}

// --- side zones: click to decide, hover to preview ------------------------------------------
function zoneMove(e: PointerEvent) {
  const el = e.currentTarget as HTMLElement
  const r = el.getBoundingClientRect()
  el.style.setProperty('--mx', `${e.clientX - r.left}px`)
  el.style.setProperty('--my', `${e.clientY - r.top}px`)
}
function zoneEnter(decision: 'keep' | 'unsubscribe') {
  if (swiper.value && !swiper.value.busy) swiper.value.preview = decision
}
function zoneLeave() {
  if (swiper.value) swiper.value.preview = null
}

// --- derived ---------------------------------------------------------------------------------
const showSync = computed(() => deck.syncing && deck.items.length === 0)
const empty = computed(() => deck.loaded && !deck.syncing && deck.items.length === 0)

const KEYS: {
  id: Decision
  kbd: string
  shortcut: string
  label: string
  cls?: string
  kbdAfter?: boolean
}[] = [
  {
    id: 'unsubscribe',
    kbd: '←',
    shortcut: 'ArrowLeft',
    label: 'actions.unsubscribe',
    cls: 'text-danger',
  },
  { id: 'skip', kbd: '↓', shortcut: 'ArrowDown', label: 'actions.skip' },
  { id: 'mute', kbd: 'M', shortcut: 'M', label: 'actions.mute' },
  { id: 'archive', kbd: 'A', shortcut: 'A', label: 'actions.archive' },
  {
    id: 'keep',
    kbd: '→',
    shortcut: 'ArrowRight',
    label: 'actions.keep',
    cls: 'text-success',
    kbdAfter: true,
  },
]

const ZONES = [
  { id: 'unsubscribe', label: 'deck.zoneLeave', cls: 'zone-l left-0', hint: 'right-9' },
  { id: 'keep', label: 'deck.zoneKeep', cls: 'zone-r right-0', hint: 'left-9' },
] as const
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
  <section v-else-if="deck.loaded" class="glow relative flex min-h-0 flex-1 flex-col items-center">
    <h1 class="sr-only">{{ t('app.name') }}</h1>
    <p class="sr-only" aria-live="polite">
      <template v-if="deck.current">
        {{ deck.current.title }} ·
        {{ t('deck.position', { pos: deck.position, total: deck.counts.total }) }}
      </template>
    </p>

    <div class="relative w-full flex-1 pt-8">
      <!-- clickable side zones: the same as swiping toward them -->
      <button
        v-for="z in ZONES"
        :key="z.id"
        tabindex="-1"
        aria-hidden="true"
        class="zone absolute inset-y-0 w-[calc(50%-260px)]"
        :class="z.cls"
        @pointermove="zoneMove"
        @pointerenter="zoneEnter(z.id)"
        @pointerleave="zoneLeave"
        @click="act(z.id)"
      >
        <span class="zone-hint" :class="z.hint">
          <kbd v-if="z.id === 'unsubscribe'">←</kbd>{{ t(z.label)
          }}<kbd v-if="z.id === 'keep'">→</kbd>
        </span>
      </button>

      <div class="relative mx-auto h-[min(560px,calc(100vh-220px))] min-h-[420px] w-[460px]">
        <SwipeDeck
          ref="swiper"
          :items="deck.items"
          :returning="deck.returning"
          @decide="deck.decide"
          @flinging="onFlinging"
        />
      </div>
    </div>

    <div class="relative z-10 flex flex-wrap justify-center gap-2 pt-4 pb-7">
      <button
        v-for="k in KEYS"
        :key="k.id"
        class="key"
        :class="[k.cls, pressed === k.id ? 'pressed' : '']"
        :aria-keyshortcuts="k.shortcut"
        @click="act(k.id)"
      >
        <kbd v-if="!k.kbdAfter">{{ k.kbd }}</kbd>{{ t(k.label)
        }}<kbd v-if="k.kbdAfter">{{ k.kbd }}</kbd>
      </button>
    </div>
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
    50% 45% at 50% 38%,
    rgb(var(--ch) / var(--glow-strength)),
    transparent 70%
  );
}

.zone {
  overflow: hidden;
  cursor: pointer;
}
.zone::before {
  content: '';
  position: absolute;
  inset: 0;
  opacity: 0;
  transition: opacity 0.2s;
  background: radial-gradient(
    420px circle at var(--mx, 50%) var(--my, 50%),
    var(--zone-color),
    transparent 70%
  );
}
.zone-l {
  --zone-color: color-mix(in srgb, var(--danger) 20%, transparent);
}
.zone-r {
  --zone-color: color-mix(in srgb, var(--success) 18%, transparent);
}
.zone:hover::before {
  opacity: 1;
}
.zone-hint {
  position: absolute;
  top: 42%;
  display: flex;
  align-items: center;
  gap: 0.6rem;
  font-family: var(--font-display);
  font-size: 16px;
  font-weight: 600;
  opacity: 0;
  transition:
    opacity 0.2s,
    translate 0.25s;
}
.zone-l .zone-hint {
  color: var(--danger);
  translate: 10px 0;
}
.zone-r .zone-hint {
  color: var(--success);
  translate: -10px 0;
}
.zone:hover .zone-hint {
  opacity: 1;
  translate: 0 0;
}
.zone-hint kbd {
  font-family: var(--font-mono);
  font-size: 11px;
  border: 1px solid currentColor;
  border-radius: 5px;
  padding: 0 0.35rem;
  opacity: 0.7;
}
</style>
