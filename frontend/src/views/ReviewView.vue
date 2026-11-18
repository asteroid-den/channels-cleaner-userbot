<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'

import { api } from '@/api/client'
import type { ActionDecision, Channel } from '@/api/types'
import AppIcon, { type IconName } from '@/components/AppIcon.vue'
import ChannelAvatar from '@/components/ChannelAvatar.vue'
import { useHotkeys } from '@/composables/useHotkeys'
import { useApplyStore } from '@/stores/apply'
import { useDeckStore } from '@/stores/deck'
import { useUiStore } from '@/stores/ui'
import { actionErrorKind } from '@/utils/errors'
import { relativeTime } from '@/utils/format'

const { t, locale } = useI18n()
const router = useRouter()
const deck = useDeckStore()
const apply = useApplyStore()
const ui = useUiStore()

const pending = ref<Channel[]>([])
const failed = ref<Channel[]>([])
const loading = ref(true)
const starting = ref(false)

const GROUPS: {
  decision: ActionDecision | 'keep'
  icon: IconName
  label: string
  cls: string
}[] = [
  {
    decision: 'unsubscribe',
    icon: 'x',
    label: 'review.unsubscribe',
    cls: 'bg-danger-soft text-danger',
  },
  { decision: 'mute', icon: 'bellOff', label: 'review.mute', cls: 'bg-warn-soft text-warn' },
  {
    decision: 'archive',
    icon: 'archive',
    label: 'review.archive',
    cls: 'bg-accent-soft text-accent',
  },
  // "keep" only shows up here when it takes back a mute/archive applied earlier
  { decision: 'keep', icon: 'undo', label: 'review.revert', cls: 'bg-surface-3 text-muted' },
]

const grouped = computed(() =>
  GROUPS.map((g) => ({
    ...g,
    items: pending.value.filter((c) => c.decision === g.decision),
  })).filter((g) => g.items.length),
)
const minutes = computed(() => Math.round((pending.value.length * 2.6) / 60))
/** Private channels being left: without an invite link there is no way back. */
const noWayBack = computed(
  () => pending.value.filter((c) => c.decision === 'unsubscribe' && !c.username).length,
)
/** Chats the user runs that they are about to leave: admin rights go with them. */
const leavingRun = computed(
  () => pending.value.filter((c) => c.decision === 'unsubscribe' && c.role === 'admin').length,
)
const leavingOwned = computed(
  () => pending.value.filter((c) => c.decision === 'unsubscribe' && c.role === 'owner').length,
)
const modKey = /Mac|iPhone|iPad/.test(navigator.platform) ? '⌘' : 'Ctrl'

async function load() {
  loading.value = true
  try {
    const [p, f] = await Promise.all([
      api.get<{ items: Channel[] }>('/api/decisions?status=pending'),
      api.get<{ items: Channel[] }>('/api/decisions?status=failed'),
    ])
    pending.value = p.items
    failed.value = f.items
  } finally {
    loading.value = false
  }
}

async function putBack(channel: Channel) {
  try {
    await api.del(`/api/decisions/${channel.id}`)
    pending.value = pending.value.filter((c) => c.id !== channel.id)
    failed.value = failed.value.filter((c) => c.id !== channel.id)
    deck.forget(channel.id)
  } catch (err) {
    ui.toast(String(err))
  }
}

async function retryFailed() {
  await api.post('/api/decisions/retry-failed')
  await load()
}

async function start() {
  starting.value = true
  try {
    await apply.start()
    await router.push('/apply')
  } catch (err) {
    ui.toast(err instanceof Error ? err.message : String(err))
  } finally {
    starting.value = false
  }
}

onMounted(load)

useHotkeys({
  Escape: () => void router.push('/'),
  'mod+Enter': () => {
    if (pending.value.length && !starting.value) void start()
  },
})
</script>

