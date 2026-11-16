<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import type { Channel, Decision } from '@/api/types'
import type { HistoryEntry } from '@/stores/deck'

import AppIcon, { type IconName } from './AppIcon.vue'
import ChannelCard from './ChannelCard.vue'

const props = defineProps<{ items: Channel[]; returning: HistoryEntry | null }>()
const emit = defineEmits<{ decide: [decision: Decision] }>()
const { t } = useI18n()

const SWIPE_X = 110
const SWIPE_Y = 130
const FLY_MS = 340

const visible = computed(() => props.items.slice(0, 3))
const dx = ref(0)
const dy = ref(0)
const dragging = ref(false)
const flying = ref<Decision | null>(null)
const entering = ref(false)
let start = { x: 0, y: 0, t: 0 }
let pointerId: number | null = null

const busy = computed(() => flying.value !== null || entering.value)

function flyTarget(decision: Decision): string {
  const w = window.innerWidth
  const h = window.innerHeight
  switch (decision) {
    case 'keep':
      return `translate(${w}px, ${dy.value - 40}px) rotate(28deg)`
    case 'unsubscribe':
      return `translate(${-w}px, ${dy.value - 40}px) rotate(-28deg)`
    case 'skip':
      return `translate(0, ${h}px) rotate(4deg)`
    default:
      return `translate(0, ${-h}px) scale(0.9)`
  }
}

const topStyle = computed(() => {
  if (flying.value) {
    return {
      transform: flyTarget(flying.value),
      transition: `transform ${FLY_MS}ms cubic-bezier(.4,.1,.6,1), opacity ${FLY_MS}ms`,
      opacity: flying.value === 'mute' || flying.value === 'archive' ? 0 : 1,
    }
  }
  if (entering.value) {
    return { transform: flyTarget(props.returning?.decision ?? 'keep'), transition: 'none' }
  }
  return {
    transform: `translate(${dx.value}px, ${dy.value}px) rotate(${dx.value / 18}deg)`,
    transition: dragging.value ? 'none' : 'transform 0.35s cubic-bezier(.2,.9,.3,1.2)',
  }
})

function depthStyle(depth: number) {
  // Cards behind grow toward the front as the top card is dragged away.
  const pull = Math.min(1, Math.hypot(dx.value, dy.value) / 220) * (flying.value ? 1 : 0.6)
  const level = Math.max(0, depth - (flying.value ? 1 : pull))
  return {
    transform: `translateY(${level * 16}px) scale(${1 - level * 0.05})`,
    opacity: depth >= 2 && !flying.value ? 0.6 : 1,
    transition: 'transform 0.3s ease, opacity 0.3s ease',
  }
}

/** Which stamp to show and how strongly (0..1). */
const stamp = computed<{ decision: Decision; strength: number } | null>(() => {
  if (flying.value) return { decision: flying.value, strength: 1 }
  if (Math.abs(dx.value) > Math.abs(dy.value)) {
    if (dx.value > 12) return { decision: 'keep', strength: Math.min(1, dx.value / SWIPE_X) }
    if (dx.value < -12)
      return { decision: 'unsubscribe', strength: Math.min(1, -dx.value / SWIPE_X) }
  } else if (dy.value > 12) {
    return { decision: 'skip', strength: Math.min(1, dy.value / SWIPE_Y) }
  }
  return null
})

const STAMPS: Record<Decision, { label: string; icon: IconName; cls: string; pos: string }> = {
  keep: {
    label: 'deck.stampKeep',
    icon: 'check',
    cls: 'border-success text-success',
    pos: 'left-5 top-[86px] -rotate-6',
  },
  unsubscribe: {
    label: 'deck.stampLeave',
    icon: 'x',
    cls: 'border-danger text-danger',
    pos: 'right-5 top-[86px] rotate-6',
  },
  skip: {
    label: 'deck.stampSkip',
    icon: 'skip',
    cls: 'border-muted text-muted',
    pos: 'left-1/2 bottom-10 -translate-x-1/2',
  },
  mute: {
    label: 'actions.mute',
    icon: 'bellOff',
    cls: 'border-warn text-warn',
    pos: 'left-1/2 top-1/3 -translate-x-1/2',
  },
  archive: {
    label: 'actions.archive',
    icon: 'archive',
    cls: 'border-accent text-accent',
    pos: 'left-1/2 top-1/3 -translate-x-1/2',
  },
}

