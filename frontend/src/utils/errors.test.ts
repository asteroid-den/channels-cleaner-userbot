import { describe, expect, it } from 'vitest'

import { actionErrorKind } from './errors'

describe('actionErrorKind', () => {
  it('recognises channels that are no longer reachable', () => {
    expect(actionErrorKind('CHANNEL_PRIVATE')).toBe('gone')
    expect(actionErrorKind('[400 CHANNEL_INVALID] The channel is invalid')).toBe('gone')
  })
  it('recognises flood limits', () => {
    expect(actionErrorKind('Too many flood waits')).toBe('flood')
  })
  it('falls back to unknown', () => {
    expect(actionErrorKind('boom')).toBe('unknown')
    expect(actionErrorKind(null)).toBe('unknown')
  })
})
