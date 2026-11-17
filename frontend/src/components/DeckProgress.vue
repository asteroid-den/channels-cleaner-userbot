<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import type { DeckCounts, FinalDecision } from '@/api/types'
import { useDeckStore } from '@/stores/deck'

const { t } = useI18n()
const deck = useDeckStore()

/**
 * What the bar shows. It follows the store, except while "+1" chips are flying: then it
 * waits for them to land, so the bar grows at the moment the chip hits it.
 */
const copy = (c: DeckCounts): DeckCounts => ({ ...c, by_decision: { ...c.by_decision } })
const shown = ref<DeckCounts>(copy(deck.counts))
watch(
  () => [deck.counts, deck.chipsInFlight] as const,
  () => {
    if (deck.chipsInFlight === 0) shown.value = copy(deck.counts)
  },
  { deep: true },
)

const pulse = ref(false)
const flash = ref(false)
watch(
  () => deck.landed,
  () => {
    shown.value = copy(deck.counts)
    pulse.value = flash.value = false
    requestAnimationFrame(() => (pulse.value = flash.value = true))
  },
)

const decided = computed(() => shown.value.total - shown.value.undecided)
const pct = computed(() => (shown.value.total ? (decided.value / shown.value.total) * 100 : 0))

const SEGMENTS: { id: FinalDecision; cls: string }[] = [
  { id: 'keep', cls: 'bg-success' },
  { id: 'unsubscribe', cls: 'bg-danger' },
  { id: 'mute', cls: 'bg-warn' },
  { id: 'archive', cls: 'bg-accent' },
]
const segments = computed(() =>
  SEGMENTS.map((s) => ({ ...s, n: shown.value.by_decision[s.id] })).filter((s) => s.n > 0),
)
</script>

<template>
  <div class="flex w-full items-center gap-3.5">
    <span
      class="min-w-[5.5rem] origin-right text-right font-mono text-[15px] font-bold tabular-nums"
      :class="pulse ? 'count-bump' : ''"
      @animationend="pulse = false"
    >
      {{ decided }}<span class="font-medium text-faint">/{{ shown.total }}</span>
    </span>

    <div
      class="relative h-2.5 min-w-[140px] flex-1 rounded-full bg-surface-3"
      :title="deck.eta !== null ? t('deck.eta', { m: t('time.minutes', deck.eta) }) : undefined"
      role="progressbar"
      :aria-label="t('deck.progressLabel')"
      :aria-valuemin="0"
      :aria-valuemax="shown.total"
      :aria-valuenow="decided"
    >
      <i
        v-for="tick in [25, 50, 75]"
        :key="tick"
        class="absolute -inset-y-[3px] w-px bg-border-2"
        :style="{ left: `${tick}%` }"
      />
      <div
        class="absolute inset-y-0 left-0 flex overflow-hidden rounded-full transition-[width] duration-500 ease-out"
        :style="{ width: `${pct}%` }"
      >
        <span
          v-for="s in segments"
          :key="s.id"
          class="h-full transition-[flex-grow] duration-500 ease-out"
          :class="s.cls"
          :style="{ flex: `${s.n} 0 0` }"
        />
      </div>
      <span
        data-progress-edge
        class="edge absolute top-1/2 h-[18px] w-[18px] -translate-x-1/2 -translate-y-1/2 rounded-full transition-[left] duration-500 ease-out"
        :class="flash ? 'edge-flash' : ''"
        :style="{ left: `${pct}%` }"
        @animationend="flash = false"
      />
    </div>
  </div>
</template>

<style scoped>
.edge {
  pointer-events: none;
  background: radial-gradient(circle, rgb(var(--ch) / 0.85), rgb(var(--ch) / 0) 70%);
}
.edge-flash {
  animation: edge-flash 0.6s ease-out;
}
@keyframes edge-flash {
  40% {
    scale: 2.6;
  }
}
.count-bump {
  animation: count-bump 0.5s cubic-bezier(0.2, 0.8, 0.2, 1);
}
@keyframes count-bump {
  35% {
    transform: scale(1.2);
    color: rgb(var(--ch-ink));
  }
}
</style>
