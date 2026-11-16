<script setup lang="ts">
import { ref, watch } from 'vue'

import { colorFor, initials } from '@/utils/format'

const props = withDefaults(
  defineProps<{ id: number; title: string; src: string | null; size?: number; rounded?: string }>(),
  { size: 48, rounded: '9999px' },
)

const failed = ref(false)
watch(
  () => props.src,
  () => (failed.value = false),
)
</script>

<template>
  <div
    class="relative shrink-0 overflow-hidden select-none"
    :style="{
      width: `${size}px`,
      height: `${size}px`,
      borderRadius: rounded,
      background: colorFor(id),
    }"
  >
    <img
      v-if="src && !failed"
      :src="src"
      :alt="title"
      class="h-full w-full object-cover"
      draggable="false"
      loading="lazy"
      @error="failed = true"
    />
    <span
      v-else
      class="flex h-full w-full items-center justify-center font-semibold text-white"
      :style="{ fontSize: `${Math.round(size * 0.38)}px` }"
    >
      {{ initials(title) }}
    </span>
  </div>
</template>
