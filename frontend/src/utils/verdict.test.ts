import { describe, expect, it } from 'vitest'

import type { Pulse } from '@/api/types'

import { verdictOf } from './verdict'

const pulse = (weeks: (number | null)[], per_week: number): Pulse => ({
  weeks,
  per_week,
  truncated: false,
  sample: 0,
})
const AT = '2026-04-01T00:00:00Z'

describe('verdictOf', () => {
  it('leads with the posting rate for active channels', () => {
    expect(verdictOf({ last_post_at: AT, pulse: pulse([3, 4, 5], 4) })).toEqual({
      kind: 'rate',
      perWeek: 4,
    })
  })
  it('leads with the silence for channels that went quiet', () => {
    expect(verdictOf({ last_post_at: AT, pulse: pulse([0, 0, 0], 0) })).toEqual({
      kind: 'since',
      at: AT,
      silent: true,
    })
    expect(verdictOf({ last_post_at: AT, pulse: pulse([2, 0, 0], 0.2) })).toEqual({
      kind: 'since',
      at: AT,
      silent: false,
    })
  })
  it('handles channels that never posted and pulses still loading', () => {
    expect(verdictOf({ last_post_at: null, pulse: null })).toEqual({ kind: 'never' })
    expect(verdictOf({ last_post_at: AT, pulse: null })).toBeNull()
  })
})
