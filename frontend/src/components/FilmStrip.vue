<script setup lang="ts">
import { computed } from 'vue'

import type { Channel, Decision } from '@/api/types'
import type { HistoryEntry } from '@/stores/deck'

import AppIcon, { type IconName } from './AppIcon.vue'
import ChannelAvatar from './ChannelAvatar.vue'

const props = defineProps<{ items: Channel[]; history: HistoryEntry[] }>()

const PAST = 4
const AHEAD = 9

const past = computed(() => props.history.slice(-PAST))
const upcoming = computed(() => props.items.slice(1, AHEAD + 1))
const current = computed(() => props.items[0] ?? null)

const MARK: Record<Decision, { icon: IconName; cls: string }> = {
  keep: { icon: 'check', cls: 'bg-success' },
  unsubscribe: { icon: 'x', cls: 'bg-danger' },
  skip: { icon: 'skip', cls: 'bg-faint' },
  mute: { icon: 'bellOff', cls: 'bg-warn' },
  archive: { icon: 'archive', cls: 'bg-accent' },
}
</script>

<template>
  <div class="flex items-center justify-center gap-2 overflow-hidden px-2 py-1">
    <!-- decided -->
    <div class="flex w-[184px] shrink-0 justify-end gap-2">
      <TransitionGroup
        enter-from-class="opacity-0 scale-75"
        enter-active-class="transition duration-300"
        leave-to-class="opacity-0 scale-75"
        leave-active-class="transition duration-200 absolute"
        move-class="transition duration-300"
      >
        <div v-for="h in past" :key="`p${h.channel.id}`" class="relative opacity-45">
          <ChannelAvatar
            :id="h.channel.id"
            :title="h.channel.title"
            :src="h.channel.avatar_url"
            :size="40"
            rounded="12px"
          />
          <span
            class="absolute -right-1 -bottom-1 flex h-4.5 w-4.5 items-center justify-center rounded-full text-white ring-2 ring-bg"
            :class="MARK[h.decision].cls"
          >
            <AppIcon :name="MARK[h.decision].icon" :size="10" :stroke="3" />
          </span>
        </div>
      </TransitionGroup>
    </div>

    <!-- current -->
    <div class="shrink-0 rounded-[16px] p-[3px] ring-2 ring-accent">
      <Transition
        mode="out-in"
        enter-from-class="opacity-0 scale-75"
        enter-active-class="transition duration-200"
        leave-to-class="opacity-0"
        leave-active-class="transition duration-100"
      >
        <ChannelAvatar
          v-if="current"
          :id="current.id"
          :key="current.id"
          :title="current.title"
          :src="current.avatar_url"
          :size="52"
          rounded="13px"
        />
        <div v-else class="h-[52px] w-[52px] rounded-[13px] bg-surface-2" />
      </Transition>
    </div>

    <!-- upcoming -->
    <div class="relative flex w-[184px] shrink-0 gap-2 overflow-hidden sm:w-[424px]">
      <TransitionGroup
        move-class="transition duration-300"
        enter-from-class="opacity-0"
        enter-active-class="transition duration-300"
      >
        <ChannelAvatar
          v-for="c in upcoming"
          :id="c.id"
          :key="`u${c.id}`"
          :title="c.title"
          :src="c.avatar_url"
          :size="40"
          rounded="12px"
        />
      </TransitionGroup>
      <div
        class="pointer-events-none absolute inset-y-0 right-0 w-16 bg-gradient-to-l from-bg to-transparent"
      />
    </div>
  </div>
</template>
