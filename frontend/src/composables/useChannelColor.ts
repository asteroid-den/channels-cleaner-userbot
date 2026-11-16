import { ref, watch, type Ref } from 'vue'

import type { Channel } from '@/api/types'
import { companion, css, hexToRgb, normalize, sampleImage, type Rgb } from '@/utils/color'
import { colorFor } from '@/utils/format'

/**
 * Keeps --ch / --ch2 on <html> in sync with the given channel's avatar colour.
 * Falls back to the palette colour derived from the id when there is no avatar.
 */
export function useChannelColor(channel: Ref<Channel | null>) {
  const rgb = ref<Rgb | null>(null)

  async function apply(ch: Channel | null) {
    if (!ch) return
    const fallback = normalize(hexToRgb(colorFor(ch.id)))
    const sampled = ch.avatar_url ? await sampleImage(ch.avatar_url) : null
    if (channel.value?.id !== ch.id) return // the user already moved on
    const base = sampled ? normalize(sampled) : fallback
    rgb.value = base
    const root = document.documentElement.style
    root.setProperty('--ch', css(base))
    root.setProperty('--ch2', css(companion(base)))
  }

  watch(
    () => channel.value?.id,
    () => void apply(channel.value),
    { immediate: true },
  )
  return rgb
}
