import { describe, expect, it } from 'vitest'

import { hotkeyName } from './useHotkeys'

const press = (key: string, code: string, mod = false) => ({
  key,
  code,
  ctrlKey: mod,
  metaKey: false,
})

describe('hotkeyName', () => {
  it('uses the physical key for letters on a Russian layout', () => {
    expect(hotkeyName(press('ь', 'KeyM'))).toBe('m')
    expect(hotkeyName(press('ф', 'KeyA'))).toBe('a')
    expect(hotkeyName(press('я', 'KeyZ', true))).toBe('mod+z')
  })

  it('keeps named keys as they are', () => {
    expect(hotkeyName(press('ArrowLeft', 'ArrowLeft'))).toBe('ArrowLeft')
    expect(hotkeyName(press('Enter', 'Enter', true))).toBe('mod+Enter')
    expect(hotkeyName(press('Escape', 'Escape'))).toBe('Escape')
  })

  it('lowercases latin letters', () => {
    expect(hotkeyName(press('M', 'KeyM'))).toBe('m')
  })
})
