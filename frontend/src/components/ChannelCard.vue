<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import type { Channel } from '@/api/types'
import {
  activityOf,
  ageShort,
  compactNumber,
  fullDate,
  pulseAxis,
  relativeTime,
} from '@/utils/format'

import AppIcon from './AppIcon.vue'
import ChannelAvatar from './ChannelAvatar.vue'
import PulseChart from './PulseChart.vue'

const props = defineProps<{ channel: Channel }>()
const { t, locale } = useI18n()

const activity = computed(() => activityOf(props.channel.last_post_at))
const statusClass = computed(
  () =>
    ({
      fresh: 'bg-success-soft text-success',
      slow: 'bg-accent-soft text-accent',
      stale: 'bg-warn-soft text-warn',
      dead: 'bg-danger-soft text-danger',
    })[activity.value],
)
const members = computed(() =>
  props.channel.members_count === null
    ? null
    : compactNumber(props.channel.members_count, locale.value),
)
const mediaLabel = computed(() =>
  props.channel.last_post_media ? t(`deck.media.${props.channel.last_post_media}`) : null,
)
const axis = computed(() => pulseAxis(locale.value))
const pulseUnknown = computed(() => props.channel.pulse?.weeks.some((w) => w === null) ?? false)
const pulseSilent = computed(
  () => !!props.channel.pulse && props.channel.pulse.weeks.every((w) => w === 0),
)
const perWeek = computed(() =>
  new Intl.NumberFormat(locale.value, { maximumFractionDigits: 1 }).format(
    props.channel.pulse?.per_week ?? 0,
  ),
)
</script>

