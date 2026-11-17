<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import type { Channel } from '@/api/types'
import { ageShort, compactNumber, fullDate, pulseAxis, relativeTime } from '@/utils/format'
import { verdictOf } from '@/utils/verdict'

import AppIcon from './AppIcon.vue'
import ChannelAvatar from './ChannelAvatar.vue'
import PulseChart from './PulseChart.vue'

const props = defineProps<{ channel: Channel; stacked?: boolean }>()
const { t, locale } = useI18n()

/** Compact figures ("18,7 тыс.") take the plural form of a round number, not of the raw count. */
const pluralCount = (n: number) => (n >= 1000 ? 1000 : n)

const verdict = computed(() => verdictOf(props.channel))
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
/** The chart only earns its place when there is some activity to show. */
const showChart = computed(
  () =>
    verdict.value?.kind === 'rate' || (verdict.value?.kind === 'since' && !verdict.value.silent),
)
const rate = computed(() =>
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
    <!-- cards behind the top one only peek out at the bottom: keep that strip clean -->
    <div
      v-if="stacked"
      class="pointer-events-none absolute inset-x-0 bottom-0 z-10 h-10 bg-surface-2"
    />

    <div data-card-body class="flex flex-col gap-4 px-6 pt-5 pb-5">
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
      </div>

      <!-- verdict: the one figure that decides, plus the supporting facts -->
      <div class="rounded-xl border border-border px-4 pt-3.5 pb-3">
        <div class="grid grid-cols-[auto_minmax(0,1fr)] items-center gap-x-5">
          <div class="min-w-[7.5rem]">
            <template v-if="verdict">
              <div
                class="font-mono text-[44px] leading-none font-bold tracking-[-0.03em] whitespace-nowrap text-ch-ink"
                :title="channel.last_post_at ? fullDate(channel.last_post_at, locale) : ''"
              >
                <template v-if="verdict.kind === 'rate'">{{ rate }}</template>
                <template v-else-if="verdict.kind === 'since'">{{
                  ageShort(verdict.at, locale)
                }}</template>
                <template v-else>0</template>
              </div>
              <div class="mt-1.5 text-[12.5px] text-muted">
                {{
                  verdict.kind === 'rate'
                    ? t('deck.verdict.rate')
                    : verdict.kind === 'never'
                      ? t('deck.verdict.never')
                      : verdict.silent
                        ? t('deck.verdict.silent')
                        : t('deck.verdict.since')
                }}
              </div>
            </template>
            <template v-else>
              <div class="skeleton h-11 w-28" />
              <div class="skeleton mt-2 h-3 w-24" />
            </template>
          </div>

          <ul class="space-y-1.5 text-[13px] text-muted">
            <li>
              <b v-if="members" class="font-mono font-semibold text-text">{{ members }}</b>
              <span v-else-if="!channel.full_loaded" class="skeleton inline-block h-3 w-10" />
              <b v-else class="font-mono text-faint">—</b>
              {{ t('deck.subscribers', pluralCount(channel.members_count ?? 0)) }}
            </li>
            <li>
              <b
                class="font-mono font-semibold"
                :class="channel.unread_count > 0 ? 'text-ch-ink' : 'text-text'"
                >{{ compactNumber(channel.unread_count, locale) }}</b
              >
              {{ t('deck.unreadLong', pluralCount(channel.unread_count)) }}
            </li>
            <li v-if="channel.last_post_at">
              {{ t('deck.lastPostAt', { when: relativeTime(channel.last_post_at, locale) }) }}
            </li>
            <li v-else>{{ t('deck.neverPosted') }}</li>
          </ul>
        </div>

        <div v-if="showChart && channel.pulse" class="mt-3.5 text-ch">
          <PulseChart :weeks="channel.pulse.weeks" :height="40" />
          <div class="mt-1.5 flex justify-between font-mono text-[10.5px] text-faint">
            <span>{{ axis[0] }}</span>
            <span v-if="pulseUnknown">{{
              t('deck.pulseTruncated', { n: channel.pulse.sample })
            }}</span>
            <span v-else>{{ axis[1] }}</span>
            <span>{{ axis[2] }}</span>
          </div>
        </div>
      </div>

      <!-- about -->
      <div class="text-[14px] leading-relaxed text-muted">
        <p v-if="channel.about" class="line-clamp-2 whitespace-pre-line">{{ channel.about }}</p>
        <div v-else-if="!channel.full_loaded" class="space-y-2 pt-1">
          <div class="skeleton h-3 w-full" />
          <div class="skeleton h-3 w-2/3" />
        </div>
        <p v-else class="text-faint italic">{{ t('deck.noAbout') }}</p>
      </div>

      <!-- last post -->
      <div v-if="channel.last_post_at" class="post flex gap-3 rounded-xl p-3">
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
            {{ t('deck.lastPost') }} · {{ relativeTime(channel.last_post_at, locale) }}
            <template v-if="mediaLabel"> · {{ mediaLabel }}</template>
          </div>
          <p class="mt-1 line-clamp-3 text-[14px] leading-snug whitespace-pre-line">
            {{ channel.last_post_text ?? mediaLabel ?? '…' }}
          </p>
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
