import type { Channel } from '@/api/types'

/**
 * The one figure the card leads with:
 * - `rate`   — posts per week, for channels that still post at least weekly;
 * - `since`  — time since the last post (`silent` when the whole pulse is empty);
 * - `never`  — the channel has never posted.
 * `null` while the pulse is still loading.
 */
export type Verdict =
  | { kind: 'rate'; perWeek: number }
  | { kind: 'since'; at: string; silent: boolean }
  | { kind: 'never' }

export function verdictOf(channel: Pick<Channel, 'last_post_at' | 'pulse'>): Verdict | null {
  if (!channel.last_post_at) return { kind: 'never' }
  const pulse = channel.pulse
  if (!pulse) return null
  if (pulse.per_week >= 1) return { kind: 'rate', perWeek: pulse.per_week }
  return { kind: 'since', at: channel.last_post_at, silent: pulse.weeks.every((w) => !w) }
}
