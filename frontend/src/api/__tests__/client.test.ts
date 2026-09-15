import { describe, it, expect, beforeEach, vi } from 'vitest'
import axios from 'axios'

// Mock axios before importing apiClient
vi.mock('axios', () => {
  const interceptors = {
    request: { use: vi.fn() },
    response: { use: vi.fn() },
  }
  const instance = {
    interceptors,
    defaults: { headers: { common: {} } },
  }
  return {
    default: {
      create: vi.fn(() => instance),
    },
  }
})

describe('apiClient', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    // sessionStorage too — it is where the auth token actually lives, so
    // without this each test inherits the previous one's token and any
    // assertion about a *missing* header silently passes on stale state.
    sessionStorage.clear()
  })

  it('creates axios instance with correct baseURL', async () => {
    // Re-import to trigger module execution
    vi.resetModules()
    await import('../client')

    expect(axios.create).toHaveBeenCalledWith(
      expect.objectContaining({
        baseURL: expect.stringContaining('/api/v1'),
        headers: { 'Content-Type': 'application/json' },
      })
    )
  })

  it('registers request and response interceptors', async () => {
    vi.resetModules()
    const mod = await import('../client')
    const client = mod.default

    expect(client.interceptors.request.use).toHaveBeenCalledTimes(1)
    expect(client.interceptors.response.use).toHaveBeenCalledTimes(1)
  })

  describe('request interceptor', () => {
    // sessionStorage, not localStorage. client.ts reads the token from
    // sessionStorage only, on purpose: localStorage is XSS-readable for
    // the lifetime of the browser profile, sessionStorage only for the
    // tab. This test still set localStorage and expected the header,
    // so it asserted the very behaviour that was deliberately removed —
    // and had been failing ever since.
    it('injects auth token when present in sessionStorage', async () => {
      vi.resetModules()
      await import('../client')

      // Get the request interceptor callback
      const requestInterceptor = (axios.create as ReturnType<typeof vi.fn>)
        .mock.results[0]?.value.interceptors.request.use.mock.calls[0][0]

      sessionStorage.setItem('authToken', 'test-token-123')

      const config = {
        url: '/accounting/journals/',
        headers: {} as Record<string, string>,
      }
      const result = requestInterceptor(config)

      expect(result.headers['Authorization']).toBe('Token test-token-123')
    })

    it('ignores a token sitting in localStorage', async () => {
      // The point of reading sessionStorage is that localStorage is not
      // read. Without this, a change that adds a localStorage fallback
      // "to be helpful" passes every other test in this file while
      // widening the XSS window back to the whole browser profile.
      vi.resetModules()
      await import('../client')

      const requestInterceptor = (axios.create as ReturnType<typeof vi.fn>)
        .mock.results[0]?.value.interceptors.request.use.mock.calls[0][0]

      localStorage.setItem('authToken', 'xss-readable-token')

      const config = {
        url: '/accounting/journals/',
        headers: {} as Record<string, string>,
      }
      const result = requestInterceptor(config)

      expect(result.headers['Authorization']).toBeUndefined()
    })

    it('injects tenant domain header when present', async () => {
      vi.resetModules()
      await import('../client')

      const requestInterceptor = (axios.create as ReturnType<typeof vi.fn>)
        .mock.results[0]?.value.interceptors.request.use.mock.calls[0][0]

      localStorage.setItem('authToken', 'test-token')
      localStorage.setItem('tenantDomain', 'acme.localhost')

      const config = {
        url: '/accounting/journals/',
        headers: {} as Record<string, string>,
      }
      const result = requestInterceptor(config)

      expect(result.headers['X-Tenant-Domain']).toBe('acme.localhost')
    })

    it('skips auth headers for login endpoints', async () => {
      vi.resetModules()
      await import('../client')

      const requestInterceptor = (axios.create as ReturnType<typeof vi.fn>)
        .mock.results[0]?.value.interceptors.request.use.mock.calls[0][0]

      localStorage.setItem('authToken', 'stale-token')

      const config = {
        url: '/core/auth/login/',
        headers: {} as Record<string, string>,
      }
      const result = requestInterceptor(config)

      expect(result.headers['Authorization']).toBeUndefined()
    })

    it('does not inject tenant domain if value is null string', async () => {
      vi.resetModules()
      await import('../client')

      const requestInterceptor = (axios.create as ReturnType<typeof vi.fn>)
        .mock.results[0]?.value.interceptors.request.use.mock.calls[0][0]

      localStorage.setItem('authToken', 'test-token')
      localStorage.setItem('tenantDomain', 'null')

      const config = {
        url: '/accounting/journals/',
        headers: {} as Record<string, string>,
      }
      const result = requestInterceptor(config)

      expect(result.headers['X-Tenant-Domain']).toBeUndefined()
    })
  })
})
