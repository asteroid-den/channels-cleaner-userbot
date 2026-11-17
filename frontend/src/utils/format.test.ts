import { describe, expect, it } from 'vitest'

import { initials } from './format'

describe('initials', () => {
  it('takes up to two letters', () => {
    expect(initials('Daily Digest')).toBe('DD')
    expect(initials('Кофе и код')).toBe('КИ')
    expect(initials('— 🙂')).toBe('?')
  })
})
