import { afterEach, describe, expect, it, vi } from 'vitest'

import { api, ApiError } from './client'

function answer(status: number, body: string) {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue(new Response(body, { status, statusText: 'Oops' })),
  )
}

afterEach(() => vi.unstubAllGlobals())

describe('api client', () => {
  it('reads the error shape the API answers with', async () => {
    answer(429, JSON.stringify({ ok: false, type: 'flood_wait', message: 'Wait', retry_after: 7 }))
    const err = await api.get('/api/x').catch((e: unknown) => e)
    expect(err).toBeInstanceOf(ApiError)
    expect(err).toMatchObject({ status: 429, type: 'flood_wait', message: 'Wait', retryAfter: 7 })
  })

  it('adds what Telegram said to the message', async () => {
    answer(
      502,
      JSON.stringify({
        ok: false,
        type: 'telegram_error',
        message: 'Refused',
        reason: 'CHANNEL_PRIVATE',
      }),
    )
    const err = await api.get('/api/channels/1/full').catch((e: unknown) => e)
    expect(err).toMatchObject({ type: 'telegram_error', message: 'Refused: CHANNEL_PRIVATE' })
  })

  it('turns a body that is not JSON into an ApiError too', async () => {
    answer(500, 'Internal Server Error')
    const err = await api.post('/api/apply').catch((e: unknown) => e)
    expect(err).toBeInstanceOf(ApiError)
    expect(err).toMatchObject({ status: 500, type: 'http_error', message: 'Internal Server Error' })
  })

  it('returns the parsed body on success', async () => {
    answer(200, JSON.stringify({ ok: true }))
    expect(await api.get('/api/health')).toEqual({ ok: true })
  })
})