function onPointerDown(e: PointerEvent) {
  if (busy.value || e.button !== 0) return
  if ((e.target as HTMLElement).closest('a,button')) return
  pointerId = e.pointerId
  ;(e.currentTarget as HTMLElement).setPointerCapture(e.pointerId)
  dragging.value = true
  start = { x: e.clientX, y: e.clientY, t: performance.now() }
}

function onPointerMove(e: PointerEvent) {
  if (!dragging.value || e.pointerId !== pointerId) return
  dx.value = e.clientX - start.x
  dy.value = Math.max(-40, e.clientY - start.y) // only "down" is meaningful vertically
}

function onPointerUp(e: PointerEvent) {
  if (!dragging.value || e.pointerId !== pointerId) return
  dragging.value = false
  pointerId = null
  const elapsed = Math.max(1, performance.now() - start.t)
  const vx = dx.value / elapsed // px/ms
  const vy = dy.value / elapsed
  if (dx.value > SWIPE_X || (vx > 0.6 && dx.value > 40)) fling('keep')
  else if (dx.value < -SWIPE_X || (vx < -0.6 && dx.value < -40)) fling('unsubscribe')
  else if (dy.value > SWIPE_Y || (vy > 0.6 && dy.value > 50)) fling('skip')
  else {
    dx.value = 0
    dy.value = 0
  }
}

function fling(decision: Decision): boolean {
  if (busy.value || !visible.value.length) return false
  flying.value = decision
  setTimeout(() => {
    // Reset and shift the list in the same tick: one render, no flicker on the next card.
    flying.value = null
    dx.value = 0
    dy.value = 0
    emit('decide', decision)
  }, FLY_MS)
  return true
}

// After an undo the restored card flies back in from where it left.
watch(
  () => props.returning,
  async (entry) => {
    if (!entry || visible.value[0]?.id !== entry.channel.id) return
    entering.value = true
    dx.value = 0
    dy.value = 0
    await nextTick()
    requestAnimationFrame(() =>
      requestAnimationFrame(() => {
        entering.value = false
      }),
    )
  },
)

defineExpose({ fling, busy })
</script>

<template>
  <div class="relative h-full w-full">
    <div
      v-for="(channel, depth) in visible"
      :key="channel.id"
      class="absolute inset-0"
      :style="{ zIndex: 10 - depth, ...(depth === 0 ? {} : depthStyle(depth)) }"
      :aria-hidden="depth > 0"
    >
      <div
        v-if="depth === 0"
        class="h-full w-full touch-none select-none"
        :class="dragging ? 'cursor-grabbing' : 'cursor-grab'"
        :style="topStyle"
        @pointerdown="onPointerDown"
        @pointermove="onPointerMove"
        @pointerup="onPointerUp"
        @pointercancel="onPointerUp"
      >
        <ChannelCard :channel="channel" />
        <div
          v-if="stamp"
          class="pointer-events-none absolute z-10 flex items-center gap-2 rounded-lg border-2 bg-surface-2/90 px-3 py-1.5 font-mono text-lg font-bold tracking-wide uppercase backdrop-blur-sm"
          :class="[STAMPS[stamp.decision].cls, STAMPS[stamp.decision].pos]"
          :style="{ opacity: stamp.strength }"
        >
          <AppIcon :name="STAMPS[stamp.decision].icon" :size="22" :stroke="3" />
          {{ t(STAMPS[stamp.decision].label) }}
        </div>
      </div>
      <ChannelCard v-else :channel="channel" />
    </div>
  </div>
</template>
