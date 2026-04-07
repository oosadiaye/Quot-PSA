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
    it('injects auth token when present in localStorage', async () => {
      vi.resetModules()
      await import('../client')

      // Get the request interceptor callback
      const requestInterceptor = (axios.create as ReturnType<typeof vi.fn>)
        .mock.results[0]?.value.interceptors.request.use.mock.calls[0][0]

      localStorage.setItem('authToken', 'test-token-123')

      const config = {
        url: '/accounting/journals/',
        headers: {} as Record<string, string>,
      }
      const result = requestInterceptor(config)

      expect(result.headers['Authorization']).toBe('Token test-token-123')
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
