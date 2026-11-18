import { useI18n } from 'vue-i18n'

import type { ChatKind } from '@/api/types'
import { useDeckStore } from '@/stores/deck'

/**
 * `t` that prefers the wording written for supergroups (`group.<key>`) while the deck shows
 * them, and falls back to the shared one. Channels always use the shared keys.
 * `kind` defaults to the kind the deck shows; a card passes its own channel's.
 */
export function useKindI18n(kind?: () => ChatKind) {
  const { t, te } = useI18n()
  const deck = useDeckStore()

  function tk(key: string, named?: Record<string, unknown> | number): string {
    const resolved =
      (kind?.() ?? deck.kind) === 'supergroup' && te(`group.${key}`) ? `group.${key}` : key
    return typeof named === 'number' ? t(resolved, named) : t(resolved, named ?? {})
  }

  return { t, tk }
}
