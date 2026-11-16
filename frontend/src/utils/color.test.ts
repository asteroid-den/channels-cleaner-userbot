import { describe, expect, it } from 'vitest'

import { companion, normalize } from './color'

const lightness = ([r, g, b]: number[]) => (Math.max(r!, g!, b!) + Math.min(r!, g!, b!)) / 2 / 255

describe('normalize', () => {
  it('pulls very dark and very light colours into a usable band', () => {
    expect(lightness(normalize([10, 20, 60]))).toBeGreaterThan(0.45)
    expect(lightness(normalize([250, 240, 230]))).toBeLessThan(0.65)
  })
  it('keeps greys neutral', () => {
    const [r, g, b] = normalize([128, 128, 130])
    expect(Math.max(r, g, b) - Math.min(r, g, b)).toBeLessThan(30)
  })
})

describe('companion', () => {
  it('is darker than the base colour', () => {
    const base = normalize([124, 92, 255])
    expect(lightness(companion(base))).toBeLessThan(lightness(base))
  })
})
