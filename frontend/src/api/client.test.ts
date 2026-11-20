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
    answer(429, JSON.stringify({ error: { code: 'flood_wait', message: 'Wait', retry_after: 7 } }))
    const err = await api.get('/api/x').catch((e: unknown) => e)
    expect(err).toBeInstanceOf(ApiError)
    expect(err).toMatchObject({ status: 429, code: 'flood_wait', message: 'Wait', retryAfter: 7 })
  })

  it('turns a body that is not JSON into an ApiError too', async () => {
    answer(500, 'Internal Server Error')
    const err = await api.post('/api/apply').catch((e: unknown) => e)
    expect(err).toBeInstanceOf(ApiError)
    expect(err).toMatchObject({ status: 500, code: 'http_error', message: 'Internal Server Error' })
  })

  it('returns the parsed body on success', async () => {
    answer(200, JSON.stringify({ ok: true }))
    expect(await api.get('/api/health')).toEqual({ ok: true })
  })
})
