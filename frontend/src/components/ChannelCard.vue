<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import type { Channel } from '@/api/types'
import { activityOf, colorFor, compactNumber, fullDate, relativeTime } from '@/utils/format'

import AppIcon from './AppIcon.vue'
import ChannelAvatar from './ChannelAvatar.vue'

const props = defineProps<{ channel: Channel }>()
const { t, locale } = useI18n()

const activity = computed(() => activityOf(props.channel.last_post_at))
const activityClass = computed(
  () =>
    ({
      fresh: 'bg-success-soft text-success',
      slow: 'bg-accent-soft text-accent',
      stale: 'bg-warn-soft text-warn',
      dead: 'bg-danger-soft text-danger',
    })[activity.value],
)
const lastPost = computed(() =>
  props.channel.last_post_at ? relativeTime(props.channel.last_post_at, locale.value) : null,
)
const members = computed(() =>
  props.channel.members_count === null
    ? null
    : compactNumber(props.channel.members_count, locale.value),
)
const mediaLabel = computed(() =>
  props.channel.last_post_media ? t(`deck.media.${props.channel.last_post_media}`) : null,
)
</script>

<template>
  <article
    class="relative flex h-full w-full flex-col overflow-hidden rounded-[28px] border border-border bg-surface shadow-card"
  >
    <!-- tinted header band -->
    <div
      class="pointer-events-none absolute inset-x-0 top-0 h-36 opacity-25"
      :style="{ background: `linear-gradient(180deg, ${colorFor(channel.id)}, transparent)` }"
    />

    <div class="relative flex flex-col gap-4 px-6 pt-6">
      <div class="flex items-start justify-between gap-3">
        <ChannelAvatar
          :id="channel.id"
          :title="channel.title"
          :src="channel.avatar_url"
          :size="84"
          rounded="26px"
        />
        <span class="rounded-full px-2.5 py-1 text-xs font-medium" :class="activityClass">
          {{ t(`deck.activity.${activity}`) }}
        </span>
      </div>

      <div>
        <h2 class="line-clamp-2 text-2xl leading-tight font-semibold tracking-tight">
          {{ channel.title }}
        </h2>
        <div class="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-muted">
          <a
            v-if="channel.link"
            :href="channel.link"
            target="_blank"
            rel="noopener"
            class="text-accent hover:underline"
            @pointerdown.stop
            >@{{ channel.username }}</a
          >
          <span v-else class="inline-flex items-center gap-1"
            ><AppIcon name="lock" :size="12" />{{ t('deck.private') }}</span
          >
          <span
            v-if="channel.is_archived"
            class="inline-flex items-center gap-1 rounded-md bg-surface-2 px-1.5 py-0.5 text-xs"
            ><AppIcon name="archive" :size="12" />{{ t('deck.archived') }}</span
          >
          <span
            v-if="channel.is_muted"
            class="inline-flex items-center gap-1 rounded-md bg-surface-2 px-1.5 py-0.5 text-xs"
            ><AppIcon name="bellOff" :size="12" />{{ t('deck.muted') }}</span
          >
        </div>
      </div>

      <dl class="grid grid-cols-3 gap-2 text-center">
        <div class="rounded-2xl bg-surface-2 px-2 py-2.5">
          <dt class="sr-only">{{ t('deck.subscribers', 2) }}</dt>
          <dd class="text-base font-semibold">
            <span v-if="members">{{ members }}</span>
            <span v-else-if="!channel.full_loaded" class="skeleton mx-auto block h-5 w-10" />
            <span v-else>—</span>
          </dd>
          <div class="mt-0.5 text-[11px] text-muted">
            {{ t('deck.subscribers', channel.members_count ?? 0) }}
          </div>
        </div>
        <div class="rounded-2xl bg-surface-2 px-2 py-2.5">
          <dd
            class="text-base font-semibold"
            :class="channel.unread_count > 0 ? 'text-accent' : ''"
          >
            {{ compactNumber(channel.unread_count, locale) }}
          </dd>
          <div class="mt-0.5 text-[11px] text-muted">{{ t('deck.unread') }}</div>
        </div>
        <div class="rounded-2xl bg-surface-2 px-2 py-2.5">
          <dd
            class="truncate text-base font-semibold"
            :title="channel.last_post_at ? fullDate(channel.last_post_at, locale) : ''"
          >
            {{ lastPost ?? '—' }}
          </dd>
          <div class="mt-0.5 text-[11px] text-muted">{{ t('deck.lastPost') }}</div>
        </div>
      </dl>
    </div>

    <div class="relative flex min-h-0 flex-1 flex-col gap-4 px-6 pt-4 pb-6">
      <div class="min-h-[3.75rem] text-sm leading-relaxed">
        <p v-if="channel.about" class="line-clamp-3 whitespace-pre-line text-muted">
          {{ channel.about }}
        </p>
        <div v-else-if="!channel.full_loaded" class="space-y-2">
          <div class="skeleton h-3.5 w-full" />
          <div class="skeleton h-3.5 w-11/12" />
          <div class="skeleton h-3.5 w-2/3" />
        </div>
        <p v-else class="text-faint italic">{{ t('deck.noAbout') }}</p>
      </div>

      <section
        class="flex min-h-0 flex-1 flex-col overflow-hidden rounded-2xl border border-border bg-surface-2/60"
      >
        <header
          class="flex items-center justify-between px-4 pt-3 pb-2 text-[11px] font-medium tracking-wide text-muted uppercase"
        >
          <span>{{ t('deck.lastPost') }}</span>
          <span v-if="mediaLabel" class="inline-flex items-center gap-1 normal-case">
            <AppIcon name="image" :size="12" />{{ mediaLabel }}
          </span>
        </header>
        <div v-if="channel.last_post_at" class="flex min-h-0 flex-1 gap-3 px-4 pb-4">
          <img
            v-if="channel.thumb_url"
            :src="channel.thumb_url"
            alt=""
            class="h-24 w-24 shrink-0 rounded-xl object-cover"
            draggable="false"
            loading="lazy"
            @error="($event.target as HTMLImageElement).style.display = 'none'"
          />
          <p class="line-clamp-5 min-w-0 text-sm leading-relaxed whitespace-pre-line">
            {{ channel.last_post_text ?? mediaLabel ?? '…' }}
          </p>
        </div>
        <p v-else class="px-4 pb-4 text-sm text-faint italic">{{ t('deck.neverPosted') }}</p>
      </section>
    </div>
  </article>
</template>
