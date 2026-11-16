<script setup lang="ts">
import { useNow } from '@vueuse/core'
import { computed, onBeforeUnmount, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'

import type { ActionDecision } from '@/api/types'
import AppIcon, { type IconName } from '@/components/AppIcon.vue'
import ChannelAvatar from '@/components/ChannelAvatar.vue'
import { useApplyStore } from '@/stores/apply'
import { useDeckStore } from '@/stores/deck'

const { t } = useI18n()
const apply = useApplyStore()
const deck = useDeckStore()
const now = useNow({ interval: 250 })

const VISIBLE = 14

onMounted(() => apply.connect())
onBeforeUnmount(() => {
  apply.disconnect()
  deck.clear() // the deck must be reloaded after channels were left
})

const state = computed(() => apply.state)
const queue = computed(() =>
  state.value.items.filter((i) => i.status === 'queued' || i.status === 'running'),
)
const shown = computed(() => queue.value.slice(0, VISIBLE))
const hidden = computed(() => Math.max(0, queue.value.length - VISIBLE))
const failedItems = computed(() => state.value.items.filter((i) => i.status === 'failed'))
const current = computed(() => state.value.items.find((i) => i.status === 'running') ?? null)
const finished = computed(() => ['finished', 'cancelled', 'error'].includes(state.value.status))
const floodLeft = computed(() =>
  state.value.flood_wait_until
    ? Math.max(0, Math.ceil(state.value.flood_wait_until - now.value.getTime() / 1000))
    : null,
)

const BADGE: Record<ActionDecision, { icon: IconName; cls: string; verb: string }> = {
  unsubscribe: { icon: 'x', cls: 'bg-danger', verb: 'actions.unsubscribe' },
  mute: { icon: 'bellOff', cls: 'bg-warn', verb: 'actions.mute' },
  archive: { icon: 'archive', cls: 'bg-accent', verb: 'actions.archive' },
}

const avatarUrl = (id: number, hasPhoto: boolean) =>
  hasPhoto ? `/api/channels/${id}/avatar` : null
</script>

<template>
  <section class="flex flex-1 flex-col items-center px-4 pt-6 pb-12">
    <div class="w-full max-w-3xl">
      <div class="flex items-end justify-between gap-4">
        <div>
          <h1 class="text-3xl font-semibold tracking-tight">
            {{
              state.status === 'finished'
                ? t('apply.finished')
                : state.status === 'cancelled'
                  ? t('apply.cancelled')
                  : t('apply.title')
            }}
          </h1>
          <p class="mt-1 h-5 truncate text-sm text-muted">
            <template v-if="current">
              {{ t(BADGE[current.decision].verb) }} ·
              <span class="text-text">{{ current.title }}</span>
            </template>
          </p>
        </div>
        <div class="text-right text-2xl font-semibold tabular-nums">
          {{ t('apply.progress', { done: state.done + state.failed, total: state.total }) }}
        </div>
      </div>

      <div class="mt-4 h-2 overflow-hidden rounded-full bg-surface-2">
        <div
          class="h-full rounded-full transition-[width] duration-500 ease-out"
          :class="state.failed ? 'bg-gradient-to-r from-success to-warn' : 'bg-success'"
          :style="{ width: `${apply.progress * 100}%` }"
        />
      </div>

      <Transition
        enter-from-class="opacity-0 -translate-y-1"
        enter-active-class="transition"
        leave-to-class="opacity-0"
        leave-active-class="transition"
      >
        <p
          v-if="floodLeft !== null"
          class="mt-4 flex items-center gap-2 rounded-xl bg-warn-soft px-4 py-2.5 text-sm text-warn"
        >
          <AppIcon name="clock" :size="16" />{{ t('apply.floodWait', { s: floodLeft }) }}
        </p>
      </Transition>
      <p
        v-if="state.status === 'error'"
        class="mt-4 rounded-xl bg-danger-soft px-4 py-2.5 text-sm text-danger"
      >
        {{ t('apply.error') }}
      </p>
    </div>

    <!-- the deck of avatars, in the order they will be processed -->
    <div class="mt-14 flex h-48 w-full max-w-4xl items-center justify-center [perspective:900px]">
      <TransitionGroup
        tag="div"
        class="flex items-center pl-12"
        move-class="transition-transform duration-500 ease-out"
        leave-active-class="transition-all duration-500 ease-out"
        leave-to-class="opacity-0 -translate-y-10 scale-75 !w-0 !ml-0"
      >
        <div
          v-for="(item, i) in shown"
          :key="item.channel_id"
          class="relative -ml-12 w-[104px] shrink-0 [transform-style:preserve-3d]"
          :style="{ zIndex: VISIBLE - i }"
        >
          <div
            class="relative transition-transform duration-500 ease-out"
            :style="{
              transform:
                item.status === 'running'
                  ? 'translateY(-14px) rotateY(0deg) scale(1.12)'
                  : `rotateY(38deg) translateZ(${-i * 4}px)`,
            }"
          >
            <div
              class="overflow-hidden rounded-[22px] shadow-card ring-1 ring-black/10"
              :class="item.status === 'running' ? 'ring-4 !ring-accent' : ''"
            >
              <ChannelAvatar
                :id="item.channel_id"
                :title="item.title"
                :src="avatarUrl(item.channel_id, item.has_photo)"
                :size="104"
                rounded="22px"
              />
            </div>
            <span
              class="absolute -right-1.5 -bottom-1.5 flex h-7 w-7 items-center justify-center rounded-full text-white ring-[3px] ring-bg"
              :class="BADGE[item.decision].cls"
            >
              <AppIcon :name="BADGE[item.decision].icon" :size="14" :stroke="3" />
            </span>
            <span
              v-if="item.status === 'running'"
              class="absolute -top-2 -left-2 h-6 w-6 animate-spin rounded-full border-[3px] border-accent/30 border-t-accent"
            />
          </div>
        </div>
      </TransitionGroup>
      <span
        v-if="hidden"
        class="ml-6 shrink-0 rounded-full border border-border bg-surface px-3 py-1.5 text-sm text-muted tabular-nums"
        >+{{ hidden }}</span
      >
      <div v-if="finished && !queue.length" class="flex flex-col items-center gap-3 text-success">
        <div class="flex h-20 w-20 items-center justify-center rounded-3xl bg-success-soft">
          <AppIcon name="check" :size="38" :stroke="2.5" />
        </div>
      </div>
    </div>

    <div v-if="failedItems.length" class="mt-6 w-full max-w-3xl">
      <p class="mb-2 text-sm text-danger">{{ t('apply.failed', { n: failedItems.length }) }}</p>
      <TransitionGroup
        tag="div"
        class="flex flex-wrap gap-2"
        enter-from-class="opacity-0 translate-y-3"
        enter-active-class="transition duration-300"
      >
        <div
          v-for="item in failedItems"
          :key="item.channel_id"
          class="flex items-center gap-2 rounded-full border border-danger/40 bg-danger-soft py-1 pr-3 pl-1 text-xs"
          :title="item.error ?? ''"
        >
          <ChannelAvatar
            :id="item.channel_id"
            :title="item.title"
            :src="avatarUrl(item.channel_id, item.has_photo)"
            :size="24"
          />
          <span class="max-w-40 truncate">{{ item.title }}</span>
        </div>
      </TransitionGroup>
    </div>

    <div class="mt-10 flex gap-3">
      <button
        v-if="apply.running"
        class="rounded-full border border-border bg-surface px-5 py-2.5 text-sm hover:bg-surface-2 disabled:opacity-50"
        :disabled="apply.cancelling"
        @click="apply.cancel()"
      >
        {{ apply.cancelling ? t('apply.cancelling') : t('apply.cancel') }}
      </button>
      <template v-else>
        <RouterLink
          to="/"
          class="flex items-center gap-2 rounded-full border border-border bg-surface px-5 py-2.5 text-sm hover:bg-surface-2"
        >
          <AppIcon name="arrowLeft" :size="16" />{{ t('results.backToDeck') }}
        </RouterLink>
        <RouterLink
          to="/results"
          class="flex items-center gap-2 rounded-full bg-accent px-5 py-2.5 text-sm font-medium text-white"
        >
          {{ t('apply.seeResults') }}<AppIcon name="arrowRight" :size="16" />
        </RouterLink>
      </template>
    </div>
  </section>
</template>