<template>
  <section class="mx-auto flex w-full max-w-2xl flex-1 flex-col px-4 pt-8 pb-32">
    <RouterLink
      to="/"
      class="mb-4 inline-flex w-fit items-center gap-1.5 text-sm text-muted hover:text-text"
    >
      <AppIcon name="arrowLeft" :size="16" />{{ t('review.backToDeck') }}
      <kbd class="font-mono text-[11px] text-faint">Esc</kbd>
    </RouterLink>
    <h1 class="text-3xl font-bold tracking-tight">{{ t('review.title') }}</h1>
    <p class="mt-1 text-muted">{{ t('review.subtitle') }}</p>

    <div v-if="loading" class="mt-8 space-y-3">
      <div v-for="i in 4" :key="i" class="skeleton h-16 w-full rounded-xl" />
    </div>

    <template v-else>
      <p v-if="!pending.length && !failed.length" class="mt-10 text-center text-muted">
        {{ t('review.empty') }}
      </p>

      <div v-for="group in grouped" :key="group.decision" class="mt-8">
        <h2 class="label mb-3 flex items-center gap-2">
          <span class="flex h-6 w-6 items-center justify-center rounded-full" :class="group.cls">
            <AppIcon :name="group.icon" :size="14" :stroke="2.5" />
          </span>
          {{ t(group.label) }}
          <span class="text-muted tabular-nums">· {{ group.items.length }}</span>
        </h2>
        <p class="mb-3 text-[13px] text-muted">{{ t(`review.hints.${group.decision}`) }}</p>
        <TransitionGroup
          tag="ul"
          class="relative overflow-hidden rounded-xl border border-border bg-surface"
          leave-active-class="transition duration-200 absolute inset-x-0"
          leave-to-class="opacity-0 translate-x-6"
          move-class="transition duration-200"
        >
          <li
            v-for="c in group.items"
            :key="c.id"
            class="flex items-center gap-3 border-b border-border bg-surface px-4 py-3 last:border-b-0"
          >
            <ChannelAvatar :id="c.id" :title="c.title" :src="c.avatar_url" :size="40" />
            <div class="min-w-0 flex-1">
              <div class="truncate font-medium">{{ c.title }}</div>
              <div class="truncate text-xs text-muted">
                <span v-if="c.reverts && group.decision !== 'unsubscribe'" class="text-text"
                  >↺ {{ t(`review.reverts.${c.reverts}`) }} ·
                </span>
                <span v-if="c.role !== 'member'" class="font-medium text-text"
                  >{{ t(`deck.role.${c.role}`) }} ·
                </span>
                <span v-if="c.kind === 'supergroup'">{{ t('settings.kind.supergroup') }} · </span>
                <span v-if="c.username">@{{ c.username }} · </span>
                <span
                  v-else
                  class="inline-flex items-center gap-1"
                  :class="group.decision === 'unsubscribe' ? 'font-medium text-danger' : ''"
                  ><AppIcon name="lock" :size="11" />{{
                    group.decision === 'unsubscribe' ? t('review.noWayBack') : t('deck.private')
                  }}</span
                ><span v-if="!c.username"> · </span>
                <span v-if="c.last_post_at">{{ relativeTime(c.last_post_at, locale) }}</span>
                <span v-else>{{ t('deck.neverPosted') }}</span>
                <span v-if="c.unread_count"> · {{ c.unread_count }} {{ t('deck.unread') }}</span>
              </div>
            </div>
            <button class="key shrink-0 !px-2.5 !py-1 !text-xs" @click="putBack(c)">
              {{ t('review.putBack') }}
            </button>
          </li>
        </TransitionGroup>
      </div>

      <div v-if="failed.length" class="mt-8">
        <h2 class="mb-3 flex items-center justify-between text-sm font-medium">
          <span class="flex items-center gap-2 text-danger">
            <AppIcon name="alert" :size="16" />{{ t('review.failedTitle') }} · {{ failed.length }}
          </span>
          <button class="text-accent hover:underline" @click="retryFailed">
            {{ t('results.retryFailed') }}
          </button>
        </h2>
        <ul class="overflow-hidden rounded-xl border border-border bg-surface">
          <li
            v-for="c in failed"
            :key="c.id"
            class="flex items-center gap-3 border-b border-border px-4 py-3 last:border-b-0"
          >
            <ChannelAvatar :id="c.id" :title="c.title" :src="c.avatar_url" :size="36" />
            <div class="min-w-0 flex-1">
              <div class="truncate text-sm font-medium">{{ c.title }}</div>
              <div class="truncate text-xs text-danger" :title="c.error ?? ''">
                {{ t(`review.errors.${actionErrorKind(c.error)}`) }}
              </div>
            </div>
            <button class="key shrink-0 !px-2.5 !py-1 !text-xs" @click="putBack(c)">
              {{ t('review.putBack') }}
            </button>
          </li>
        </ul>
      </div>
    </template>

    <div
      v-if="pending.length"
      class="fixed inset-x-0 bottom-0 z-20 border-t border-border bg-bg/85 px-4 py-4 backdrop-blur-md"
    >
      <div class="mx-auto flex max-w-2xl items-center gap-4">
        <div class="flex-1 text-xs leading-relaxed text-muted">
          <p v-if="noWayBack" class="mb-0.5 flex items-center gap-1.5 font-medium text-danger">
            <AppIcon name="lock" :size="12" />{{ t('review.noWayBackCount', noWayBack) }}
          </p>
          <p v-if="leavingOwned" class="mb-0.5 flex items-center gap-1.5 font-medium text-danger">
            <AppIcon name="alert" :size="12" />{{ t('review.leavingOwned', leavingOwned) }}
          </p>
          <p v-if="leavingRun" class="mb-0.5 flex items-center gap-1.5 font-medium text-danger">
            <AppIcon name="alert" :size="12" />{{ t('review.leavingRun', leavingRun) }}
          </p>
          <p>{{ t('review.pacing', { m: t('time.minutes', minutes) }) }}</p>
        </div>
        <button
          class="flex shrink-0 items-center gap-2 rounded-[10px] bg-danger-strong px-5 py-3 font-semibold text-white shadow-card hover:brightness-110 disabled:opacity-50"
          :disabled="starting"
          @click="start"
        >
          {{ t('review.apply', pending.length) }}
          <kbd class="font-mono text-[11px] font-medium opacity-75">{{ modKey }} ↵</kbd>
        </button>
      </div>
    </div>
  </section>
</template>
