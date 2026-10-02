/** Shared transport: bounded requests, consistent errors, and session expiry. */
export const apiUrl = (import.meta.env.VITE_API_URL || '/api').replace(
  /\/$/,
  '',
)

export class ApiError extends Error {
  status: number
  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

export function clearSession() {
  for (const key of ['hireflowToken', 'hireflowUser', 'hireflowOfferLinks'])
    sessionStorage.removeItem(key)
}

export async function apiFetch(
  path: string,
  token: string,
  init: RequestInit = {},
): Promise<Response> {
  const headers = new Headers(init.headers)
  if (token) headers.set('Authorization', `Bearer ${token}`)
  if (init.body && !(init.body instanceof FormData))
    headers.set('Content-Type', 'application/json')
  let response: Response
  try {
    response = await fetch(`${apiUrl}${path}`, {
      ...init,
      headers,
      cache: 'no-store',
      signal: init.signal ?? AbortSignal.timeout(30000),
    })
  } catch {
    throw new ApiError(
      'Unable to reach the service. Check your connection and try again.',
      0,
    )
  }
  if (!response.ok) {
    if (response.status === 401 && token)
      window.dispatchEvent(new Event('hireflow:session-expired'))
    const body = (await response.json().catch(() => ({}))) as {
      detail?: string | { msg: string }[]
    }
    const detail = Array.isArray(body.detail)
      ? body.detail.map((issue) => issue.msg).join('; ')
      : body.detail
    throw new ApiError(
      detail || `Request failed (${response.status})`,
      response.status,
    )
  }
  return response
}

export async function api<T>(
  path: string,
  token: string,
  init: RequestInit = {},
): Promise<T> {
  const response = await apiFetch(path, token, init)
  if (response.status === 204) return undefined as T
  if (!response.headers.get('content-type')?.includes('application/json')) {
    throw new ApiError(
      'The API address is not configured correctly. Contact your administrator.',
      502,
    )
  }
  return response.json() as Promise<T>
}

/** Retrieve bounded API pages without silently truncating the workspace. */
export async function apiList<T>(path: string, token: string): Promise<T[]> {
  const items: T[] = []
  for (let offset = 0; ; offset += 200) {
    const page = await api<T[]>(
      `${path}${path.includes('?') ? '&' : '?'}limit=200&offset=${offset}`,
      token,
    )
    items.push(...page)
    if (page.length < 200) return items
  }
}
