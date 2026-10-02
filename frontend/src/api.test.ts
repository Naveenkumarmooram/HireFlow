import { afterEach, describe, expect, it, vi } from 'vitest'
import { api, apiFetch, apiList } from './api'

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('API transport', () => {
  it('sends bearer credentials and JSON content type', async () => {
    const fetch = vi.fn().mockResolvedValue(
      new Response('{"ok":true}', {
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    vi.stubGlobal('fetch', fetch)
    expect(
      await api('/test', 'secret', { method: 'POST', body: '{}' }),
    ).toEqual({ ok: true })
    const options = fetch.mock.calls[0][1]
    expect(options.headers.get('Authorization')).toBe('Bearer secret')
    expect(options.headers.get('Content-Type')).toBe('application/json')
    expect(options.cache).toBe('no-store')
  })
  it('leaves multipart content type to the browser', async () => {
    const fetch = vi.fn().mockResolvedValue(new Response(null, { status: 204 }))
    vi.stubGlobal('fetch', fetch)
    await apiFetch('/upload', 'token', { method: 'POST', body: new FormData() })
    expect(fetch.mock.calls[0][1].headers.has('Content-Type')).toBe(false)
  })
  it('dispatches session expiry for an authenticated 401', async () => {
    const dispatchEvent = vi.fn()
    vi.stubGlobal('window', { dispatchEvent })
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response('{"detail":"Authentication required"}', {
          status: 401,
          headers: { 'Content-Type': 'application/json' },
        }),
      ),
    )
    await expect(api('/private', 'token')).rejects.toMatchObject({
      status: 401,
    })
    expect(dispatchEvent.mock.calls[0][0].type).toBe('hireflow:session-expired')
  })
  it('reports HTML fallback as an API configuration error', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response('<html>app</html>', {
          headers: { 'Content-Type': 'text/html' },
        }),
      ),
    )
    await expect(api('/test', '')).rejects.toMatchObject({ status: 502 })
  })
  it('retrieves subsequent pages instead of silently dropping records', async () => {
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify(Array.from({ length: 200 }, (_, id) => ({ id }))),
          { headers: { 'Content-Type': 'application/json' } },
        ),
      )
      .mockResolvedValueOnce(
        new Response('[{"id":200}]', {
          headers: { 'Content-Type': 'application/json' },
        }),
      )
    vi.stubGlobal('fetch', fetch)
    expect(await apiList('/candidates', 'token')).toHaveLength(201)
    expect(fetch.mock.calls[1][0]).toContain('offset=200')
  })
  it('does not retry writes after a network error', async () => {
    const fetch = vi.fn().mockRejectedValue(new Error('offline'))
    vi.stubGlobal('fetch', fetch)
    await expect(
      api('/jobs', 'token', { method: 'POST', body: '{}' }),
    ).rejects.toMatchObject({ status: 0 })
    expect(fetch).toHaveBeenCalledTimes(1)
  })
})
