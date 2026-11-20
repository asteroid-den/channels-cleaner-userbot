export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly retryAfter: number | null

  constructor(status: number, code: string, message: string, retryAfter: number | null = null) {
    super(message)
    this.status = status
    this.code = code
    this.retryAfter = retryAfter
  }
}

async function request<T>(method: string, url: string, body?: unknown): Promise<T> {
  const response = await fetch(url, {
    method,
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  const text = await response.text()
  const data = parseJson(text)
  if (!response.ok) {
    // The API always answers {error: {code, message}}; anything else (a proxy, a crash before the app) still
    // becomes an ApiError the views know how to show
    const err = (data as ErrorBody | null)?.error
    throw new ApiError(
      response.status,
      err?.code ?? 'http_error',
      err?.message ?? (text.trim() || response.statusText),
      err?.retry_after ?? null,
    )
  }
  return data as T
}

interface ErrorBody {
  error?: { code?: string; message?: string; retry_after?: number | null }
}

function parseJson(text: string): unknown {
  if (!text) return null
  try {
    return JSON.parse(text)
  } catch {
    return null
  }
}

export const api = {
  get: <T>(url: string) => request<T>('GET', url),
  post: <T>(url: string, body: unknown = {}) => request<T>('POST', url, body),
  put: <T>(url: string, body: unknown) => request<T>('PUT', url, body),
  del: <T>(url: string) => request<T>('DELETE', url),
}

export type SseHandlers = Record<string, (data: never) => void>

/** Subscribe to a Server-Sent Events stream; returns an unsubscribe function. */
export function subscribe(url: string, handlers: SseHandlers): () => void {
  const source = new EventSource(url)
  for (const [event, handler] of Object.entries(handlers)) {
    source.addEventListener(event, (e) => {
      handler(JSON.parse((e as MessageEvent<string>).data) as never)
    })
  }
  return () => source.close()
}
