import { describe, expect, it } from 'vitest'

import { activityOf, initials } from './format'

describe('activityOf', () => {
  const now = Date.parse('2026-01-31T00:00:00Z')
  const daysAgo = (d: number) => new Date(now - d * 86_400_000).toISOString()

  it('classifies by last post age', () => {
    expect(activityOf(daysAgo(1), now)).toBe('fresh')
    expect(activityOf(daysAgo(30), now)).toBe('slow')
    expect(activityOf(daysAgo(120), now)).toBe('stale')
    expect(activityOf(daysAgo(400), now)).toBe('dead')
    expect(activityOf(null, now)).toBe('dead')
  })
})

describe('initials', () => {
  it('takes up to two letters', () => {
    expect(initials('Daily Digest')).toBe('DD')
    expect(initials('Кофе и код')).toBe('КИ')
    expect(initials('— 🙂')).toBe('?')
  })
})
