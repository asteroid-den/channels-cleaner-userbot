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
  const data = text ? JSON.parse(text) : null
  if (!response.ok) {
    const err = data?.error
    const detail = typeof data?.detail === 'string' ? data.detail : null
    throw new ApiError(
      response.status,
      err?.code ?? 'http_error',
      err?.message ?? detail ?? response.statusText,
      err?.retry_after ?? null,
    )
  }
  return data as T
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