<template>
  <article
    class="relative flex h-full w-full flex-col overflow-hidden rounded-[18px] border border-border-2 bg-surface-2 shadow-card"
  >
    <div class="h-1 shrink-0 bg-gradient-to-r from-ch to-ch2" />

    <div class="flex min-h-0 flex-1 flex-col gap-4 px-6 pt-5 pb-5">
      <!-- head -->
      <div class="flex items-start gap-4">
        <ChannelAvatar
          :id="channel.id"
          :title="channel.title"
          :src="channel.avatar_url"
          :size="64"
          rounded="16px"
        />
        <div class="min-w-0 flex-1">
          <h2 class="line-clamp-2 text-[23px] leading-[1.15] font-bold tracking-[-0.01em]">
            {{ channel.title }}
          </h2>
          <div class="mt-1.5 flex flex-wrap items-center gap-x-1.5 text-[13px] text-muted">
            <a
              v-if="channel.link"
              :href="channel.link"
              target="_blank"
              rel="noopener"
              class="hover:text-text hover:underline"
              @pointerdown.stop
              >@{{ channel.username }}</a
            >
            <span v-else class="inline-flex items-center gap-1"
              ><AppIcon name="lock" :size="11" />{{ t('deck.private') }}</span
            >
            <template v-if="channel.is_muted"><span>·</span>{{ t('deck.muted') }}</template>
            <template v-if="channel.is_archived"><span>·</span>{{ t('deck.archived') }}</template>
          </div>
        </div>
        <span class="tag shrink-0" :class="statusClass">{{ t(`deck.activity.${activity}`) }}</span>
      </div>

      <!-- figures -->
      <dl class="grid grid-cols-3 rounded-xl border border-border">
        <div class="px-3.5 py-2.5">
          <dd class="font-mono text-[19px] font-bold">
            <span v-if="members">{{ members }}</span>
            <span v-else-if="!channel.full_loaded" class="skeleton block h-6 w-16" />
            <span v-else class="text-faint">—</span>
          </dd>
          <dt class="text-[11.5px] text-faint">
            {{ t('deck.subscribers', channel.members_count ?? 0) }}
          </dt>
        </div>
        <div class="border-l border-border px-3.5 py-2.5">
          <dd
            class="font-mono text-[19px] font-bold"
            :class="channel.unread_count > 0 ? 'text-ch' : ''"
          >
            {{ compactNumber(channel.unread_count, locale) }}
          </dd>
          <dt class="text-[11.5px] text-faint">{{ t('deck.unread') }}</dt>
        </div>
        <div class="border-l border-border px-3.5 py-2.5">
          <dd
            class="truncate font-mono text-[19px] font-bold"
            :title="channel.last_post_at ? fullDate(channel.last_post_at, locale) : ''"
          >
            {{ channel.last_post_at ? ageShort(channel.last_post_at, locale) : '—' }}
          </dd>
          <dt class="text-[11.5px] text-faint">{{ t('deck.sinceLast') }}</dt>
        </div>
      </dl>

      <!-- pulse -->
      <div class="rounded-xl border border-border px-3.5 pt-3 pb-2">
        <div class="mb-2.5 flex items-center justify-between gap-3 text-[11.5px] text-faint">
          <span>{{ t('deck.pulseTitle') }}</span>
          <span v-if="channel.pulse" class="truncate">
            <b class="font-semibold text-text">{{ perWeek }}</b>
            {{ t('deck.perWeek', { n: '' }).trim() }}
          </span>
          <span v-else-if="!channel.full_loaded" class="skeleton h-3.5 w-24" />
        </div>
        <div class="relative text-ch">
          <PulseChart v-if="channel.pulse" :weeks="channel.pulse.weeks" :height="54" />
          <span
            v-if="pulseSilent"
            class="absolute inset-0 flex items-center justify-center text-[12.5px] text-faint"
            >{{ t('deck.pulseEmpty') }}</span
          >
          <div v-if="!channel.pulse" class="skeleton h-[54px] w-full" />
        </div>
        <div class="mt-1.5 flex justify-between font-mono text-[10.5px] text-faint">
          <span>{{ axis[0] }}</span>
          <span v-if="pulseUnknown">{{
            t('deck.pulseTruncated', { n: channel.pulse?.sample ?? 0 })
          }}</span>
          <span v-else>{{ axis[1] }}</span>
          <span>{{ axis[2] }}</span>
        </div>
      </div>

      <!-- about -->
      <div class="min-h-[2.6rem] text-[14px] leading-relaxed text-muted">
        <p v-if="channel.about" class="line-clamp-2 whitespace-pre-line">{{ channel.about }}</p>
        <div v-else-if="!channel.full_loaded" class="space-y-2 pt-1">
          <div class="skeleton h-3 w-full" />
          <div class="skeleton h-3 w-2/3" />
        </div>
        <p v-else class="text-faint italic">{{ t('deck.noAbout') }}</p>
      </div>

      <!-- last post -->
      <div class="post mt-auto flex min-h-0 gap-3 rounded-xl p-3">
        <img
          v-if="channel.thumb_url"
          :src="channel.thumb_url"
          alt=""
          class="h-[76px] w-[76px] shrink-0 rounded-[10px] object-cover"
          draggable="false"
          loading="lazy"
          @error="($event.target as HTMLImageElement).style.display = 'none'"
        />
        <div class="min-w-0">
          <div class="text-[11.5px] text-faint">
            {{ t('deck.lastPost') }}
            <template v-if="channel.last_post_at">
              · {{ relativeTime(channel.last_post_at, locale) }}</template
            >
            <template v-if="mediaLabel"> · {{ mediaLabel }}</template>
          </div>
          <p
            v-if="channel.last_post_at"
            class="mt-1 line-clamp-3 text-[14px] leading-snug whitespace-pre-line"
          >
            {{ channel.last_post_text ?? mediaLabel ?? '…' }}
          </p>
          <p v-else class="mt-1 text-[14px] text-faint italic">{{ t('deck.neverPosted') }}</p>
        </div>
      </div>
    </div>
  </article>
</template>

<style scoped>
.post {
  background: color-mix(in srgb, var(--text) 4%, transparent);
}
</style>
